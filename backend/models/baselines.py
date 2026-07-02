"""Forecast baselines (BUILD_SPEC §8.1).

(1) Persistence:  y_hat(t+h) = y(t)
(2) Hour-of-week climatology: mean pm25 at matching (dow, hour) over training
(3) Raw CAMS pm2_5 at the nearest CAMS point (reported where it overlaps).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.geoutils import haversine_km


def persistence(df: pd.DataFrame) -> np.ndarray:
    """y_hat(t+h) = observed pm25 at t (the 'pm25' column of the panel)."""
    return df["pm25"].to_numpy(dtype=float)


def climatology_table(train: pd.DataFrame) -> pd.Series:
    """Mean pm25 keyed by (day-of-week, hour) from the training rows."""
    t = train.dropna(subset=["pm25"]).copy()
    t["_dow"] = t["ts_utc"].dt.dayofweek
    t["_hour"] = t["ts_utc"].dt.hour
    return t.groupby(["_dow", "_hour"])["pm25"].mean()


def climatology_predict(table: pd.Series, df: pd.DataFrame, horizon: int) -> np.ndarray:
    """Climatology forecast for target time t+h using its (dow, hour)."""
    target_ts = df["ts_utc"] + pd.Timedelta(hours=horizon)
    keys = list(zip(target_ts.dt.dayofweek, target_ts.dt.hour))
    overall = float(table.mean()) if len(table) else np.nan
    return np.array([table.get(k, overall) for k in keys], dtype=float)


def cams_predict(df: pd.DataFrame, cams: pd.DataFrame, horizon: int) -> np.ndarray:
    """Raw CAMS pm2_5 at nearest CAMS point for target time t+h (NaN where absent).

    Returns an array aligned to df's row order.
    """
    out = np.full(len(df), np.nan)
    if cams is None or cams.empty or "cams_pm25" not in cams.columns:
        return out
    cams = cams.copy()
    cams["ts_utc"] = pd.to_datetime(cams["ts_utc"], utc=True)
    points = cams[["point_id", "lat", "lng"]].drop_duplicates("point_id")
    lut = {pid: g.set_index("ts_utc")["cams_pm25"] for pid, g in cams.groupby("point_id")}

    dfx = df.reset_index(drop=True)
    target_ts = dfx["ts_utc"] + pd.Timedelta(hours=horizon)
    for _, sdf in dfx.groupby("station_id"):
        pos = sdf.index.to_numpy()  # positional 0..n-1 after reset_index
        slat, slng = sdf.iloc[0]["lat"], sdf.iloc[0]["lng"]
        d = haversine_km(slat, slng, points["lat"].to_numpy(), points["lng"].to_numpy())
        pid = int(points["point_id"].to_numpy()[int(np.argmin(d))])
        series = lut.get(pid)
        if series is None:
            continue
        want = pd.DatetimeIndex(target_ts.to_numpy()[pos], tz="UTC")
        out[pos] = series.reindex(want).to_numpy()
    return out
