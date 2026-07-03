"""Scenario engine (DECISION_LAYER_SPEC §A1.2) — the honesty architecture.

Every predicted improvement is a range [lo, mid, hi]. Two estimation methods:
  Method A (attribution arithmetic): ΔPM = pm_now × source_share × efficacy_prior
  Method M (model counterfactual):   re-predict with intervention-scaled features
Triangulated where both exist (biomass); confidence is inherited from the hex's
attribution tier (never invented), downgraded one tier on >50% method disagreement.
All efficacy/cost/time priors come from config/interventions.yaml, labelled "planning estimate".
"""
from __future__ import annotations

import logging

import h3
import numpy as np
import pandas as pd

from backend.config import (
    city_config, geo_city_dir, load_interventions, snap_dir,
)
from backend.features.aqi import aqi_subindex
from backend.features.build import FEATURE_COLUMNS
from backend.features.interpolate import _idw, _neighbors

log = logging.getLogger("vayunetra.actions.simulate")

AQI_ACTION_FLOOR = 200
POP_PROXY_PER_SCHOOL = 500  # labelled proxy when no population raster is present
CONF_ORDER = ["low", "medium", "high"]
DISAGREE_FRAC = 0.50

_CTX: dict[str, dict] = {}
_MODEL_CTX: dict[str, dict] = {}


def _downgrade(conf: str) -> str:
    i = CONF_ORDER.index(conf) if conf in CONF_ORDER else 0
    return CONF_ORDER[max(0, i - 1)]


def _aqi(pm25: float, pm10: float | None = None) -> float:
    """AQI = max sub-index of (reduced) pm25 and (unchanged) pm10."""
    subs = [aqi_subindex("pm25", max(pm25, 0.0))]
    if pm10 is not None and not np.isnan(pm10):
        subs.append(aqi_subindex("pm10", max(pm10, 0.0)))
    return float(max(subs))


def _ctx(city: str) -> dict:
    if city in _CTX:
        return _CTX[city]
    sdir = snap_dir(city)
    nowcast = pd.read_parquet(sdir / "hex_nowcast.parquet")
    nowcast["ts_utc"] = pd.to_datetime(nowcast["ts_utc"], utc=True)
    latest = nowcast[nowcast["ts_utc"] == nowcast["ts_utc"].max()].set_index("hex_id")
    attr = pd.read_parquet(sdir / "attribution.parquet")
    attr["ts_utc"] = pd.to_datetime(attr["ts_utc"], utc=True)
    attr_latest = attr[attr["ts_utc"] == attr["ts_utc"].max()].set_index("hex_id")
    forecasts = pd.read_parquet(sdir / "forecasts.parquet") if (sdir / "forecasts.parquet").exists() else pd.DataFrame()
    static = pd.read_parquet(geo_city_dir(city) / "hex_static.parquet").set_index("hex_id")
    _CTX[city] = {"nowcast": nowcast, "latest": latest, "attr": attr_latest,
                  "forecasts": forecasts, "static": static, "ivs": load_interventions()}
    return _CTX[city]


def _model_ctx(city: str) -> dict:
    """Lazy context for Method M (loaded once per city). Uses the small origin.parquet."""
    if city in _MODEL_CTX:
        return _MODEL_CTX[city]
    import lightgbm as lgb

    from backend.models.dataset import model_dir

    mdir = model_dir(city)
    model = lgb.Booster(model_file=str(mdir / "pm25_h24.txt"))
    origin_path = mdir / "origin.parquet"
    if origin_path.exists():
        origin = pd.read_parquet(origin_path)
    else:  # fallback: compute once from the full panel and cache it
        from backend.models.dataset import load_panel
        from backend.models.predict import _latest_origin
        origin = _latest_origin(load_panel(city))
        origin.to_parquet(origin_path, index=False)
    grid = pd.read_parquet(geo_city_dir(city) / "grid.parquet")
    stations = origin[["station_id", "lat", "lng"]].reset_index(drop=True)
    nn_idx, weights, _ = _neighbors(grid, stations, float(city_config(city)["idw_max_radius_km"]))
    hpos = {h: i for i, h in enumerate(grid["hex_id"].to_numpy())}
    _MODEL_CTX[city] = {"model": model, "origin": origin, "grid": grid,
                        "nn_idx": nn_idx, "weights": weights, "hpos": hpos, "delta_cache": {}}
    return _MODEL_CTX[city]


