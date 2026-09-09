"""Train on existing monthly bucket averages; never read raw trips."""

import json
from pathlib import Path
import time

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

DATA = Path(__file__).resolve().parents[1] / 'data'
DAYS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
FEATURES = ['zone_id', 'hour_of_day', 'day_of_week', 'is_weekend']


def training_table(path: Path) -> pd.DataFrame:
    with path.open(encoding='utf-8') as source:
        demand = json.load(source)
    rows = []
    for day_index, day in enumerate(DAYS):
        for hour in range(24):
            bucket = demand[day][str(hour)]
            if len(bucket) != 263 or {r['zoneId'] for r in bucket} != set(range(1, 264)):
                raise ValueError(f'Incomplete or duplicate zone IDs: {day}/{hour}')
            for row in bucket:
                rows.append(dict(zone_id=row['zoneId'], hour_of_day=hour,
                                 day_of_week=day_index, is_weekend=day_index >= 5,
                                 pickup_count=row['predictedCount']))
    frame = pd.DataFrame(rows)
    if not frame.pickup_count.map(lambda x: pd.notna(x) and 0 <= x < float('inf')).all():
        raise ValueError('Targets must be finite and nonnegative')
    return frame


def baseline_predict(train: pd.DataFrame, test: pd.DataFrame) -> pd.Series:
    """Held-out exact buckets are unavailable: use train-only zone/hour means."""
    means = train.groupby(['zone_id', 'hour_of_day']).pickup_count.mean()
    zone_means = train.groupby('zone_id').pickup_count.mean()
    global_mean = train.pickup_count.mean()
    return pd.Series([means.get((r.zone_id, r.hour_of_day),
                                zone_means.get(r.zone_id, global_mean))
                      for r in test.itertuples()], index=test.index)


def make_model() -> Pipeline:
    preprocessing = ColumnTransformer([
        ('categories', OneHotEncoder(handle_unknown='ignore'), ['zone_id', 'day_of_week']),
        ('numeric', 'passthrough', ['hour_of_day', 'is_weekend']),
    ])
    return Pipeline([
        ('preprocessing', preprocessing),
        # One-hot zone splits isolate one category at a time. A shallow depth cap
        # pools hundreds of lower-demand zones into the same terminal leaves.
        ('regressor', RandomForestRegressor(n_estimators=100, max_depth=None,
                                            min_samples_leaf=2, random_state=42, n_jobs=-1)),
    ])


def metrics(actual, predicted) -> dict:
    return {'MAE': float(mean_absolute_error(actual, predicted)),
            'RMSE': float(root_mean_squared_error(actual, predicted)),
            'R2': float(r2_score(actual, predicted))}


def main() -> None:
    started = time.perf_counter()
    frame = training_table(DATA / 'demand_aggregates.json')
    train, test = train_test_split(frame, test_size=0.2, random_state=42)
    model = make_model()
    model.fit(train[FEATURES], train.pickup_count)
    report = {
        'random_state': 42, 'training_rows': len(train), 'test_rows': len(test),
        'target': 'May 2026 average hourly pickup count for a zone/weekday/hour bucket',
        'baseline_method': 'Training-only zone/hour mean; fallback zone mean then global mean',
        'baseline': metrics(test.pickup_count, baseline_predict(train, test)),
        'random_forest': metrics(test.pickup_count, model.predict(test[FEATURES])),
    }
    for name in ('baseline', 'random_forest'):
        print(name, json.dumps(report[name]), flush=True)
    # Evaluation is finished. Refit the deployment pipeline on all available buckets.
    model.fit(frame[FEATURES], frame.pickup_count)
    predictions = model.predict(frame[FEATURES])
    report['prediction_summary'] = {
        'min': float(predictions.min()), 'max': float(predictions.max()),
        'mean': float(predictions.mean()),
    }
    report['deployment_rows'] = len(frame)
    report['sanity_examples'] = []
    for label, index in [('highest historical bucket', frame.pickup_count.idxmax()),
                         ('lowest historical bucket', frame.pickup_count.idxmin()),
                         ('weekday', frame.query('zone_id == 161 and day_of_week == 0 and hour_of_day == 18').index[0]),
                         ('weekend', frame.query('zone_id == 161 and day_of_week == 5 and hour_of_day == 18').index[0])]:
        row = frame.loc[index]
        example = {'case': label, 'zone_id': int(row.zone_id), 'day': DAYS[int(row.day_of_week)],
                   'hour': int(row.hour_of_day), 'historical_average': float(row.pickup_count),
                   'prediction': float(predictions[index])}
        report['sanity_examples'].append(example)
        print(example, flush=True)
    if predictions.min() < 0 or predictions.max() == predictions.min():
        raise ValueError('Model sanity check failed')
    temporary = DATA / 'model.joblib.tmp'
    joblib.dump(model, temporary, compress=3)
    temporary.replace(DATA / 'model.joblib')
    report['elapsed_seconds'] = time.perf_counter() - started
    (DATA / 'model_metrics.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('Prediction summary:', report['prediction_summary'])
    print(f'Saved {DATA / "model.joblib"}; {len(frame):,} rows; {report["elapsed_seconds"]:.1f} seconds')


if __name__ == '__main__':
    main()
