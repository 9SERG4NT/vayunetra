"""Station-hour feature panel (BUILD_SPEC §7.1).

Resamples each station-parameter to a strict hourly index (gaps <=3h linearly
interpolated), joins the nearest met point, and builds lag/roll/calendar/fire
features plus the upwind-fire load. Targets are pm25(t+24/48/72). -> features.parquet.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from backend.config import city_config, snap_dir
from backend.geoutils import haversine_km, initial_bearing_deg, wrap_deg

log = logging.getLogger("vayunetra.features.build")

# Festival windows (seasonal emission calendar). 0/1 flag feature.
FESTIVAL_WINDOWS = [("2024-10-30", "2024-11-03"), ("2025-10-18", "2025-10-23")]
HORIZONS = [24, 48, 72]
LAGS = [1, 3, 6, 12, 24, 48]
UPWIND_HALF_ANGLE = 45.0
MET_COLS = ["temp", "rh", "precip", "pressure", "wind_speed", "wind_u", "wind_v", "blh"]

FEATURE_COLUMNS = (
    [f"pm25_lag_{h}" for h in LAGS]
    + ["pm25_roll_mean_24", "pm25_roll_max_24"]
    + ["pm10_lag_1", "pm10_lag_24", "pm10_roll_mean_24"]
    + MET_COLS
    + ["hour_sin", "hour_cos", "dow", "is_weekend", "month", "festival_window"]
    + ["fire_load_upwind_24", "fire_count_radius_24"]
)


def _pivot_station(meas: pd.DataFrame, station_id: int, hours: pd.DatetimeIndex) -> pd.DataFrame:
    """Wide hourly frame (pm25/pm10/no2 columns) for one station, gaps<=3h filled."""
    sub = meas[meas["station_id"] == station_id]
    wide = sub.pivot_table(index="ts_utc", columns="parameter", values="value", aggfunc="mean")
    wide = wide.reindex(hours)
    for col in ("pm25", "pm10", "no2"):
        if col not in wide.columns:
            wide[col] = np.nan
        else:
            wide[col] = wide[col].interpolate(method="linear", limit=3, limit_area="inside")
    return wide[["pm25", "pm10", "no2"]]


def _calendar(hours: pd.DatetimeIndex) -> pd.DataFrame:
    hour = hours.hour.to_numpy()
    festival = np.zeros(len(hours), dtype=int)
    for start, end in FESTIVAL_WINDOWS:
        mask = (hours >= pd.Timestamp(start, tz="UTC")) & (hours <= pd.Timestamp(end + " 23:59", tz="UTC"))
        festival[np.asarray(mask)] = 1
    dow = np.asarray(hours.dayofweek)
    return pd.DataFrame({
        "hour_sin": np.sin(2 * np.pi * hour / 24),
        "hour_cos": np.cos(2 * np.pi * hour / 24),
        "dow": dow,
        "is_weekend": (dow >= 5).astype(int),
        "month": np.asarray(hours.month),
        "festival_window": festival,
    }, index=hours)


def _nearest_met_point(met: pd.DataFrame, lat: float, lng: float) -> int:
    pts = met[["point_id", "lat", "lng"]].drop_duplicates("point_id")
    d = haversine_km(lat, lng, pts["lat"].to_numpy(), pts["lng"].to_numpy())
    return int(pts["point_id"].to_numpy()[int(np.argmin(d))])


def _met_for_point(met: pd.DataFrame, point_id: int, hours: pd.DatetimeIndex) -> pd.DataFrame:
    m = met[met["point_id"] == point_id].set_index("ts_utc").sort_index()
    m = m[~m.index.duplicated(keep="first")].reindex(hours)
    for col in MET_COLS:
        if col not in m.columns:
            m[col] = np.nan
    return m[MET_COLS]


def _fire_features(lat: float, lng: float, radius_km: float, hours: pd.DatetimeIndex,
                   wind_dir: np.ndarray, fires: pd.DataFrame) -> pd.DataFrame:
    """Upwind fire load & count over trailing 24h (BUILD_SPEC §7.1 exact formula)."""
    load = np.zeros(len(hours))
    count = np.zeros(len(hours), dtype=int)
    if fires.empty:
        return pd.DataFrame({"fire_load_upwind_24": load, "fire_count_radius_24": count}, index=hours)

    f_lat, f_lng = fires["lat"].to_numpy(), fires["lng"].to_numpy()
    dist = haversine_km(lat, lng, f_lat, f_lng)
    near = dist <= radius_km
    if not near.any():
        return pd.DataFrame({"fire_load_upwind_24": load, "fire_count_radius_24": count}, index=hours)

    bearing = initial_bearing_deg(lat, lng, f_lat[near], f_lng[near])
    contrib = fires["frp"].to_numpy()[near] / np.maximum(dist[near], 5.0)
    f_ts = fires["ts_utc"].dt.tz_convert("UTC").dt.tz_localize(None).to_numpy()
    f_hour = f_ts[near].astype("datetime64[h]")

    t0 = np.datetime64(hours[0].tz_convert("UTC").tz_localize(None).to_datetime64(), "h")
    n = len(hours)
    base_pos = ((f_hour - t0) / np.timedelta64(1, "h")).astype(int)  # target hour == fire hour
    for offset in range(24):  # fire influences the next 24 hourly targets
        pos = base_pos + offset
        valid = (pos >= 0) & (pos < n)
        p = pos[valid]
        wd = wind_dir[p]
        ang = np.abs(wrap_deg(bearing[valid] - wd))
        up = ~np.isnan(wd) & (ang <= UPWIND_HALF_ANGLE)
        np.add.at(load, p[up], contrib[valid][up])
        np.add.at(count, p[up], 1)
    return pd.DataFrame({"fire_load_upwind_24": load, "fire_count_radius_24": count}, index=hours)


def _station_frame(station: pd.Series, meas: pd.DataFrame, met: pd.DataFrame,
                   fires: pd.DataFrame, radius_km: float, hours: pd.DatetimeIndex) -> pd.DataFrame:
    wide = _pivot_station(meas, station["station_id"], hours)
    met_pt = _met_for_point(met, _nearest_met_point(met, station["lat"], station["lng"]), hours) \
        if not met.empty else pd.DataFrame(np.nan, index=hours, columns=MET_COLS)
    cal = _calendar(hours)
    wind_dir = _wind_dir(met, station, hours)
    fire = _fire_features(station["lat"], station["lng"], radius_km, hours, wind_dir, fires)

    df = pd.concat([wide, met_pt, cal, fire], axis=1)
    for h in LAGS:
        df[f"pm25_lag_{h}"] = df["pm25"].shift(h)
    df["pm25_roll_mean_24"] = df["pm25"].rolling(24, min_periods=6).mean()
    df["pm25_roll_max_24"] = df["pm25"].rolling(24, min_periods=6).max()
    df["pm10_lag_1"] = df["pm10"].shift(1)
    df["pm10_lag_24"] = df["pm10"].shift(24)
    df["pm10_roll_mean_24"] = df["pm10"].rolling(24, min_periods=6).mean()
    for h in HORIZONS:
        df[f"y_{h}"] = df["pm25"].shift(-h)

    df.insert(0, "ts_utc", df.index)
    df.insert(1, "station_id", station["station_id"])
    df.insert(2, "station_name", station["station_name"])
    df.insert(3, "lat", station["lat"])
    df.insert(4, "lng", station["lng"])
    return df.reset_index(drop=True)


def _wind_dir(met: pd.DataFrame, station: pd.Series, hours: pd.DatetimeIndex) -> np.ndarray:
    if met.empty:
        return np.full(len(hours), np.nan)
    pid = _nearest_met_point(met, station["lat"], station["lng"])
    m = met[met["point_id"] == pid].set_index("ts_utc").sort_index()
    m = m[~m.index.duplicated(keep="first")].reindex(hours)
    return m["wind_dir"].to_numpy() if "wind_dir" in m.columns else np.full(len(hours), np.nan)


def build_features(city: str) -> pd.DataFrame:
    """Assemble the station-hour panel for a city; persist features.parquet."""
    sdir = snap_dir(city)
    meas = pd.read_parquet(sdir / "measurements.parquet")
    if meas.empty:
        raise SystemExit(f"HALT: no measurements for {city}; run ingestion first.")
    met = pd.read_parquet(sdir / "met.parquet") if (sdir / "met.parquet").exists() else pd.DataFrame()
    fires = pd.read_parquet(sdir / "fires.parquet") if (sdir / "fires.parquet").exists() else pd.DataFrame()
    stations = pd.read_parquet(sdir / "stations.parquet")
    radius_km = float(city_config(city)["fire_radius_km"])

    meas["ts_utc"] = pd.to_datetime(meas["ts_utc"], utc=True)
    hours = pd.date_range(meas["ts_utc"].min().floor("h"), meas["ts_utc"].max().ceil("h"),
                          freq="h", tz="UTC")

    frames = [_station_frame(st, meas, met, fires, radius_km, hours)
              for _, st in stations.iterrows() if (meas["station_id"] == st["station_id"]).any()]
    panel = pd.concat(frames, ignore_index=True)
    panel.to_parquet(sdir / "features.parquet", index=False)

    nan_met = panel[MET_COLS].isna().mean().mean() * 100
    log.info("[%s] features rows=%d stations=%d met-NaN%%=%.1f", city, len(panel), len(frames), nan_met)
    return panel


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for c in ("delhi", "pune"):
        build_features(c)
