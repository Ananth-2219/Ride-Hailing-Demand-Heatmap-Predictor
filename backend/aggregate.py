"""Phase 1: aggregate May 2026 yellow taxi pickups into hourly demand."""

import argparse
from collections import Counter
from datetime import date, timedelta
import json
from pathlib import Path
import sys
from urllib.request import urlopen
import shutil

import duckdb
import geopandas as gpd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
FILENAME = "yellow_tripdata_2026-05.parquet"
URL = f"https://d37ci6vzurychx.cloudfront.net/trip-data/{FILENAME}"
START, END = date(2026, 5, 1), date(2026, 6, 1)
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def validate_zones(path):
    """Read existing geometry only; never convert or rewrite zone files."""
    if not path.is_file():
        raise FileNotFoundError(f"Existing taxi zone GeoJSON required: {path}")
    zones = gpd.read_file(path)
    required = ["LocationID", "zone", "borough"]
    if not set(required).issubset(zones.columns):
        raise ValueError(f"GeoJSON must contain {required}")
    if zones[required].isna().any().any():
        raise ValueError("GeoJSON contains null zone attributes")
    if set(zones.LocationID) != set(range(1, 264)):
        raise ValueError("GeoJSON must contain every LocationID from 1 to 263")
    if zones.geometry.isna().any() or zones.geometry.is_empty.any():
        raise ValueError("GeoJSON contains missing or empty geometry")
    if zones.crs is None or zones.crs.to_epsg() != 4326:
        raise ValueError("Existing GeoJSON must use EPSG:4326 for the future map")
    return sorted(set(int(zone) for zone in zones.LocationID))


def download_parquet(path):
    """Download only when absent; publish the file after a complete download."""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".parquet.part")
    print(f"Downloading {URL}", flush=True)
    try:
        with urlopen(URL, timeout=120) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def aggregate(parquet, zone_ids):
    """Read two columns; keep trip-level processing inside in-memory DuckDB."""
    with duckdb.connect() as connection:
        connection.execute("""
            CREATE TEMP TABLE pickups AS
            SELECT TRY_CAST(tpep_pickup_datetime AS TIMESTAMP) AS pickup,
                   TRY_CAST(PULocationID AS DOUBLE) AS zone_id
            FROM read_parquet(?)
        """, [str(parquet)])
        stats = connection.execute("""
            SELECT count(*) AS processed,
                   count(*) FILTER (WHERE pickup IS NULL OR NOT isfinite(pickup)),
                   count(*) FILTER (WHERE zone_id IS NULL OR NOT isfinite(zone_id)
                       OR zone_id NOT BETWEEN 1 AND 263 OR zone_id != trunc(zone_id)),
                   count(*) FILTER (WHERE isfinite(pickup)
                       AND (pickup < ? OR pickup >= ?))
            FROM pickups
        """, [START, END]).fetchone()
        connection.execute("""
            CREATE TEMP VIEW valid_pickups AS
            SELECT pickup, CAST(zone_id AS INTEGER) AS zone_id
            FROM pickups
            WHERE isfinite(pickup) AND pickup >= DATE '2026-05-01'
                AND pickup < DATE '2026-06-01'
                AND isfinite(zone_id) AND zone_id BETWEEN 1 AND 263
                AND zone_id = trunc(zone_id)
        """)
        valid, observed_zones, dates = connection.execute("""
            SELECT count(*), count(DISTINCT zone_id), count(DISTINCT CAST(pickup AS DATE))
            FROM valid_pickups
        """).fetchone()
        if not valid:
            raise ValueError("No valid May 2026 pickups; verify the input file")
        buckets = connection.execute("""
            SELECT zone_id, CAST(isodow(pickup) AS INTEGER) - 1 AS day_of_week,
                   CAST(hour(pickup) AS INTEGER) AS hour_of_day, count(*) AS trips
            FROM valid_pickups
            GROUP BY zone_id, day_of_week, hour_of_day
        """).fetchall()

    # Divide by calendar weekdays, not just dates with nonzero pickups.
    weekday_counts = Counter((START + timedelta(days=i)).weekday()
                             for i in range((END - START).days))
    totals = {(zone, day, hour): count for zone, day, hour, count in buckets}
    demand = {
        day: {
            str(hour): [
                {"zoneId": zone,
                 "predictedCount": totals.get((zone, day_index, hour), 0)
                                   / weekday_counts[day_index]}
                for zone in zone_ids
            ]
            for hour in range(24)
        }
        for day_index, day in enumerate(DAYS)
    }
    print(f"Rows processed: {stats[0]:,}")
    print(f"Valid rows: {valid:,}; removed: {stats[0] - valid:,}")
    print(f"Null/invalid timestamps: {stats[1]:,}")
    print(f"Null/invalid zone IDs: {stats[2]:,}")
    print(f"Timestamps outside May 2026: {stats[3]:,} (rejection reasons can overlap)")
    print(f"Unique taxi zones in valid trips: {observed_zones}; output zones: {len(zone_ids)}")
    print(f"Dates with valid pickups: {dates}/31")
    if dates != 31:
        print("WARNING: Some May dates have no valid pickups; averages assume full-month coverage.")
    print(f"Day/hour combinations: {len(DAYS) * 24}; zone/day/hour entries: {len(zone_ids) * 168:,}")
    values = [row['predictedCount'] for hours in demand.values()
              for rows in hours.values() for row in rows]
    print(f"Minimum demand: {min(values)}; maximum demand: {max(values)}")
    return demand


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    # Reuse the user's existing input; fresh downloads belong in data/raw/.
    existing = DATA / FILENAME
    parser.add_argument("--input", type=Path,
                        default=existing if existing.exists() else DATA / "raw" / FILENAME)
    parser.add_argument("--zones", type=Path, default=DATA / "taxi_zones.geojson")
    parser.add_argument("--download", action="store_true", help="Download May 2026 if input is absent")
    args = parser.parse_args()
    zone_ids = validate_zones(args.zones)
    print(f"Existing taxi_zones.geojson validated (read only): {args.zones}")
    if args.download:
        download_parquet(args.input)
    if not args.input.is_file():
        raise FileNotFoundError(f"Parquet missing: {args.input}. Supply --input or use --download.")
    print(f"Input: {args.input}")
    demand = aggregate(args.input, zone_ids)
    output = DATA / "demand_aggregates.json"
    temporary = output.with_suffix(".json.tmp")
    try:
        temporary.write_text(json.dumps(demand, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Created demand_aggregates.json: {output} ({output.stat().st_size:,} bytes)")
    print("Existing taxi_zones.geojson confirmed; no zone files were modified or regenerated.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, duckdb.Error) as error:
        sys.exit(f"Phase 1 failed: {error}")