def _method_a(pm_now: float, share: float, eff: list[float]) -> dict:
    """Attribution arithmetic. Returns ΔPM and pm_after for lo/mid/hi."""
    out = {"delta_pm": {}, "pm_after": {}}
    for name, e in zip(("lo", "mid", "hi"), eff):
        d = pm_now * share * e
        out["delta_pm"][name] = d
        out["pm_after"][name] = max(pm_now - d, 0.0)
    return out


def _method_m(city: str, hex_id: str, iv: dict, e_mid: float) -> float | None:
    """Model counterfactual: scale listed features by (1-e_mid), re-predict h24, IDW to hex.

    The full per-hex delta array is computed once per (features, e_mid) and cached,
    so single-hex and city-level scenarios are both fast.
    """
    scale_feats = [f for f in (iv.get("model_counterfactual") or {}).get("feature_scale", {})
                   if f in FEATURE_COLUMNS]
    if not scale_feats:
        return None
    mc = _model_ctx(city)
    if hex_id not in mc["hpos"]:
        return None
    key = (tuple(sorted(scale_feats)), round(e_mid, 4))
    arr = mc["delta_cache"].get(key)
    if arr is None:
        X_base = mc["origin"][FEATURE_COLUMNS].to_numpy(dtype=float)
        X_mod = X_base.copy()
        for f in scale_feats:
            X_mod[:, FEATURE_COLUMNS.index(f)] *= (1.0 - e_mid)
        delta_station = np.clip(mc["model"].predict(X_base) - mc["model"].predict(X_mod), 0, None)
        arr = _idw(delta_station, mc["nn_idx"], mc["weights"])
        mc["delta_cache"][key] = arr
    val = arr[mc["hpos"][hex_id]]
    return float(val) if not np.isnan(val) else None


def _exposure_delta(ctx: dict, hex_id: str, share: float, eff: list[float],
                    tti_lo: float) -> dict:
    """Schools/hospitals affected + person-hours-above-200 relieved, per lo/mid/hi."""
    affected = h3.grid_disk(hex_id, 1)  # hex ∪ 6 neighbours
    static, latest = ctx["static"], ctx["latest"]
    schools = int(sum(int(static.loc[h, "schools_n"]) for h in affected if h in static.index))
    hospitals = int(sum(int(static.loc[h, "hospitals_n"]) for h in affected if h in static.index))

    person_hours = {"lo": 0.0, "mid": 0.0, "hi": 0.0}
    window = max(0.0, 24.0 - tti_lo)
    for h in affected:
        if h not in latest.index or h not in static.index:
            continue
        pm25 = float(latest.loc[h, "pm25"])
        pm10 = float(latest.loc[h].get("pm10", np.nan))
        aqi_now = _aqi(pm25, pm10)
        pop_proxy = int(static.loc[h, "schools_n"]) * POP_PROXY_PER_SCHOOL
        for name, e in zip(("lo", "mid", "hi"), eff):
            aqi_after = _aqi(pm25 * (1 - share * e), pm10)
            if aqi_now > AQI_ACTION_FLOOR and aqi_after <= AQI_ACTION_FLOOR:
                person_hours[name] += pop_proxy * window
    return {"schools_affected": schools, "hospitals_affected": hospitals,
            "person_hours_avoided": {k: round(v) for k, v in person_hours.items()},
            "person_hours_basis": "proxy: schools_n × 500 persons (no population raster loaded)"}


def _forecast_after(ctx: dict, hex_id: str, frac_mid: float) -> dict:
    fc = ctx["forecasts"]
    out = {}
    if fc.empty:
        return out
    hx = fc[fc["hex_id"] == hex_id]
    for h in (24, 48):
        row = hx[hx["horizon_h"] == h]
        if row.empty:
            continue
        pm = float(row.iloc[0]["pm25_pred"])
        pm_after = pm * (1 - frac_mid)
        out[f"h{h}"] = {"aqi_baseline": round(_aqi(pm)), "aqi_after_mid": round(_aqi(pm_after))}
    return out


