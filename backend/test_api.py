"""Offline API tests using the existing Phase 1 artifacts."""

import copy
import json
import math
import joblib
import numpy as np
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import DATA_DIR, create_app, feature_rows


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = joblib.load(DATA_DIR / 'model.joblib')
        cls.demand = {}
        for day in ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'):
            cls.demand[day] = {}
            for hour in range(24):
                values = cls.model.predict(feature_rows(day, hour))
                cls.demand[day][str(hour)] = [
                    {'zoneId': z, 'predictedCount': max(0.0, float(v))}
                    for z, v in zip(range(1, 264), values)]
        cls.zones = json.loads((DATA_DIR / "taxi_zones.geojson").read_text())
        cls.client = TestClient(create_app())
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_health(self):
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_demand_all_buckets_match_model(self):
        for day, hours in self.demand.items():
            for hour, expected in hours.items():
                with self.subTest(day=day, hour=hour):
                    response = self.client.get('/api/demand', params={'day': day, 'hour': hour})
                    self.assertEqual(response.status_code, 200)
                    body = response.json()
                    self.assertEqual((body['day'], body['hour']), (day, int(hour)))
                    np.testing.assert_allclose([r['predictedCount'] for r in body['data']],
                                               [r['predictedCount'] for r in expected], rtol=1e-12)
                    self.assertTrue(all(math.isfinite(r['predictedCount']) and r['predictedCount'] >= 0 for r in body['data']))
                    self.assertEqual(len(body['data']), 263)
                    self.assertEqual({r['zoneId'] for r in body['data']}, set(range(1, 264)))
                    self.assertTrue(all('predictedCount' in r for r in body['data']))

    def test_invalid_day_and_hour(self):
        for endpoint in ('/api/demand', '/api/recommend'):
            for params in (
                {'day': 'Monday', 'hour': 18}, {'day': 'mon', 'hour': 18},
                {'day': 'Mon', 'hour': -1}, {'day': 'Mon', 'hour': 24},
                {'day': 'Mon', 'hour': '1.5'}, {'day': 'Mon', 'hour': 'bad'},
                {'day': 'Mon'}, {'hour': 18}, {},
            ):
                with self.subTest(endpoint=endpoint, params=params):
                    response = self.client.get(endpoint, params=params)
                    self.assertEqual(response.status_code, 422)
                    self.assertIn('detail', response.json())

    def test_zones_preserve_entire_geojson(self):
        response = self.client.get('/api/zones')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.zones)
        self.assertEqual(response.json()['type'], 'FeatureCollection')
        self.assertEqual({f['properties']['LocationID'] for f in response.json()['features']},
                         set(range(1, 264)))

    def test_recommendations_and_names(self):
        names = {f['properties']['LocationID']: f['properties']['zone']
                 for f in self.zones['features']}
        for top in (1, 5, 263):
            response = self.client.get('/api/recommend', params={'day': 'Mon', 'hour': 18, 'top': top})
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual((body['day'], body['hour']), ('Mon', 18))
            expected = sorted(self.demand['Mon']['18'], key=lambda r: (-r['predictedCount'], r['zoneId']))[:top]
            self.assertEqual([r['zoneId'] for r in body['recommendations']], [r['zoneId'] for r in expected])
            for actual, row in zip(body['recommendations'], expected):
                self.assertAlmostEqual(actual['predictedCount'], row['predictedCount'], places=9)
                self.assertEqual(actual['zoneName'], names[row['zoneId']])
        self.assertEqual(len(self.client.get('/api/recommend?day=Mon&hour=18').json()['recommendations']), 5)

    def test_invalid_top(self):
        for top in (0, -1, 264, 'bad', '2.5'):
            with self.subTest(top=top):
                self.assertEqual(self.client.get('/api/recommend', params={
                    'day': 'Mon', 'hour': 18, 'top': top}).status_code, 422)

    def test_cors(self):
        for origin in ('http://localhost:5173', 'http://127.0.0.1:5173'):
            response = self.client.options('/api/demand', headers={
                'Origin': origin, 'Access-Control-Request-Method': 'GET'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['access-control-allow-origin'], origin)

    def test_no_request_time_disk_reads(self):
        with patch.object(Path, 'open', side_effect=AssertionError('Unexpected disk read')), \
             patch('main.joblib.load', side_effect=AssertionError('Unexpected model reload')):
            for url in ('/health', '/api/demand?day=Mon&hour=18', '/api/zones',
                        '/api/recommend?day=Mon&hour=18'):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_names_match_ids_with_reversed_feature_order(self):
        zones = copy.deepcopy(self.zones)
        zones['features'].reverse()
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / 'taxi_zones.geojson').write_text(json.dumps(zones))
            (directory / 'model.joblib').write_bytes((DATA_DIR / 'model.joblib').read_bytes())
            with TestClient(create_app(directory)) as client:
                expected = {f['properties']['LocationID']: f['properties']['zone'] for f in self.zones['features']}
                for row in client.get('/api/recommend?day=Mon&hour=18').json()['recommendations']:
                    self.assertEqual(row['zoneName'], expected[row['zoneId']])

    def test_missing_corrupted_and_incomplete_files(self):
        for filename, endpoint, healthy_endpoint in (
            ('model.joblib', '/api/demand?day=Mon&hour=18', '/api/zones'),
            ('taxi_zones.geojson', '/api/zones', '/api/demand?day=Mon&hour=18'),
        ):
            for contents in (None, '{broken json', '{}', 'null'):
                with self.subTest(filename=filename, contents=contents), tempfile.TemporaryDirectory() as folder:
                    directory = Path(folder)
                    for name in ('model.joblib', 'taxi_zones.geojson'):
                        if name != filename:
                            (directory / name).write_bytes((DATA_DIR / name).read_bytes())
                    if contents is not None:
                        (directory / filename).write_text(contents)
                    with self.assertLogs('main', level='ERROR'), TestClient(create_app(directory)) as client:
                        response = client.get(endpoint)
                        self.assertEqual(response.status_code, 503)
                        self.assertIn(filename, response.json()['detail'])
                        self.assertEqual(client.get('/api/recommend?day=Mon&hour=18').status_code, 503)
                        self.assertEqual(client.get('/health').status_code, 200)
                        self.assertEqual(client.get(healthy_endpoint).status_code, 200)


if __name__ == '__main__':
    unittest.main()
