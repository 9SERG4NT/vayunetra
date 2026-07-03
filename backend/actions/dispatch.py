"""Dispatch optimizer (DECISION_LAYER_SPEC §A2) — lite operations research, pure numpy.

Assigns inspectors to the highest-impact hotspot+intervention candidates via
deterministic greedy nearest-neighbor insertion under a shift-hours budget, and
compares against a geography-blind naive plan (the demo stat: +X% impact, −Y km).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from backend.actions.simulate import _aqi, _ctx
from backend.config import IST_OFFSET_MINUTES, city_config, load_interventions
from backend.geoutils import haversine_km

log = logging.getLogger("vayunetra.actions.dispatch")

AVG_SPEED_KMPH = 25.0
CIRCUITY = 1.3
DEFAULT_INSPECTION_MIN = 45
INSPECTION_MIN = {"dust_suppression": 20}
TOP_CANDIDATES = 40
IST = pd.Timedelta(minutes=IST_OFFSET_MINUTES)
AQI_FLOOR = 200


def _depot(city: str) -> tuple[float, float]:
    w, s, e, n = city_config(city)["bbox"]
    return (s + n) / 2, (w + e) / 2  # lat, lng


def _candidates(city: str) -> list[dict]:
    """Top hotspots × their best applicable intervention (impact = ΔAQI_mid × exposure)."""
    ctx = _ctx(city)
    ivs = load_interventions()
    latest, attr, static = ctx["latest"], ctx["attr"], ctx["static"]
    hot = latest[latest["aqi"] > AQI_FLOOR].sort_values("aqi", ascending=False).head(TOP_CANDIDATES)

    out = []
    for hex_id, row in hot.iterrows():
        pm, pm10, aqi_now = float(row["pm25"]), float(row.get("pm10", np.nan)), float(row["aqi"])
        best = None
        for iid, iv in ivs.items():
            share = float(attr.loc[hex_id, iv["targets"]]) if hex_id in attr.index else 0.0
            if share <= 0:
                continue
            daqi = max(aqi_now - _aqi(pm * (1 - share * iv["efficacy"][1]), pm10), 0.0)
            if best is None or daqi > best["daqi"]:
                best = {"intervention": iid, "label": iv["label"], "daqi": daqi,
                        "inspection_h": INSPECTION_MIN.get(iid, DEFAULT_INSPECTION_MIN) / 60.0}
        if best is None or best["daqi"] <= 0:
            continue
        schools = int(static.loc[hex_id, "schools_n"]) if hex_id in static.index else 0
        hospitals = int(static.loc[hex_id, "hospitals_n"]) if hex_id in static.index else 0
        expo = schools + hospitals + 1
        out.append({"hex": hex_id, "lat": float(row["lat"]) if "lat" in row else _ctx_latlng(ctx, hex_id)[0],
                    "lng": float(row["lng"]) if "lng" in row else _ctx_latlng(ctx, hex_id)[1],
                    "locality": _locality(ctx, hex_id), "aqi": round(aqi_now), "impact": best["daqi"] * expo,
                    **best})
    return out


def _ctx_latlng(ctx: dict, hex_id: str) -> tuple[float, float]:
    import h3
    return h3.cell_to_latlng(hex_id)


def _locality(ctx: dict, hex_id: str) -> str:
    st = ctx["static"]
    return str(st.loc[hex_id, "locality"]) if hex_id in st.index else hex_id


def _travel_h(coords: list[tuple[float, float]]) -> tuple[float, float]:
    """Total (km, hours) through an ordered list of (lat,lng), with circuity."""
    if len(coords) < 2:
        return 0.0, 0.0
    km = 0.0
    for a, b in zip(coords[:-1], coords[1:]):
        km += float(haversine_km(a[0], a[1], b[0], b[1])) * CIRCUITY
    return km, km / AVG_SPEED_KMPH


def _best_insertion(cand: dict, stops: list[dict], depot: tuple[float, float],
                    used_h: float, shift_h: float) -> tuple[float | None, int]:
    """Min added time (travel + inspection) to insert cand, keeping route ≤ shift. -> (added_h, pos)."""
    base_coords = [depot] + [(s["lat"], s["lng"]) for s in stops]
    _, base_h = _travel_h(base_coords)
    best_added, best_pos = None, -1
    for pos in range(len(stops) + 1):
        new_stops = stops[:pos] + [cand] + stops[pos:]
        coords = [depot] + [(s["lat"], s["lng"]) for s in new_stops]
        _, new_h = _travel_h(coords)
        added = (new_h - base_h) + cand["inspection_h"]
        route_total = new_h + sum(s["inspection_h"] for s in new_stops)
        if route_total <= shift_h and (best_added is None or added < best_added):
            best_added, best_pos = added, pos
    return best_added, best_pos


def _greedy(candidates: list[dict], inspectors: int, depot, shift_h: float) -> list[list[dict]]:
    routes: list[list[dict]] = [[] for _ in range(inspectors)]
    used = [0.0] * inspectors
    remaining = list(candidates)
    while remaining:
        pick = None  # (ratio, cand, insp, pos, added)
        for c in remaining:
            for insp in range(inspectors):
                added, pos = _best_insertion(c, routes[insp], depot, used[insp], shift_h)
                if added is None:
                    continue
                ratio = c["impact"] / max(added, 1e-6)
                if pick is None or ratio > pick[0]:
                    pick = (ratio, c, insp, pos, added)
        if pick is None:
            break
        _, c, insp, pos, added = pick
        routes[insp].insert(pos, c)
        coords = [depot] + [(s["lat"], s["lng"]) for s in routes[insp]]
        _, trav = _travel_h(coords)
        used[insp] = trav + sum(s["inspection_h"] for s in routes[insp])
        remaining.remove(c)
    return routes


def _naive(candidates: list[dict], inspectors: int, depot, shift_h: float) -> list[list[dict]]:
    """Top candidates by AQI alone, round-robin, geography-blind; truncate at shift."""
    by_aqi = sorted(candidates, key=lambda c: c["aqi"], reverse=True)
    buckets: list[list[dict]] = [[] for _ in range(inspectors)]
    for i, c in enumerate(by_aqi):
        buckets[i % inspectors].append(c)
    routes: list[list[dict]] = [[] for _ in range(inspectors)]
    for insp, bucket in enumerate(buckets):
        for c in bucket:  # keep in assigned order until the shift budget is spent
            coords = [depot] + [(s["lat"], s["lng"]) for s in routes[insp] + [c]]
            _, trav = _travel_h(coords)
            if trav + sum(s["inspection_h"] for s in routes[insp] + [c]) <= shift_h:
                routes[insp].append(c)
    return routes


def _summarize(routes: list[list[dict]], depot) -> tuple[float, float, int]:
    impact = sum(s["impact"] for r in routes for s in r)
    km = sum(_travel_h([depot] + [(s["lat"], s["lng"]) for s in r])[0] for r in routes)
    sites = sum(len(r) for r in routes)
    return impact, km, sites


def dispatch(city: str, inspectors: int = 10, shift_hours: float = 8.0) -> dict:
    inspectors = int(np.clip(inspectors, 1, 50))
    depot = _depot(city)
    cands = _candidates(city)
    opt = _greedy(cands, inspectors, depot, shift_hours)
    naive = _naive(cands, inspectors, depot, shift_hours)

    opt_impact, opt_km, opt_sites = _summarize(opt, depot)
    nv_impact, nv_km, nv_sites = _summarize(naive, depot)
    now = pd.Timestamp.now(tz="UTC")

    plan = []
    for i, route in enumerate(opt):
        coords, t_h, stops = [depot], 0.0, []
        for s in route:
            km, th = _travel_h([coords[-1], (s["lat"], s["lng"])])
            t_h += th
            eta = (now + pd.Timedelta(hours=t_h) + IST).strftime("%H:%M IST")
            t_h += s["inspection_h"]
            coords.append((s["lat"], s["lng"]))
            stops.append({"hex": s["hex"], "locality": s["locality"], "intervention": s["label"],
                          "eta_ist": eta, "impact": round(s["impact"], 1), "aqi": s["aqi"],
                          "lat": s["lat"], "lng": s["lng"]})
        route_km, _ = _travel_h(coords)
        plan.append({"inspector_id": i + 1, "stops": stops, "route_km": round(route_km, 1),
                     "utilisation": round(min(t_h / shift_hours, 1.0), 2)})

    gain = (opt_impact - nv_impact) / nv_impact * 100 if nv_impact > 0 else 0.0
    return {
        "city": city, "inspectors": inspectors, "shift_hours": shift_hours,
        "depot": {"lat": depot[0], "lng": depot[1]}, "plan": plan,
        "totals": {"impact_covered": round(opt_impact, 1), "sites_covered": opt_sites,
                   "travel_km": round(opt_km, 1)},
        "baseline_comparison": {
            "naive_impact_covered": round(nv_impact, 1), "naive_sites": nv_sites,
            "naive_travel_km": round(nv_km, 1), "impact_gain_pct": round(gain, 1),
            "travel_km_saved": round(nv_km - opt_km, 1),
        },
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(dispatch("delhi", 10, 8), indent=2, default=str)[:1200])