def simulate(city: str, hex_id: str, intervention_id: str, at: str | None = None) -> dict:
    """Full scenario payload for one hex + intervention (DECISION_LAYER_SPEC §A1.2)."""
    ctx = _ctx(city)
    ivs = ctx["ivs"]
    if intervention_id not in ivs:
        raise KeyError(f"unknown intervention '{intervention_id}'")
    iv = ivs[intervention_id]
    source = iv["targets"]
    eff = iv["efficacy"]

    if hex_id not in ctx["latest"].index:
        raise KeyError(f"hex '{hex_id}' not in nowcast")
    pm_now = float(ctx["latest"].loc[hex_id, "pm25"])
    pm10_now = float(ctx["latest"].loc[hex_id].get("pm10", np.nan))
    share = float(ctx["attr"].loc[hex_id, source]) if hex_id in ctx["attr"].index else 0.0
    confidence = str(ctx["attr"].loc[hex_id, "confidence"]) if hex_id in ctx["attr"].index else "low"

    a = _method_a(pm_now, share, eff)
    assumptions = ["Source shares assumed stable over the forecast horizon.",
                   "Efficacy priors are planning estimates from config/interventions.yaml, not causal guarantees."]
    method = "attribution_only"
    downgraded = False

    delta_pm = dict(a["delta_pm"])
    m = _method_m(city, hex_id, iv, eff[1])
    if m is not None:
        method = "triangulated"
        delta_pm = {"lo": min(a["delta_pm"]["lo"], m), "mid": (a["delta_pm"]["mid"] + m) / 2,
                    "hi": max(a["delta_pm"]["hi"], m)}
        assumptions.append("Method M (model counterfactual) triangulated with Method A (attribution arithmetic).")
        if a["delta_pm"]["mid"] > 0 and abs(m - a["delta_pm"]["mid"]) / a["delta_pm"]["mid"] > DISAGREE_FRAC:
            confidence, downgraded = _downgrade(confidence), True
            assumptions.append(f"Methods disagreed >{int(DISAGREE_FRAC*100)}% → confidence downgraded one tier.")

    pm_after = {k: max(pm_now - delta_pm[k], 0.0) for k in ("lo", "mid", "hi")}
    aqi_now = _aqi(pm_now, pm10_now)
    aqi_after = {k: _aqi(pm_after[k], pm10_now) for k in ("lo", "mid", "hi")}
    delta_aqi = {k: max(aqi_now - aqi_after[k], 0.0) for k in ("lo", "mid", "hi")}

    exposure = _exposure_delta(ctx, hex_id, share, eff, iv["time_to_impact_h"][0])
    forecast_after = _forecast_after(ctx, hex_id, share * eff[1])

    return {
        "city": city, "hex_id": hex_id, "intervention_id": intervention_id, "label": iv["label"],
        "target_source": source, "method": method, "planning_estimate": True,
        "pm_now": round(pm_now, 1), "source_share": round(share, 3),
        "delta_pm": {k: round(v, 1) for k, v in delta_pm.items()},
        "pm_after": {k: round(v, 1) for k, v in pm_after.items()},
        "aqi_now": round(aqi_now), "aqi_after": {k: round(v) for k, v in aqi_after.items()},
        "delta_aqi": {k: round(v) for k, v in delta_aqi.items()},
        "forecast_after": forecast_after, "exposure": exposure,
        "confidence": confidence, "confidence_downgraded": downgraded,
        "department": iv["department"], "legal_basis": iv["legal_basis"],
        "time_to_impact_h": iv["time_to_impact_h"], "cost_tier": iv["cost_tier"],
        "assumptions": assumptions,
    }


_COST_RANK = {"low": 0, "medium": 1, "medium-high (logistics)": 2, "high": 3, "high (economic disruption)": 4}


