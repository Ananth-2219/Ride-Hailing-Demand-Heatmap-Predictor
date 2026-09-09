"""Serve trained model predictions and the original taxi-zone polygons."""

from contextlib import asynccontextmanager
import json
import logging
import math
import os

import joblib
import pandas as pd
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
Day = Literal["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
Hour = Annotated[int, Query(ge=0, le=23)]
ZONE_IDS = set(range(1, 264))
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
logger = logging.getLogger(__name__)


def feature_rows(day: str, hour: int) -> pd.DataFrame:
    day_index = DAYS.index(day)
    return pd.DataFrame({
        'zone_id': sorted(ZONE_IDS), 'hour_of_day': hour,
        'day_of_week': day_index, 'is_weekend': day_index >= 5,
    })


def predict_rows(model, day: str, hour: int) -> list[dict]:
    features = feature_rows(day, hour)
    values = model.predict(features)
    if len(values) != 263 or not all(math.isfinite(float(v)) for v in values):
        raise ValueError('Model must return 263 finite predictions')
    return [{'zoneId': int(zone), 'predictedCount': max(0.0, float(value))}
            for zone, value in zip(features.zone_id, values)]


def validate_zones(zones: dict) -> dict[int, str]:
    if zones["type"] != "FeatureCollection":
        raise ValueError("Expected a GeoJSON FeatureCollection")
    names = {}
    for feature in zones["features"]:
        properties = feature["properties"]
        zone_id = properties["LocationID"]
        geometry = feature["geometry"]
        if (feature["type"] != "Feature" or type(zone_id) is not int
                or geometry["type"] not in ("Polygon", "MultiPolygon")
                or not geometry["coordinates"]):
            raise ValueError("Expected taxi-zone IDs and nonempty polygon geometry")
        if not isinstance(properties["zone"], str) or not properties["zone"].strip():
            raise ValueError(f"Missing zone name for LocationID {zone_id}")
        names[zone_id] = properties["zone"]
    if set(names) != ZONE_IDS:
        raise ValueError("GeoJSON must contain LocationID values 1–263")
    return names


def create_app(data_dir: Path = DATA_DIR) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.errors = {}
        try:
            # Only load the trusted artifact produced by train_model.py.
            app.state.model = joblib.load(data_dir / 'model.joblib')
            predict_rows(app.state.model, 'Mon', 18)
        except Exception as error:
            message = 'model.joblib is missing or invalid. Run backend/train_model.py and restart the API.'
            app.state.errors['model'] = message
            logger.error('%s Details: %s', message, error)
        try:
            with (data_dir / 'taxi_zones.geojson').open(encoding='utf-8') as source:
                zones = json.load(source)
            app.state.zone_names = validate_zones(zones)
            app.state.zones_response = JSONResponse(zones, media_type='application/geo+json')
        except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
            message = 'taxi_zones.geojson is missing or invalid. Restore the local file and restart the API.'
            app.state.errors['zones'] = message
            logger.error('%s Details: %s', message, error)
        yield

    app = FastAPI(title="Ride-Hailing Demand API", lifespan=lifespan)
    frontend_origin = os.environ.get(
        "FRONTEND_ORIGIN",
        "https://ride-hailing-demand-heatmap-predictor-1.onrender.com",
    ).strip().rstrip("/")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            frontend_origin,
        ],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    def require_data(request: Request, *keys: str) -> None:
        for key in keys:
            if key in request.app.state.errors:
                raise HTTPException(status_code=503, detail=request.app.state.errors[key])

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/demand")
    def demand(request: Request, day: Day, hour: Hour) -> dict:
        require_data(request, "model")
        return {"day": day, "hour": hour, "data": predict_rows(request.app.state.model, day, hour)}

    @app.get("/api/zones")
    def zones(request: Request) -> JSONResponse:
        require_data(request, "zones")
        return request.app.state.zones_response

    @app.get("/api/recommend")
    def recommend(
        request: Request, day: Day, hour: Hour,
        top: Annotated[int, Query(ge=1, le=263)] = 5,
    ) -> dict:
        require_data(request, "model", "zones")
        rows = predict_rows(request.app.state.model, day, hour)
        # Break equal-demand ties by ID for reproducible results; never mutate the cache.
        ranked = sorted(rows, key=lambda row: (-row["predictedCount"], row["zoneId"]))[:top]
        return {
            "day": day, "hour": hour,
            "recommendations": [
                {"zoneId": row["zoneId"],
                 "zoneName": request.app.state.zone_names[row["zoneId"]],
                 "predictedCount": row["predictedCount"]}
                for row in ranked
            ],
        }

    return app


app = create_app()
