# Ride-Hailing Demand Heatmap Predictor

## Phase 1: historical demand pipeline

Python 3.12 is tested. This phase reads NYC TLC **Yellow Taxi Trip Records for May 2026** and writes `data/demand_aggregates.json`. Phase 1 performs data processing only; Phase 2 serves its output through the API described below.

Sources: [TLC trip records](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page), [May 2026 Parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2026-05.parquet), and [Yellow Taxi data dictionary](https://www.nyc.gov/assets/tlc/downloads/pdf/data_dictionary_trip_records_yellow.pdf).

### Run from a fresh setup (PowerShell)

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe backend/aggregate.py --download
```

Prerequisite: place the already-converted `taxi_zones.geojson` at `data/taxi_zones.geojson`. The script reads it with GeoPandas and validates IDs 1–263, `zone`, `borough`, nonempty geometry, and EPSG:4326. It never converts shapefiles or writes GeoJSON. In this workspace, the supplied GeoJSON was found at `data/taxi_zones/taxi_zones.geojson` and copied byte-for-byte to the requested path, leaving the original untouched.

`--download` fetches the official Parquet only if the input is missing. Fresh downloads go to `data/raw/`. If `data/yellow_tripdata_2026-05.parquet` already exists, the script reuses it in place. Rerun without downloading:

```powershell
.\.venv\Scripts\python.exe backend/aggregate.py
```

Explicit paths are also supported:

```powershell
.\.venv\Scripts\python.exe backend/aggregate.py --input data/raw/yellow_tripdata_2026-05.parquet --zones data/taxi_zones.geojson
```

### Processing and assumptions

- DuckDB reads only `tpep_pickup_datetime` and `PULocationID` from Parquet. All trip-level processing stays in an in-memory DuckDB connection; no persistent database is created.
- `PULocationID` identifies a TLC taxi zone, not a raw latitude/longitude pair. Join output `zoneId` to GeoJSON `LocationID` later.
- Null, unparsable, or nonfinite timestamps are removed. Only pickups from May 1 (inclusive) to June 1, 2026 (exclusive) are retained; out-of-month timestamps are treated as invalid for this monthly analysis.
- Null, nonnumeric, fractional, nonfinite, and out-of-range zone IDs are removed. Valid IDs are 1–263; unknown IDs such as 264/265 are excluded.
- Pickup timestamps are interpreted as NYC local wall-clock times, without timezone conversion. Extract hour 0–23 and weekday Mon–Sun using the pickup timestamp.
- For each zone, weekday, and hour, sum trips and divide by the number of that weekday in the **full May calendar**. May 2026 contains four each of Mon–Thu and five each of Fri–Sun. This equals averaging daily hourly counts with zero-trip dates included. For example, 100 Monday 18:00 pickups over May gives 100 / 4 = 25.0.
- All 263 zones appear in all 168 weekday/hour combinations (44,184 entries); unseen buckets have `predictedCount: 0.0`. Arrays are sorted by zone ID. Values are average trips per one-hour period, not probabilities.
- Full-month input coverage is assumed. Missing records cannot be distinguished from no demand; the script warns if a whole date has no valid pickups. It reports processed/valid rows, rejection counts (which can overlap), zones, calendar coverage, combinations, and min/max demand.
- This is a **historical-average heuristic**, not a trained ML model. It reflects yellow taxi pickups, not all ride-hailing services, and does not account for weather, events, or holidays.

### Output

Query `demand["Mon"]["18"]` to retrieve every zone for Monday at 18:00. Shape example (illustrative values; actual output contains all zones):

```json
{"Mon": {"18": [{"zoneId": 1, "predictedCount": 25.0}]}}
```

The script replaces only `data/demand_aggregates.json` after successful processing. Existing Parquet, shapefile components, and GeoJSON are left unchanged. `frontend/` contains the Phase 3 dashboard documented below.

### Validation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend
```

Tests cover zero-trip calendar averaging, weekday/hour extraction, month boundaries, invalid timestamps and zone IDs, all-zone output, and rejection of a file without valid May 2026 pickups.

The supplied file produced 4,084,337 valid rows from 4,090,836 records (6,499 removed), with 257 observed zones and all 31 dates represented. The output includes 263 zones, 168 day/hour combinations, and demand from 0.0 to 706.2. Input hashes and an independent daily-count calculation were checked after execution.

### Prediction approach: trained model

The data remains NYC TLC Yellow Taxi Trip Records for May 2026. Pickup locations are taxi-zone IDs, not latitude/longitude; geographic placement comes from the unchanged GeoJSON polygons.

1. Phase 1 cleans trips and aggregates average hourly pickups by zone, weekday, and hour.
2. `train_model.py` flattens the existing JSON into 44,184 training rows in memory. No additional raw-trip processing or duplicate training file is needed.
3. Features are `zone_id`, `hour_of_day`, `day_of_week` (Mon=0 through Sun=6), and `is_weekend`. The target `pickup_count` is the existing **average hourly pickup count**, not a monthly total or an individual trip count.
4. A ColumnTransformer one-hot encodes zone and weekday using `OneHotEncoder(handle_unknown="ignore")`; hour and weekend pass through as numerical features. Zone IDs carry no assumed numerical or geographic order.
5. RandomForestRegressor uses 100 trees, no maximum depth cap (one-hot zone splits need enough depth to separate 263 categories), minimum leaf size 2, all available CPU cores, and random state 42. A reproducible 80/20 random bucket split evaluates 35,347 training rows and 8,837 test rows.
6. After evaluation, the full preprocessing/model pipeline is refitted on all 44,184 buckets and saved as `data/model.joblib`. Actual evaluation results and sanity checks are saved in `data/model_metrics.json`.
7. FastAPI loads this model and the existing GeoJSON once per process at startup. Requests build 263 feature rows and call the model dynamically, clamping final values to zero if needed. No fitting, historical-average fallback, or per-request file loading occurs.
8. Both demand and recommendations use the same model prediction function. Phase 3 visualizes those predictions as a React + Leaflet choropleth.

### Baseline and evaluation

The original exact zone/weekday/hour historical average is itself the target in this dataset. Looking it up for a held-out row would leak that row's answer and cannot provide an honest baseline score. Instead, the evaluated historical baseline uses **training-only zone/hour means across weekdays**, falling back to the training zone mean and then the training global mean if necessary. Both methods use the same held-out rows.

Actual results (random state 42):

| Method | MAE | RMSE | R? |
| --- | ---: | ---: | ---: |
| Training-only historical mean baseline | 5.857950 | 21.707877 | 0.863710 |
| Random Forest | 3.602376 | 13.458386 | 0.947614 |

The corrected forest improves all three metrics on this split. This evaluation measures interpolation of monthly bucket averages, not future-trip forecasting or performance on another month. There is only one month of data, and all buckets (including zeros) already exist in Phase 1. The model smooths sparse buckets but does not prove improved accuracy for them. It can predict positive demand for historically zero-demand buckets.

The final refitted model produced predictions from 0.000000 to 627.920989, mean 20.906437 across all combinations. Examples: zone 79 / Sat / 01:00 = 617.858023; zone 1 / Mon / 00:00 = 0.102560; zone 161 / Mon / 18:00 = 423.611388; zone 161 / Sat / 18:00 = 315.060243. These are sanity checks on the deployment model, not test-set performance. Training and final refitting took about 24 seconds on this machine.

### Running the model and backend

From PowerShell in `C:\RideHailing`, using the existing virtual environment:

```powershell
cd C:\RideHailing
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe backend/train_model.py
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

The current environment already has dependencies installed, using local cached packages. No new dataset was downloaded. Training requires only the existing `data/demand_aggregates.json`; the API requires `data/model.joblib` and `data/taxi_zones.geojson`. Data paths resolve from the project location, independently of the working directory. Keep the same dependency versions for training and serving and load only the locally generated, trusted joblib artifact. Restart the API after retraining.

The server runs at `http://127.0.0.1:8000`; interactive documentation is at `http://127.0.0.1:8000/docs`.

| Endpoint | Example | Response |
| --- | --- | --- |
| `GET /health` | `/health` | `{"status":"ok"}`; process liveness only |
| `GET /api/demand` | `/api/demand?day=Mon&hour=18` | `day`, `hour`, and `data` containing all 263 model predictions |
| `GET /api/zones` | `/api/zones` | Original GeoJSON FeatureCollection, preserving polygon coordinates and properties |
| `GET /api/recommend` | `/api/recommend?day=Mon&hour=18&top=5` | `day`, `hour`, and `recommendations` with `zoneId`, `zoneName`, `predictedCount` |

`day` must be exactly Mon?Sun and `hour` an integer 0?23. `top` defaults to 5 and must be an integer 1?263. Invalid or missing required parameters return HTTP 422. Recommendations sort by descending prediction, breaking ties by ascending ID. Names match GeoJSON `LocationID` to API `zoneId`, never array position or assumed geographic adjacency.

Missing or invalid model/GeoJSON returns HTTP 503 on dependent endpoints, with a clear error and server log details. There is no silent fallback to historical averages. `/health` remains a liveness check. CORS allows `http://localhost:5173` and `http://127.0.0.1:5173`.

Run all offline tests after training:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend -v
```

Tests cover the unchanged Phase 1 behavior, independent model loading and all-combination prediction coverage, training-only baseline fallbacks, all API demand buckets against the saved model, nonnegative predictions, recommendation consistency, ID-based zone names, unchanged geometry, CORS, parameter validation, missing/corrupted artifacts, and no request-time file loading.

### Repeated-zone prediction fix

The previous `max_depth=32` forest returned the same Monday 18:00 value for 227 zones. Zone IDs were correctly one-hot encoded, but the depth cap stopped trees before they could separate lower-demand categories: zones 1, 50, and 200 reached the same leaf in every tree. Removing the depth cap fixes this underfitting while retaining 100 trees and `min_samples_leaf=2`. The API and Phase 1 logic are unchanged. Restart any running API after replacing `model.joblib`, because it loads the artifact only at startup.

`test_zone_encoding_and_monday_predictions` directly loads the saved pipeline, prints predictions for zones 1, 50, 100, 161, and 200, checks the exact input features and one-hot differences, and guards against pooling most zones into a common prediction. Zero-demand zones may legitimately tie; every zone is not required to have a unique prediction.

### Phase 3: React dashboard

The dashboard uses React, Vite, Tailwind CSS, Leaflet, and React-Leaflet. Each polygon is a real NYC TLC taxi zone; no grid, points, API keys, or copied GeoJSON are needed. Geometry is fetched once from `/api/zones`. Predictions come from the trained Random Forest through FastAPI, matched by **GeoJSON `LocationID` ? API `zoneId`**, never array position.

Keep the backend running at `http://127.0.0.1:8000`. In a second PowerShell terminal:

```powershell
cd C:\RideHailing\frontend
npm install
npm run dev
```

Open **http://localhost:5173** (or http://127.0.0.1:5173). Node.js 20.19+ or 22.12+ is required by Vite; Node 24 was used here. Optionally copy `.env.example` to `.env` and change `VITE_API_BASE_URL` to use another backend. The default is `http://127.0.0.1:8000`; the URL is configured only in `src/api.js`. Restart Vite after changing the environment.

Choose a weekday and hour (NYC local time). Both demand and top-five recommendations refresh after a short debounce. Superseded requests are aborted, and responses are committed together so rankings and map values refer to the same selection. Hover over polygons for details; click a polygon or recommendation to highlight and zoom to it. Clear the selection to return to the full city view.

Fixed color thresholds represent predicted pickups per hour: low 0?<10, medium 10?<50, high 50?<150, very high 150+. Missing predictions are gray, distinct from zero. These thresholds stay constant across time selections. The legend, selected-zone card, and rankings explain the counts. The layout stacks on mobile, with explicit loading, empty, connection-error, and retry states.

OpenStreetMap supplies the basemap and attribution. Tiles require internet access; if unavailable, the real taxi-zone polygons remain usable and a notice appears. Model estimates are based on May 2026 historical data, not live activity or guaranteed future pickups.

```powershell
npm run build
npm test
npm run test:e2e
```

The production build is written to `frontend/dist/`; `npm run preview` serves it locally. Two unit tests verify ID-based joins and color thresholds. Three Playwright browser tests verify all 263 polygons against the real backend, tooltips, selection, recommendations, day/hour updates, mobile layout, failure/retry, empty state, and stale-response protection. Browser tests require the backend on port 8000 and Microsoft Edge installed; Playwright starts/reuses Vite on port 5173. Only failure/empty states are simulated in tests; normal predictions use the real API.
