"""Model artifact and leakage-free baseline checks; no training or network needed."""

import unittest

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import OneHotEncoder

from train_model import DATA, FEATURES, baseline_predict, training_table
from main import feature_rows


class ModelTests(unittest.TestCase):
    def test_zone_encoding_and_monday_predictions(self):
        model = joblib.load(DATA / 'model.joblib')
        features = feature_rows('Mon', 18)
        self.assertEqual(features.zone_id.tolist(), list(range(1, 264)))
        self.assertTrue((features.hour_of_day == 18).all())
        self.assertTrue((features.day_of_week == 0).all())
        self.assertTrue((features.is_weekend == 0).all())
        sample_ids = [1, 50, 100, 161, 200]
        sample = features[features.zone_id.isin(sample_ids)]
        encoded = model.named_steps['preprocessing'].transform(sample).toarray()
        encoder = model.named_steps['preprocessing'].named_transformers_['categories']
        self.assertEqual(encoder.categories_[0].tolist(), list(range(1, 264)))
        # Only the two differing one-hot zone columns should change.
        for row in encoded[1:]:
            self.assertEqual(np.count_nonzero(encoded[0] != row), 2)
        predictions = model.predict(sample)
        print('\nDirect saved-model predictions (Monday 18:00):',
              dict(zip(sample_ids, predictions.tolist())))
        # These particular zones have distinct historical profiles. Prevent the
        # depth-limited model from pooling them into one prediction again.
        self.assertEqual(len(np.unique(np.round(predictions, 8))), len(sample_ids))
        all_predictions = model.predict(features)
        _, frequencies = np.unique(np.round(all_predictions, 8), return_counts=True)
        self.assertLess(frequencies.max(), 263 // 2)

    def test_independent_saved_pipeline(self):
        model = joblib.load(DATA / 'model.joblib')
        self.assertIsInstance(model.named_steps['regressor'], RandomForestRegressor)
        self.assertIsInstance(model.named_steps['preprocessing'].named_transformers_['categories'], OneHotEncoder)
        table = training_table(DATA / 'demand_aggregates.json')
        self.assertEqual(len(table), 44184)
        self.assertFalse(table.duplicated(['zone_id', 'day_of_week', 'hour_of_day']).any())
        values = model.predict(table[FEATURES])
        self.assertTrue(np.isfinite(values).all())
        self.assertTrue((values >= 0).all())
        self.assertGreater(np.ptp(values), 0)
        self.assertFalse(np.allclose(values, table.pickup_count))

    def test_baseline_uses_only_training_targets_and_fallbacks(self):
        train = pd.DataFrame({'zone_id': [1, 1, 2], 'hour_of_day': [18, 19, 18],
                              'pickup_count': [10., 20., 30.]})
        test = pd.DataFrame({'zone_id': [1, 1, 3], 'hour_of_day': [18, 20, 18],
                             'pickup_count': [999., 999., 999.]})
        self.assertEqual(baseline_predict(train, test).tolist(), [10., 15., 20.])


if __name__ == '__main__':
    unittest.main()
