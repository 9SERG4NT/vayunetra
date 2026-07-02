"""GRAP staging (BUILD_SPEC §8.4) — Delhi only.

Maps AQI to a Graded Response Action Plan stage and predicts the stage from the
max hex-median AQI forecast over the next 48 h.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from backend.config import city_config, load_grap, snap_dir

log = logging.getLogger("vayunetra.actions.grap")


def stage_for_aqi(aqi: float | None) -> int:
    """Return GRAP stage (1-4) for an AQI, or 0 when below the Stage-I threshold."""
    if aqi is None or (isinstance(aqi, float) and np.isnan(aqi)):
        return 0
    for s in load_grap()["stages"]:
        if s["aqi_lo"] <= aqi <= s["aqi_hi"]:
            return int(s["stage"])
    return 0


def _stage_block(stage: int) -> dict:
    if stage == 0:
        return {"stage": 0, "label": "Below Stage I (AQI ≤ 200)", "actions": []}
    for s in load_grap()["stages"]:
        if int(s["stage"]) == stage:
            return {"stage": stage, "label": s["label"], "actions": s["actions"]}
    return {"stage": stage, "label": f"Stage {stage}", "actions": []}


def _median_aqi_latest(city: str) -> float:
    path = snap_dir(city) / "hex_nowcast.parquet"
    if not path.exists():
        return float("nan")
    nc = pd.read_parquet(path)
    if nc.empty:
        return float("nan")
    nc["ts_utc"] = pd.to_datetime(nc["ts_utc"], utc=True)
    latest = nc[nc["ts_utc"] == nc["ts_utc"].max()]
    return float(latest["aqi"].median())


def _predicted_stage_48h(city: str) -> int:
    path = snap_dir(city) / "forecasts.parquet"
    if not path.exists():
        return 0
    fc = pd.read_parquet(path)
    fc = fc[fc["horizon_h"] <= 48]
    if fc.empty:
        return 0
    per_h = fc.groupby("horizon_h")["aqi_pred"].median()
    return stage_for_aqi(float(per_h.max()))


def grap_status(city: str) -> dict | None:
    """Return GRAP status for a GRAP city, else None."""
    if not city_config(city).get("grap"):
        return None
    current = stage_for_aqi(_median_aqi_latest(city))
    predicted = _predicted_stage_48h(city)
    headline = max(current, predicted)
    block = _stage_block(headline)
    return {
        "city": city,
        "current_stage": current,
        "predicted_stage_48h": predicted,
        "headline_stage": headline,
        "label": block["label"],
        "actions": block["actions"],
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for c in ("delhi", "pune"):
        print(c, grap_status(c))
