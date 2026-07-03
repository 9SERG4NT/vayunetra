"""Forecast inference (BUILD_SPEC §8.2).

Predicts pm25 at t+24/48/72 from each station's latest feature row, optionally
blends CAMS (bias-corrected) where available, then IDW-interpolates station
predictions onto H3 hexes with empirical prediction intervals. -> forecasts.parquet
"""
from __future__ import annotations

import json
import logging

import lightgbm as lgb
import numpy as np
import pandas as pd

from backend.config import city_config, geo_city_dir, snap_dir
from backend.features.aqi import aqi_from_pollutants
from backend.features.build import FEATURE_COLUMNS, HORIZONS
from backend.features.interpolate import _idw, _neighbors
from backend.geoutils import haversine_km
from backend.models.dataset import load_panel, model_dir

log = logging.getLogger("vayunetra.models.predict")

CAMS_BLEND_ML = 0.7
CAMS_BLEND_CAMS = 0.3
BIAS_WINDOW_DAYS = 92


def _load_models(city: str) -> dict[int, lgb.Booster]:
    mdir = model_dir(city)
    models = {}
    for h in HORIZONS:
        path = mdir / f"pm25_h{h}.txt"
        if path.exists():
            models[h] = lgb.Booster(model_file=str(path))
    return models


def _residuals(city: str) -> dict:
    path = model_dir(city) / "residuals.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _latest_origin(panel: pd.DataFrame) -> pd.DataFrame:
    """Latest feature row per station (the forecast origin t)."""
    idx = panel.groupby("station_id")["ts_utc"].idxmax()
    return panel.loc[idx].reset_index(drop=True)


def _station_cams(city: str, stations: pd.DataFrame) -> dict[int, tuple[pd.Series, float]]:
    """Per station: (nearest-point cams_pm25 series, bias = mean(obs - cams) over 92d)."""
    sdir = snap_dir(city)
    if not (sdir / "cams.parquet").exists():
        return {}
    cams = pd.read_parquet(sdir / "cams.parquet")
    if cams.empty or "cams_pm25" not in cams.columns:
        return {}
    cams["ts_utc"] = pd.to_datetime(cams["ts_utc"], utc=True)
    pts = cams[["point_id", "lat", "lng"]].drop_duplicates("point_id")
    series_by_pt = {pid: g.set_index("ts_utc")["cams_pm25"].sort_index() for pid, g in cams.groupby("point_id")}

    meas = pd.read_parquet(sdir / "measurements.parquet")
    meas["ts_utc"] = pd.to_datetime(meas["ts_utc"], utc=True)
    pm25 = meas[meas["parameter"] == "pm25"]
    cutoff = cams["ts_utc"].max() - pd.Timedelta(days=BIAS_WINDOW_DAYS)

    out = {}
    for _, st in stations.iterrows():
        d = haversine_km(st["lat"], st["lng"], pts["lat"].to_numpy(), pts["lng"].to_numpy())
        pid = int(pts["point_id"].to_numpy()[int(np.argmin(d))])
        cser = series_by_pt[pid]
        obs = pm25[pm25["station_id"] == st["station_id"]].set_index("ts_utc")["value"]
        joined = pd.concat([obs.rename("obs"), cser.rename("cams")], axis=1).dropna()
        joined = joined[joined.index >= cutoff]
        bias = float((joined["obs"] - joined["cams"]).mean()) if len(joined) else 0.0
        out[int(st["station_id"])] = (cser, bias)
    return out


def _blend(ml: float, cams_series: pd.Series, bias: float, target_ts: pd.Timestamp) -> float:
    """0.7*ML + 0.3*(CAMS_forecast + bias) if CAMS available at target, else ML."""
    if cams_series is None or target_ts not in cams_series.index:
        return ml
    cams_val = float(cams_series.loc[target_ts]) + bias
    return CAMS_BLEND_ML * ml + CAMS_BLEND_CAMS * cams_val


def predict_city(city: str) -> dict:
    panel = load_panel(city)
    models = _load_models(city)
    if not models:
        raise SystemExit(f"HALT: no trained models for {city}; run `make train` first.")
    residuals = _residuals(city)
    grid = pd.read_parquet(geo_city_dir(city) / "grid.parquet")

    origin = _latest_origin(panel)
    # Persist the tiny origin frame so the Decision Layer's Method-M avoids reloading the full panel.
    origin.to_parquet(model_dir(city) / "origin.parquet", index=False)
    stations = origin[["station_id", "lat", "lng"]].reset_index(drop=True)
    cams_lut = _station_cams(city, stations)
    nn_idx, weights, _ = _neighbors(grid, stations, float(city_config(city)["idw_max_radius_km"]))

    frames = []
    for h in HORIZONS:
        if h not in models:
            continue
        X = origin[FEATURE_COLUMNS]
        ml = models[h].predict(X)
        target_ts = origin["ts_utc"] + pd.Timedelta(hours=h)
        vals = np.array([
            _blend(ml[i], *cams_lut.get(int(origin.iloc[i]["station_id"]), (None, 0.0)), target_ts.iloc[i])
            for i in range(len(origin))
        ])
        hex_pred = np.clip(_idw(vals, nn_idx, weights), 0, None)
        q = residuals.get(str(h), {"q10": -20.0, "q90": 20.0})
        frame = pd.DataFrame({
            "hex_id": grid["hex_id"].to_numpy(), "horizon_h": h,
            "target_ts": target_ts.iloc[0], "pm25_pred": hex_pred,
            "pi_low": np.clip(hex_pred + q["q10"], 0, None),
            "pi_high": hex_pred + q["q90"],
        })
        aqi = aqi_from_pollutants(frame[["pm25_pred"]].rename(columns={"pm25_pred": "pm25"}))
        frame["aqi_pred"] = aqi["aqi"].to_numpy()
        frames.append(frame.dropna(subset=["pm25_pred"]))

    forecasts = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    forecasts.to_parquet(snap_dir(city) / "forecasts.parquet", index=False)
    log.info("[%s] forecasts rows=%d horizons=%s cams_blend=%s",
             city, len(forecasts), sorted(models), bool(cams_lut))
    return {"rows": len(forecasts)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for c in ("delhi", "pune"):
        print(c, predict_city(c))
