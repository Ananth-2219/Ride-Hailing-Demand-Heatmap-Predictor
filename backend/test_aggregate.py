"""Small correctness checks: python -m unittest discover -s backend."""

from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

import duckdb

from aggregate import aggregate


class AggregationTests(unittest.TestCase):
    def test_calendar_denominator_cleaning_and_zero_buckets(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.parquet"
            with duckdb.connect() as connection:
                connection.execute("""
                    CREATE TABLE trips(tpep_pickup_datetime VARCHAR, PULocationID VARCHAR);
                    INSERT INTO trips VALUES
                    ('2026-05-04 18:00:00', '1'),
                    ('2026-05-04 18:30:00', '1'),
                    ('2026-05-11 18:00:00', '1'),
                    ('2026-05-01 00:00:00', '2'),
                    ('2026-05-31 23:59:59', '263'),
                    (NULL, '1'), ('bad timestamp', '1'), ('infinity', '1'),
                    ('2026-05-04 18:00:00', NULL),
                    ('2026-05-04 18:00:00', '0'),
                    ('2026-05-04 18:00:00', '264'),
                    ('2026-05-04 18:00:00', '1.5'),
                    ('2026-05-04 18:00:00', 'bad zone'),
                    ('2026-05-04 18:00:00', 'NaN'),
                    ('2026-05-04 18:00:00', 'Infinity'),
                    ('2026-04-30 23:59:59', '1'),
                    ('2026-06-01 00:00:00', '1')
                """)
                connection.execute("COPY trips TO ? (FORMAT PARQUET)", [str(path)])
            with redirect_stdout(io.StringIO()):
                demand = aggregate(path, list(range(1, 264)))
            self.assertEqual(demand['Mon']['18'][0]['predictedCount'], 0.75)
            self.assertEqual(demand['Fri']['0'][1]['predictedCount'], 0.2)
            self.assertEqual(demand['Sun']['23'][262]['predictedCount'], 0.2)
            self.assertEqual(demand['Mon']['18'][1]['predictedCount'], 0.0)
            self.assertEqual(len(demand), 7)
            for hours in demand.values():
                self.assertEqual(set(hours), {str(h) for h in range(24)})
                for rows in hours.values():
                    self.assertEqual([r['zoneId'] for r in rows], list(range(1, 264)))

    def test_wrong_month_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "wrong.parquet"
            with duckdb.connect() as connection:
                connection.execute("""
                    COPY (SELECT TIMESTAMP '2025-05-01' AS tpep_pickup_datetime,
                                 1 AS PULocationID) TO ? (FORMAT PARQUET)
                """, [str(path)])
            with self.assertRaisesRegex(ValueError, 'No valid May 2026'):
                aggregate(path, list(range(1, 264)))


if __name__ == '__main__':
    unittest.main()