def rank_interventions(city: str, hex_id: str, at: str | None = None) -> list[dict]:
    """All applicable interventions for a hex, ranked by ΔAQI_mid then cost then time."""
    ctx = _ctx(city)
    out = []
    for iid, iv in ctx["ivs"].items():
        share = float(ctx["attr"].loc[hex_id, iv["targets"]]) if hex_id in ctx["attr"].index else 0.0
        if share <= 0:
            continue
        out.append(simulate(city, hex_id, iid, at))
    out.sort(key=lambda s: (-s["delta_aqi"]["mid"], _COST_RANK.get(s["cost_tier"], 2),
                            s["time_to_impact_h"][0]))
    return out


def simulate_city(city: str, intervention_id: str, at: str | None = None) -> dict:
    """City-level scenario over all AQI>200 hexes where the intervention applies (vectorized).

    Person-hours here are per-hex self-relief (no neighbour double-counting for the aggregate).
    """
    from backend.features.aqi import subindex_series

    ctx = _ctx(city)
    iv = ctx["ivs"][intervention_id]
    source, eff = iv["targets"], iv["efficacy"]
    latest, attr, static = ctx["latest"], ctx["attr"], ctx["static"]
    hot = latest[latest["aqi"] > AQI_ACTION_FLOOR]
    hexes = hot.index.to_numpy()
    share = attr.reindex(hexes)[source].fillna(0.0).to_numpy() if source in attr.columns else np.zeros(len(hexes))
    mask = share > 0
    if not mask.any():
        return {"city": city, "intervention_id": intervention_id, "hexes_affected": 0,
                "delta_aqi_weighted_mean": 0, "person_hours_avoided_total": 0, "top_hexes": []}

    hexes, share = hexes[mask], share[mask]
    pm25 = hot["pm25"].to_numpy()[mask]
    pm10 = hot["pm10"].to_numpy()[mask] if "pm10" in hot.columns else np.full(len(hexes), np.nan)

    delta_mid = pm25 * share * eff[1]
    if iv.get("model_counterfactual"):
        _method_m(city, hexes[0], iv, eff[1])  # warm the cache
        arr = _model_ctx(city)["delta_cache"][(tuple(sorted(
            f for f in iv["model_counterfactual"]["feature_scale"] if f in FEATURE_COLUMNS)), round(eff[1], 4))]
        hpos = _model_ctx(city)["hpos"]
        m_vals = np.array([arr[hpos[h]] if h in hpos else np.nan for h in hexes])
        delta_mid = np.where(np.isnan(m_vals), delta_mid, (delta_mid + m_vals) / 2)

    pm_after = np.clip(pm25 - delta_mid, 0, None)
    pm10_sub = np.nan_to_num(subindex_series("pm10", pm10))
    aqi_now = np.maximum(subindex_series("pm25", pm25), pm10_sub)
    aqi_after = np.maximum(subindex_series("pm25", pm_after), pm10_sub)
    delta_aqi = np.clip(aqi_now - aqi_after, 0, None)

    schools = static.reindex(hexes)["schools_n"].fillna(0).to_numpy()
    hospitals = static.reindex(hexes)["hospitals_n"].fillna(0).to_numpy()
    window = max(0.0, 24.0 - iv["time_to_impact_h"][0])
    relieved = (aqi_now > AQI_ACTION_FLOOR) & (aqi_after <= AQI_ACTION_FLOOR)
    person_hours = schools * POP_PROXY_PER_SCHOOL * window * relieved
    weight = schools + hospitals + 1.0

    df = pd.DataFrame({"hex_id": hexes, "locality": [_locality(ctx, h) for h in hexes],
                       "delta_aqi_mid": np.round(delta_aqi).astype(int),
                       "person_hours_mid": person_hours.astype(int)})
    return {
        "city": city, "intervention_id": intervention_id, "label": iv["label"],
        "hexes_affected": int(len(df)), "planning_estimate": True,
        "delta_aqi_weighted_mean": round(float(np.average(delta_aqi, weights=weight)), 1),
        "person_hours_avoided_total": int(person_hours.sum()),
        "top_hexes": df.sort_values("delta_aqi_mid", ascending=False).head(8).to_dict("records"),
    }


def _locality(ctx: dict, hex_id: str) -> str:
    st = ctx["static"]
    return str(st.loc[hex_id, "locality"]) if hex_id in st.index else hex_id


def clear_cache() -> None:
    _CTX.clear()
    _MODEL_CTX.clear()
