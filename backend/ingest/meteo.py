"""Open-Meteo ingestion (BUILD_SPEC §6.2) — keyless.

Five met points per city (bbox corners inset 25% + centroid). ERA5 archive +
4-day forecast merged into met.parquet; CAMS air-quality (past_days=92 +
forecast) into cams.parquet. Wind vectors derived from speed/direction.
"""
from __future__ import annotations

import datetime as dt
import logging

import numpy as np
import pandas as pd

from backend.config import city_config, settings, snap_dir
from backend.degrade import log_degradation
from backend.ingest.http import HttpError, get_json

log = logging.getLogger("vayunetra.ingest.meteo")

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIRQUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

HOURLY_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "surface_pressure",
    "wind_speed_10m",
    "wind_direction_10m",
    "boundary_layer_height",
]
RENAME = {
    "temperature_2m": "temp",
    "relative_humidity_2m": "rh",
    "precipitation": "precip",
    "surface_pressure": "pressure",
    "wind_speed_10m": "wind_speed",
    "wind_direction_10m": "wind_dir",
    "boundary_layer_height": "blh",
}
CAMS_VARS = ["pm2_5", "pm10", "nitrogen_dioxide"]
CAMS_RENAME = {"pm2_5": "cams_pm25", "pm10": "cams_pm10", "nitrogen_dioxide": "cams_no2"}


def met_points(city: str) -> list[tuple[int, float, float]]:
    """Five sampling points: 4 inset corners + centroid."""
    w, s, e, n = city_config(city)["bbox"]
    dx, dy = (e - w) * 0.25, (n - s) * 0.25
    pts = [
        (w + dx, s + dy), (e - dx, s + dy),
        (w + dx, n - dy), (e - dx, n - dy),
        ((w + e) / 2, (s + n) / 2),
    ]
    return [(i, lat, lng) for i, (lng, lat) in enumerate(pts)]


def _hourly_frame(payload: dict, rename: dict[str, str]) -> pd.DataFrame:
    hourly = payload.get("hourly")
    if not hourly or not hourly.get("time"):
        return pd.DataFrame()
    df = pd.DataFrame(hourly)
    df["ts_utc"] = pd.to_datetime(df.pop("time"), utc=True)
    return df.rename(columns=rename)


def _fetch_met(url: str, lat: float, lng: float, extra: dict) -> pd.DataFrame:
    """Fetch met hourly, dropping boundary_layer_height if the API rejects it."""
    params = {"latitude": lat, "longitude": lng, "hourly": ",".join(HOURLY_VARS),
              "timezone": "UTC", **extra}
    try:
        return _hourly_frame(get_json(url, params=params), RENAME)
    except HttpError as exc:
        if "boundary_layer_height" in params["hourly"]:
            log_degradation("open-meteo", f"boundary_layer_height rejected ({exc}); retrying without BLH.")
            params["hourly"] = ",".join(v for v in HOURLY_VARS if v != "boundary_layer_height")
            return _hourly_frame(get_json(url, params=params), RENAME)
        raise


def _add_wind_vectors(df: pd.DataFrame) -> pd.DataFrame:
    """wind_u/v point in the direction the wind is blowing TO (dir is FROM)."""
    if "wind_speed" in df and "wind_dir" in df:
        rad = np.radians(df["wind_dir"].to_numpy())
        df["wind_u"] = -df["wind_speed"].to_numpy() * np.sin(rad)
        df["wind_v"] = -df["wind_speed"].to_numpy() * np.cos(rad)
    return df


def ingest_meteo(city: str, latest: bool = False) -> dict[str, int]:
    """Fetch met and CAMS for a city; persist parquet.

    latest=False: full ERA5 archive + forecast (initial build).
    latest=True:  forecast-only (past_days=7 + 4-day forecast), merged into existing
                  met.parquet — the fast LIVE refresh path (no multi-month archive pull).
    """
    today = dt.date.today().isoformat()
    points = met_points(city)
    met_frames, cams_frames = [], []

    for pid, lat, lng in points:
        if latest:
            met = _fetch_met(FORECAST_URL, lat, lng, {"forecast_days": 4, "past_days": 7})
        else:
            arch = _fetch_met(ARCHIVE_URL, lat, lng,
                              {"start_date": settings.history_start, "end_date": today})
            fcst = _fetch_met(FORECAST_URL, lat, lng, {"forecast_days": 4, "past_days": 7})
            met = pd.concat([arch, fcst], ignore_index=True)
        if not met.empty:
            met = met.drop_duplicates(subset="ts_utc", keep="first")
            met.insert(0, "point_id", pid)
            met["lat"], met["lng"] = lat, lng
            met_frames.append(met)

        cams = _hourly_frame(
            get_json(AIRQUALITY_URL, params={"latitude": lat, "longitude": lng,
                     "hourly": ",".join(CAMS_VARS), "forecast_days": 4,
                     "past_days": 92, "timezone": "UTC"}),
            CAMS_RENAME,
        )
        if not cams.empty:
            cams.insert(0, "point_id", pid)
            cams["lat"], cams["lng"] = lat, lng
            cams_frames.append(cams)

    met_all = _add_wind_vectors(pd.concat(met_frames, ignore_index=True)) if met_frames else pd.DataFrame()
    cams_all = pd.concat(cams_frames, ignore_index=True) if cams_frames else pd.DataFrame()

    sdir = snap_dir(city)
    if latest and (sdir / "met.parquet").exists() and not met_all.empty:
        prev = pd.read_parquet(sdir / "met.parquet")
        prev["ts_utc"] = pd.to_datetime(prev["ts_utc"], utc=True)
        met_all = (pd.concat([prev, met_all], ignore_index=True)
                   .drop_duplicates(subset=["point_id", "ts_utc"], keep="last"))
    met_all.to_parquet(sdir / "met.parquet", index=False)
    cams_all.to_parquet(sdir / "cams.parquet", index=False)
    log.info("[%s] met rows=%d cams rows=%d (points=%d, latest=%s)",
             city, len(met_all), len(cams_all), len(points), latest)
    return {"met_rows": len(met_all), "cams_rows": len(cams_all)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for c in ("delhi", "pune"):
        print(c, ingest_meteo(c))
