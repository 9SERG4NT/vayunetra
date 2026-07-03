"""Why-engine (DECISION_LAYER_SPEC §A1.3) — deterministic facts only.

Emits <=4 explanatory bullets built ONLY from stored data (nowcast, fires, met,
attribution), plus a ranked-driver conclusion. Numbers are injected, never
generated; optional LLM polish via the existing adapter.
"""
from __future__ import annotations

import json
import logging

import h3
import numpy as np
import pandas as pd

from backend.actions.simulate import _ctx
from backend.config import city_config, snap_dir
from backend.geoutils import haversine_km, initial_bearing_deg

log = logging.getLogger("vayunetra.actions.why")
_WHY_CACHE: dict[str, dict] = {}


def _aux(city: str) -> dict:
    if city in _WHY_CACHE:
        return _WHY_CACHE[city]
    sdir = snap_dir(city)
    fires = pd.read_parquet(sdir / "fires.parquet") if (sdir / "fires.parquet").exists() else pd.DataFrame()
    if not fires.empty:
        fires["ts_utc"] = pd.to_datetime(fires["ts_utc"], utc=True)
    met = pd.read_parquet(sdir / "met.parquet") if (sdir / "met.parquet").exists() else pd.DataFrame()
    if not met.empty:
        met["ts_utc"] = pd.to_datetime(met["ts_utc"], utc=True)
    _WHY_CACHE[city] = {"fires": fires, "met": met}
    return _WHY_CACHE[city]


def _pm_trend(ctx: dict, hex_id: str) -> str | None:
    nc = ctx["nowcast"]
    hx = nc[nc["hex_id"] == hex_id].set_index("ts_utc")["pm25"].sort_index()
    if hx.empty:
        return None
    now_ts = hx.index.max()
    now = float(hx.loc[now_ts])
    ago = hx.reindex([now_ts - pd.Timedelta(hours=24)], method="nearest").iloc[0]
    if np.isnan(ago) or ago == 0:
        return f"PM2.5 now {now:.0f} µg/m³ (no comparable value 24 h ago)."
    pct = (now - ago) / ago * 100
    arrow = "up" if pct >= 0 else "down"
    return f"PM2.5 is {now:.0f} µg/m³, {arrow} {abs(pct):.0f}% vs 24 h ago ({ago:.0f})."


def _fire_trend(city: str, aux: dict, lat: float, lng: float) -> str | None:
    fires = aux["fires"]
    if fires.empty:
        return None
    radius = float(city_config(city)["fire_radius_km"])
    d = haversine_km(lat, lng, fires["lat"].to_numpy(), fires["lng"].to_numpy())
    near = fires[d <= radius].copy()
    if near.empty:
        return "No fire detections within the upwind radius in the last 48 h."
    tmax = near["ts_utc"].max()
    last24 = near[near["ts_utc"] > tmax - pd.Timedelta(hours=24)]
    prev24 = near[(near["ts_utc"] <= tmax - pd.Timedelta(hours=24)) & (near["ts_utc"] > tmax - pd.Timedelta(hours=48))]
    if last24.empty:
        return "No fire detections within the upwind radius in the last 24 h."
    frp = last24["frp"].sum()
    dl = haversine_km(lat, lng, last24["lat"].to_numpy(), last24["lng"].to_numpy())
    bearing = float(initial_bearing_deg(lat, lng, last24["lat"].mean(), last24["lng"].mean()))
    return (f"{len(last24)} upwind fires in last 24 h (ΣFRP {frp:.0f}), vs {len(prev24)} in the prior 24 h; "
            f"mean bearing {bearing:.0f}° at ~{dl.mean():.0f} km.")


def _dispersion(city: str, aux: dict, lat: float, lng: float) -> str | None:
    met = aux["met"]
    if met.empty:
        return None
    pts = met[["point_id", "lat", "lng"]].drop_duplicates("point_id")
    dp = haversine_km(lat, lng, pts["lat"].to_numpy(), pts["lng"].to_numpy())
    pid = int(pts["point_id"].to_numpy()[int(np.argmin(dp))])
    m = met[met["point_id"] == pid].sort_values("ts_utc")
    recent = m[m["ts_utc"] > m["ts_utc"].max() - pd.Timedelta(days=30)]
    if recent.empty:
        return None
    ws_now = float(m.iloc[-1]["wind_speed"]) if "wind_speed" in m.columns else np.nan
    ws_p25 = float(np.nanpercentile(recent["wind_speed"], 25)) if "wind_speed" in recent else np.nan
    parts = [f"wind {ws_now:.1f} m/s"]
    poor = ws_now <= ws_p25
    if "blh" in m.columns and not m["blh"].isna().all():
        blh_now = float(m.iloc[-1]["blh"]); blh_p25 = float(np.nanpercentile(recent["blh"].dropna(), 25))
        parts.append(f"boundary layer {blh_now:.0f} m")
        poor = poor and blh_now <= blh_p25
    flag = " — poor dispersion (both below 30-day 25th pct), pollutants accumulate." if poor else "."
    return "Dispersion: " + ", ".join(parts) + flag


def _driver(ctx: dict, hex_id: str) -> tuple[str | None, str]:
    from backend.models.attribution import SOURCES
    attr = ctx["attr"]
    if hex_id not in attr.index:
        return None, "No attribution available for this hex."
    row = attr.loc[hex_id]
    shares = {s: float(row[s]) for s in SOURCES}
    top = max(shares, key=shares.get)
    ev = json.loads(row["evidence_json"]) if isinstance(row["evidence_json"], str) else {}
    lift = ev.get(f"{top}_lift")
    bullet = None
    if lift is not None or ev.get("station_km") is not None:
        lift_txt = f"wind-sector lift {lift}" if lift is not None else "lift n/a"
        bullet = f"Dominant driver '{top}' — {lift_txt}; nearest station {ev.get('station_km','?')} km away."
    conclusion = f"Ranked driver: {top} ({shares[top]*100:.0f}%, confidence {row['confidence']})."
    return bullet, conclusion


def why(city: str, hex_id: str, at: str | None = None, polish_lang: str | None = None) -> dict:
    """Return {bullets:[...], conclusion, polished}. All facts from stored data."""
    ctx = _ctx(city)
    aux = _aux(city)
    lat, lng = h3.cell_to_latlng(hex_id)
    bullets = [b for b in (
        _pm_trend(ctx, hex_id),
        _fire_trend(city, aux, lat, lng),
        _dispersion(city, aux, lat, lng),
    ) if b]
    driver_bullet, conclusion = _driver(ctx, hex_id)
    if driver_bullet:
        bullets.append(driver_bullet)
    bullets = bullets[:4]

    polished = False
    if polish_lang:
        from backend.advisory.llm import is_enabled, polish
        if is_enabled():
            joined = "\n".join(f"- {b}" for b in bullets) + f"\n{conclusion}"
            out = polish(joined, polish_lang)
            if out and out.strip():
                polished = True
    return {"city": city, "hex_id": hex_id, "bullets": bullets,
            "conclusion": conclusion, "polished": polished}


def clear_cache() -> None:
    _WHY_CACHE.clear()


if __name__ == "__main__":
    import json as _j
    import sys
    print(_j.dumps(why(sys.argv[1], sys.argv[2]), indent=2, ensure_ascii=False))
