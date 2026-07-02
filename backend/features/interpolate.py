"""Hex spatial nowcast via IDW (BUILD_SPEC §7.2).

For each needed timestamp, inverse-distance-weight (power 2, k=5 nearest, bounded
radius) station pm25/pm10 onto H3 hex centroids; flag low_coverage where the
nearest station is >8 km. Only materializes UI-needed timestamps to keep files small.
-> hex_nowcast.parquet
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from backend.config import city_config, geo_city_dir, snap_dir
from backend.features.aqi import aqi_from_pollutants
from backend.geoutils import haversine_km

log = logging.getLogger("vayunetra.features.interpolate")

IDW_POWER = 2
IDW_K = 5
LOW_COVERAGE_KM = 8.0
NOWCAST_DAYS = 14
MIN_DIST_KM = 0.1


def _neighbors(hex_df: pd.DataFrame, stations: pd.DataFrame, max_radius_km: float):
    """Precompute k nearest stations per hex (fixed geometry). Returns idx, weights, nearest_km."""
    hlat, hlng = hex_df["lat"].to_numpy(), hex_df["lng"].to_numpy()
    slat, slng = stations["lat"].to_numpy(), stations["lng"].to_numpy()
    # distance matrix (n_hex, n_station)
    dist = haversine_km(hlat[:, None], hlng[:, None], slat[None, :], slng[None, :])
    nearest_km = dist.min(axis=1)
    order = np.argsort(dist, axis=1)[:, :IDW_K]
    nn_dist = np.take_along_axis(dist, order, axis=1)
    within = nn_dist <= max_radius_km
    w = np.where(within, 1.0 / np.maximum(nn_dist, MIN_DIST_KM) ** IDW_POWER, 0.0)
    return order, w, nearest_km


def _station_matrix(meas: pd.DataFrame, param: str, stations: pd.DataFrame,
                    timestamps: pd.DatetimeIndex) -> np.ndarray:
    """(n_ts, n_station) value matrix for a parameter, aligned to station order."""
    sub = meas[meas["parameter"] == param]
    wide = sub.pivot_table(index="ts_utc", columns="station_id", values="value", aggfunc="mean")
    wide = wide.reindex(index=timestamps, columns=stations["station_id"].to_numpy())
    return wide.to_numpy(dtype=float)


def _idw(values: np.ndarray, nn_idx: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """IDW for one timestamp. values:(n_station,) -> (n_hex,)."""
    gathered = values[nn_idx]                      # (n_hex, k)
    valid = ~np.isnan(gathered)
    w = np.where(valid, weights, 0.0)
    wsum = w.sum(axis=1)
    num = np.nansum(np.where(valid, w * gathered, 0.0), axis=1)
    out = np.full(len(nn_idx), np.nan)
    nz = wsum > 0
    out[nz] = num[nz] / wsum[nz]
    return out


def _timestamps_needed(city: str, meas: pd.DataFrame) -> pd.DatetimeIndex:
    tmax = meas["ts_utc"].max().floor("h")
    stamps = pd.date_range(tmax - pd.Timedelta(days=NOWCAST_DAYS), tmax, freq="h", tz="UTC")
    tmin, tmax_all = meas["ts_utc"].min(), meas["ts_utc"].max()
    for preset in city_config(city).get("replay_presets", []):
        start = pd.Timestamp(preset["start"], tz="UTC")
        end = pd.Timestamp(preset["end"] + " 23:00", tz="UTC")
        if start >= tmin and end <= tmax_all:
            stamps = stamps.union(pd.date_range(start, end, freq="h", tz="UTC"))
    return stamps


def build_hex_nowcast(city: str) -> pd.DataFrame:
    """Materialize the hex nowcast for a city; persist hex_nowcast.parquet."""
    sdir = snap_dir(city)
    grid = pd.read_parquet(geo_city_dir(city) / "grid.parquet")
    meas = pd.read_parquet(sdir / "measurements.parquet")
    meas["ts_utc"] = pd.to_datetime(meas["ts_utc"], utc=True)
    stations = (meas[["station_id", "lat", "lng"]].drop_duplicates("station_id")
                .reset_index(drop=True))

    max_radius = float(city_config(city)["idw_max_radius_km"])
    nn_idx, weights, nearest_km = _neighbors(grid, stations, max_radius)
    low_cov = nearest_km > LOW_COVERAGE_KM
    timestamps = _timestamps_needed(city, meas)

    pm25_m = _station_matrix(meas, "pm25", stations, timestamps)
    pm10_m = _station_matrix(meas, "pm10", stations, timestamps)

    rows = []
    for i, ts in enumerate(timestamps):
        pm25 = _idw(pm25_m[i], nn_idx, weights)
        pm10 = _idw(pm10_m[i], nn_idx, weights)
        if np.isnan(pm25).all():
            continue
        frame = pd.DataFrame({"ts_utc": ts, "hex_id": grid["hex_id"].to_numpy(),
                              "pm25": pm25, "pm10": pm10, "low_coverage": low_cov})
        rows.append(frame)

    nowcast = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    if not nowcast.empty:
        aqi = aqi_from_pollutants(nowcast[["pm25", "pm10"]])
        nowcast["aqi"] = aqi["aqi"].to_numpy()
        nowcast["category"] = aqi["category"].to_numpy()
        nowcast = nowcast.dropna(subset=["pm25"])
    nowcast.to_parquet(sdir / "hex_nowcast.parquet", index=False)

    latest = nowcast[nowcast["ts_utc"] == timestamps[-1]] if not nowcast.empty else nowcast
    log.info("[%s] hex_nowcast rows=%d timestamps=%d latest_hexes=%d low_cov_hexes=%d",
             city, len(nowcast), len(timestamps), len(latest), int(low_cov.sum()))
    return nowcast


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for c in ("delhi", "pune"):
        build_hex_nowcast(c)
