"""Enforcement action ranker (BUILD_SPEC §9.1).

score = share × severity × persistence × exposure × actionability, computed for
every hex with current AQI>200 and each source with share≥0.15. Top 10 per city
-> actions.json (the enforcement queue).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from backend.actions.grap import grap_status
from backend.config import geo_city_dir, load_interventions, snap_dir
from backend.models.attribution import SOURCES


def _source_dept_map() -> dict[str, dict]:
    """source -> {department, legal_basis, intervention_id} via highest-efficacy intervention."""
    best: dict[str, dict] = {}
    for iid, iv in load_interventions().items():
        src = iv["targets"]
        if src not in best or iv["efficacy"][1] > best[src]["_eff"]:
            best[src] = {"department": iv["department"], "legal_basis": iv["legal_basis"],
                         "intervention_id": iid, "_eff": iv["efficacy"][1]}
    return best

log = logging.getLogger("vayunetra.actions.ranker")

AQI_ACTION_FLOOR = 200
MIN_SHARE = 0.15
TOP_N = 10
ACTIONABILITY = {"construction_dust": 0.9, "biomass": 0.85, "industry": 0.8,
                 "traffic": 0.6, "background": 0.15}
ACTION_TEXT = {
    "construction_dust": "Deploy dust-control team: enforce C&D site covering, water sprinkling and anti-smog guns; halt non-compliant sites.",
    "biomass": "Dispatch field team to trace and stop open agricultural/waste burning in the upwind sector; coordinate with rural enforcement.",
    "industry": "Inspect nearby industrial units for stack/fuel compliance; verify emission controls and issue notices to violators.",
    "traffic": "Intensify corridor decongestion, PUC enforcement and roadside dust suppression during peak hours.",
    "background": "Area-wide sustained controls; limited single-point action — maintain monitoring and existing measures.",
}


def _latest_attribution(city: str) -> pd.DataFrame:
    attr = pd.read_parquet(snap_dir(city) / "attribution.parquet")
    attr["ts_utc"] = pd.to_datetime(attr["ts_utc"], utc=True)
    return attr[attr["ts_utc"] == attr["ts_utc"].max()].copy()


def _persistence(nowcast: pd.DataFrame) -> pd.Series:
    """Fraction of trailing 12 h with hex AQI > 200, per hex."""
    nowcast["ts_utc"] = pd.to_datetime(nowcast["ts_utc"], utc=True)
    last12 = sorted(nowcast["ts_utc"].unique())[-12:]
    window = nowcast[nowcast["ts_utc"].isin(last12)]
    return window.assign(hot=window["aqi"] > AQI_ACTION_FLOOR).groupby("hex_id")["hot"].mean()


def _exposure(static: pd.DataFrame) -> pd.Series:
    raw = (static["schools_n"] + static["hospitals_n"]).astype(float)
    lo, hi = raw.min(), raw.max()
    norm = (raw - lo) / (hi - lo) if hi > lo else raw * 0
    return pd.Series(0.5 + 0.5 * norm.to_numpy(), index=static["hex_id"])


def rank_city(city: str) -> dict:
    attr = _latest_attribution(city)
    nowcast = pd.read_parquet(snap_dir(city) / "hex_nowcast.parquet")
    static = pd.read_parquet(geo_city_dir(city) / "hex_static.parquet")

    latest_now = nowcast.copy()
    latest_now["ts_utc"] = pd.to_datetime(latest_now["ts_utc"], utc=True)
    now = latest_now[latest_now["ts_utc"] == latest_now["ts_utc"].max()].set_index("hex_id")
    persist = _persistence(latest_now)
    exposure = _exposure(static)
    locality = static.set_index("hex_id")["locality"]
    grap = grap_status(city)

    candidates = []
    for _, row in attr.iterrows():
        hx = row["hex_id"]
        if hx not in now.index:
            continue
        aqi = float(now.loc[hx, "aqi"])
        if aqi <= AQI_ACTION_FLOOR:
            continue
        sev = float(np.clip((aqi - 100) / 400, 0, 1))
        pst = 0.2 + 0.8 * float(persist.get(hx, 0.0))
        exp = float(exposure.get(hx, 0.5))
        for src in SOURCES:
            share = float(row[src])
            if share < MIN_SHARE:
                continue
            score = share * sev * pst * exp * ACTIONABILITY[src]
            candidates.append({
                "hex": hx, "locality": str(locality.get(hx, "")), "source": src,
                "share": round(share, 3), "confidence": row["confidence"], "aqi": round(aqi, 0),
                "score": round(score, 4), "severity": round(sev, 3), "persistence": round(pst, 3),
                "exposure": round(exp, 3),
            })

    # Rank by score, but keep the queue geographically diverse: one row per hotspot
    # AREA (its highest-scoring cell/source). Without this the top-N collapses onto
    # adjacent cells of the single worst cluster (all showing the same saturated AQI),
    # which is useless for dispatching inspectors to distinct locations.
    ordered = sorted(candidates, key=lambda c: c["score"], reverse=True)
    ranked, seen_localities = [], set()
    for c in ordered:
        loc = c["locality"] or c["hex"]
        if loc in seen_localities:
            continue
        seen_localities.add(loc)
        ranked.append(c)
        if len(ranked) >= TOP_N:
            break
    created = datetime.now(timezone.utc).isoformat()
    dept_map = _source_dept_map()
    for i, c in enumerate(ranked, start=1):
        c["id"] = str(i)
        c["recommended_action"] = ACTION_TEXT[c["source"]]
        dept = dept_map.get(c["source"], {})
        c["department"] = dept.get("department")
        c["legal_basis"] = dept.get("legal_basis")
        c["intervention_id"] = dept.get("intervention_id")
        if grap and grap["headline_stage"] > 0:
            c["grap_context"] = f"{grap['label']} (predicted 48h stage {grap['predicted_stage_48h']})"
        c["created_ts"] = created

    payload = {"city": city, "created_ts": created, "actions": ranked}
    (snap_dir(city) / "actions.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log.info("[%s] ranked %d candidates -> top %d", city, len(candidates), len(ranked))
    return {"candidates": len(candidates), "ranked": len(ranked)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for c in ("delhi", "pune"):
        print(c, rank_city(c))
