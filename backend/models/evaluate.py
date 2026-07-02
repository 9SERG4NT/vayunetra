"""Rolling-origin backtest vs baselines (BUILD_SPEC §8.2).

Metrics per horizon: RMSE, MAE, and skill = 1 - RMSE_model/RMSE_persistence, for
model / persistence / climatology / CAMS-where-available. Writes metrics.json and
docs/metrics.md, and stores empirical residual quantiles (10/90%) for prediction
intervals. If 24h skill < 0.25, writes docs/DIAGNOSIS.md and continues (§1.2).
"""
from __future__ import annotations

import datetime as dt
import json
import logging

import numpy as np
import pandas as pd

from backend.config import DOCS_DIR, snap_dir
from backend.degrade import log_diagnosis
from backend.models import baselines
from backend.models.dataset import HORIZONS, load_panel, model_dir, rolling_folds, xy
from backend.models.train import fit_booster

log = logging.getLogger("vayunetra.models.evaluate")
SKILL_TARGET_24H = 0.25


def _metrics(y: np.ndarray, pred: np.ndarray) -> dict:
    mask = ~np.isnan(y) & ~np.isnan(pred)
    if mask.sum() == 0:
        return {"rmse": None, "mae": None, "n": 0}
    err = pred[mask] - y[mask]
    return {"rmse": float(np.sqrt(np.mean(err ** 2))), "mae": float(np.mean(np.abs(err))),
            "n": int(mask.sum())}


def _skill(model_rmse, persist_rmse) -> float | None:
    if not model_rmse or not persist_rmse:
        return None
    return round(1 - model_rmse / persist_rmse, 3)


def backtest_horizon(city: str, panel: pd.DataFrame, cams: pd.DataFrame, horizon: int):
    """Run the 4-fold rolling backtest for one horizon. Returns (metrics, residuals)."""
    acc = {k: ([], []) for k in ("model", "persistence", "climatology", "cams")}  # (y, pred)
    residuals: list[float] = []
    for _, train, test in rolling_folds(panel):
        X_te, y_te, test_rows = xy(test, horizon)
        if len(X_te) < 20:
            continue
        model = fit_booster(train, horizon)
        preds = {
            "model": model.predict(X_te),
            "persistence": baselines.persistence(test_rows),
            "climatology": baselines.climatology_predict(
                baselines.climatology_table(train), test_rows, horizon),
            "cams": baselines.cams_predict(test_rows, cams, horizon),
        }
        y = y_te.to_numpy(dtype=float)
        for k, p in preds.items():
            acc[k][0].append(y)
            acc[k][1].append(np.asarray(p, dtype=float))
        residuals.extend((y - preds["model"]).tolist())

    out = {}
    for k, (ys, ps) in acc.items():
        if ys:
            out[k] = _metrics(np.concatenate(ys), np.concatenate(ps))
        else:
            out[k] = {"rmse": None, "mae": None, "n": 0}
    out["skill_vs_persistence"] = _skill(out["model"]["rmse"], out["persistence"]["rmse"])
    return out, residuals


def _coverage(city: str) -> dict:
    sdir = snap_dir(city)
    stations = pd.read_parquet(sdir / "stations.parquet")
    meas = pd.read_parquet(sdir / "measurements.parquet")
    pm25 = meas[meas["parameter"] == "pm25"]
    return {"stations": int(len(stations)),
            "reference_stations": int(stations.get("is_reference", pd.Series(dtype=bool)).sum()),
            "measurement_rows": int(len(meas)),
            "pm25_rows": int(len(pm25)),
            "date_range": [str(meas["ts_utc"].min()), str(meas["ts_utc"].max())]}


def evaluate_city(city: str) -> dict:
    panel = load_panel(city)
    sdir = snap_dir(city)
    cams = pd.read_parquet(sdir / "cams.parquet") if (sdir / "cams.parquet").exists() else pd.DataFrame()

    horizons, residual_q = {}, {}
    for h in HORIZONS:
        metrics, residuals = backtest_horizon(city, panel, cams, h)
        horizons[str(h)] = metrics
        if residuals:
            residual_q[str(h)] = {"q10": float(np.nanpercentile(residuals, 10)),
                                  "q90": float(np.nanpercentile(residuals, 90))}

    report = {"city": city, "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "horizons": horizons, "coverage": _coverage(city)}
    (sdir / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (model_dir(city) / "residuals.json").write_text(json.dumps(residual_q, indent=2), encoding="utf-8")

    skill24 = horizons.get("24", {}).get("skill_vs_persistence")
    if skill24 is not None and skill24 < SKILL_TARGET_24H:
        log_diagnosis(f"{city}: 24h skill {skill24} < target {SKILL_TARGET_24H}",
                      "Model did not clear the persistence-skill target. Reported honestly; "
                      "the app still runs. Likely causes: short history window, sparse coverage, "
                      "or dominant persistence in pm25 autocorrelation.")
    log.info("[%s] eval done; 24h skill=%s", city, skill24)
    return report


def evaluate_all(cities: list[str]) -> None:
    reports = [evaluate_city(c) for c in cities]
    _write_metrics_md(reports)


def _fmt(m: dict, key: str) -> str:
    v = m.get(key)
    return "—" if v is None else f"{v:.1f}"


def _write_metrics_md(reports: list[dict]) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    lines = ["# Forecast metrics — VayuNetra", "",
             "Rolling-origin backtest: last 8 weeks as four sequential 2-week folds; "
             "train strictly before each fold. RMSE/MAE in µg/m³ (pm25). "
             "Skill = 1 − RMSE_model/RMSE_persistence.", ""]
    for r in reports:
        lines += [f"## {r['city']}", "",
                  "| Horizon | Model RMSE | Persistence RMSE | Climatology RMSE | CAMS RMSE | Model MAE | Skill vs persistence |",
                  "|---|---|---|---|---|---|---|"]
        for h in ("24", "48", "72"):
            m = r["horizons"].get(h, {})
            skill = m.get("skill_vs_persistence")
            lines.append(
                f"| {h}h | {_fmt(m.get('model',{}),'rmse')} | {_fmt(m.get('persistence',{}),'rmse')} "
                f"| {_fmt(m.get('climatology',{}),'rmse')} | {_fmt(m.get('cams',{}),'rmse')} "
                f"| {_fmt(m.get('model',{}),'mae')} | {'—' if skill is None else f'{skill:+.3f}'} |")
        cov = r["coverage"]
        lines += ["", f"Coverage: {cov['stations']} stations "
                  f"({cov['reference_stations']} reference), {cov['pm25_rows']} pm25 rows, "
                  f"range {cov['date_range'][0]} → {cov['date_range'][1]}.", ""]
    lines += ["> Disclosure: hourly AQI proxy computed on hourly concentrations "
              "(official CPCB NAQI uses 24-h averages).", ""]
    (DOCS_DIR / "metrics.md").write_text("\n".join(lines), encoding="utf-8")
    log.info("wrote docs/metrics.md")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    evaluate_all(["delhi", "pune"])
