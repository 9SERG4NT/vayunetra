"""API routes (BUILD_SPEC §11). All reads come from local offline snapshots."""
from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response

from backend.app import deps
from backend.app.schemas import (
    ActionsResponse, AttributionResponse, City, ForecastResponse, GridResponse,
    OrderRequest, SimulateRequest, TimelineResponse,
)
from backend.config import city_config, load_cities, load_interventions

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _nowcast(city: str) -> pd.DataFrame:
    df = deps.read_parquet(deps.snap_file(city, "hex_nowcast.parquet"))
    if not df.empty:
        df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True)
    return df


def _data_range(city: str):
    nc = _nowcast(city)
    if nc.empty:
        return None, None
    return nc["ts_utc"].min(), nc["ts_utc"].max()


def _filter_presets(city: str) -> list[dict]:
    lo, hi = _data_range(city)
    presets = city_config(city).get("replay_presets", [])
    if lo is None:
        return []
    out = []
    for p in presets:
        start, end = pd.Timestamp(p["start"], tz="UTC"), pd.Timestamp(p["end"] + " 23:00", tz="UTC")
        if start >= lo and end <= hi:
            out.append(p)
    return out


def _resolve_ts(df: pd.DataFrame, t: str | None) -> pd.Timestamp:
    if t:
        want = pd.Timestamp(t)
        if want.tzinfo is None:
            want = want.tz_localize("UTC")
        idx = (df["ts_utc"] - want).abs().idxmin()
        return df.loc[idx, "ts_utc"]
    return df["ts_utc"].max()


@router.get("/cities", response_model=list[City])
def cities():
    out = []
    for cid, cfg in load_cities().items():
        out.append(City(id=cid, name=cfg["name"], bbox=cfg["bbox"], grap=bool(cfg.get("grap")),
                        replay_presets=_filter_presets(cid)))
    return out


@router.get("/timeline/{city}", response_model=TimelineResponse)
def timeline(city: str):
    deps.validate_city(city)
    nc = _nowcast(city)
    stamps = sorted(nc["ts_utc"].unique()) if not nc.empty else []
    return TimelineResponse(city=city, timestamps=[pd.Timestamp(s).isoformat() for s in stamps],
                            presets=_filter_presets(city))


@router.get("/grid/{city}", response_model=GridResponse)
def grid(city: str, t: str | None = Query(default=None)):
    deps.validate_city(city)
    nc = _nowcast(city)
    if nc.empty:
        return GridResponse(city=city, t="", cells=[])
    ts = _resolve_ts(nc, t)
    at = nc[nc["ts_utc"] == ts]
    cells = [{"hex_id": r.hex_id, "pm25": _nn(r.pm25), "aqi": _nn(r.aqi),
              "category": r.category, "low_coverage": bool(r.low_coverage)}
             for r in at.itertuples()]
    return GridResponse(city=city, t=pd.Timestamp(ts).isoformat(), cells=cells)


@router.get("/forecast/{city}/{hex_id}", response_model=ForecastResponse)
def forecast(city: str, hex_id: str):
    deps.validate_city(city)
    nc = _nowcast(city)
    history = []
    if not nc.empty:
        hx = nc[nc["hex_id"] == hex_id].sort_values("ts_utc")
        hx = hx[hx["ts_utc"] > hx["ts_utc"].max() - pd.Timedelta(hours=72)] if not hx.empty else hx
        history = [{"t": pd.Timestamp(r.ts_utc).isoformat(), "pm25": _nn(r.pm25), "aqi": _nn(r.aqi)}
                   for r in hx.itertuples()]
    fc = deps.read_parquet(deps.snap_file(city, "forecasts.parquet"))
    forecast_pts = []
    if not fc.empty:
        fx = fc[fc["hex_id"] == hex_id].sort_values("horizon_h")
        forecast_pts = [{"h": int(r.horizon_h), "t": pd.Timestamp(r.target_ts).isoformat(),
                         "pm25": _nn(r.pm25_pred), "pi_low": _nn(r.pi_low), "pi_high": _nn(r.pi_high),
                         "aqi": _nn(r.aqi_pred)} for r in fx.itertuples()]
    return ForecastResponse(city=city, hex_id=hex_id, history_72h=history, forecast=forecast_pts)


@router.get("/attribution/{city}/{hex_id}", response_model=AttributionResponse)
def attribution(city: str, hex_id: str, t: str | None = Query(default=None)):
    deps.validate_city(city)
    attr = deps.read_parquet(deps.snap_file(city, "attribution.parquet"))
    if attr.empty:
        return AttributionResponse(city=city, hex_id=hex_id, t="", shares={}, met_modifier=0.0,
                                   confidence="low", evidence={})
    attr["ts_utc"] = pd.to_datetime(attr["ts_utc"], utc=True)
    ts = _resolve_ts(attr, t)
    at = attr[(attr["ts_utc"] == ts) & (attr["hex_id"] == hex_id)]
    if at.empty:
        at = attr[attr["ts_utc"] == ts]
    row = at.iloc[0]
    from backend.models.attribution import SOURCES
    import json as _json
    shares = {s: float(row[s]) for s in SOURCES}
    return AttributionResponse(city=city, hex_id=hex_id, t=pd.Timestamp(ts).isoformat(), shares=shares,
                               met_modifier=float(row["met_modifier"]), confidence=str(row["confidence"]),
                               evidence=_json.loads(row["evidence_json"]))


@router.get("/fires/{city}")
def fires(city: str, t: str | None = Query(default=None), window_h: int = Query(default=24)):
    deps.validate_city(city)
    df = deps.read_parquet(deps.snap_file(city, "fires.parquet"))
    if df.empty:
        return []
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True)
    end = pd.Timestamp(t).tz_localize("UTC") if t and pd.Timestamp(t).tzinfo is None else \
        (pd.Timestamp(t) if t else df["ts_utc"].max())
    start = end - pd.Timedelta(hours=window_h)
    win = df[(df["ts_utc"] > start) & (df["ts_utc"] <= end)]
    return [{"lat": float(r.lat), "lng": float(r.lng), "frp": float(r.frp),
             "age_h": round((end - r.ts_utc).total_seconds() / 3600, 1)} for r in win.itertuples()]


@router.get("/actions/{city}", response_model=ActionsResponse)
def actions(city: str):
    deps.validate_city(city)
    payload = deps.read_json(deps.snap_file(city, "actions.json"))
    if not payload:
        return ActionsResponse(city=city, actions=[])
    return ActionsResponse(**payload)


@router.get("/actions/{city}/{action_id}/evidence")
def evidence(city: str, action_id: str, format: str = Query(default="html")):
    deps.validate_city(city)
    if format == "pdf":
        from backend.actions.evidence import generate_evidence_pdf
        pdf = generate_evidence_pdf(city, action_id)
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f"inline; filename=VN-{city}-{action_id}.pdf"})
    from backend.actions.evidence import generate_evidence_html
    html, gen_ms = generate_evidence_html(city, action_id)
    return HTMLResponse(content=html, headers={"X-Generation-Ms": f"{gen_ms:.0f}"})


@router.get("/advisory/{city}/{hex_id}")
def advisory(city: str, hex_id: str, lang: str = Query(default="en")):
    deps.validate_city(city)
    from backend.advisory.generate import generate_advisory
    return generate_advisory(city, hex_id, lang)


@router.get("/vulnerability/{city}")
def vulnerability(city: str):
    """Schools + hospitals point locations (OSM) for the vulnerability map layer."""
    deps.validate_city(city)
    out: dict[str, list[dict]] = {}
    for layer in ("schools", "hospitals"):
        data = deps.read_json(deps.geo_file(city, f"osm_{layer}.geojson"))
        pts = []
        for feat in data.get("features", []):
            geom = feat.get("geometry") or {}
            if geom.get("type") == "Point":
                lng, lat = geom["coordinates"][:2]
                pts.append({"lat": lat, "lng": lng})
        out[layer] = pts
    return out


@router.get("/stations/{city}")
def stations(city: str):
    deps.validate_city(city)
    df = deps.read_parquet(deps.snap_file(city, "stations.parquet"))
    if df.empty:
        return []
    return [{"station_id": int(r.station_id), "lat": float(r.lat), "lng": float(r.lng),
             "name": str(getattr(r, "station_name", ""))} for r in df.itertuples()]


@router.get("/metrics/{city}")
def metrics(city: str):
    deps.validate_city(city)
    return JSONResponse(deps.read_json(deps.snap_file(city, "metrics.json")))


@router.get("/grap/{city}")
def grap(city: str):
    deps.validate_city(city)
    from backend.actions.grap import grap_status
    status = grap_status(city)
    if status is None:
        return JSONResponse({"city": city, "grap": False})
    return status


# --- Decision Layer (DECISION_LAYER_SPEC §A1.4, §A2) ------------------------
@router.get("/interventions/{city}")
def interventions(city: str):
    deps.validate_city(city)
    out = []
    for iid, iv in load_interventions().items():
        out.append({"id": iid, "label": iv["label"], "targets": iv["targets"],
                    "efficacy": iv["efficacy"], "time_to_impact_h": iv["time_to_impact_h"],
                    "cost_tier": iv["cost_tier"], "department": iv["department"],
                    "legal_basis": iv["legal_basis"], "basis": iv["basis"]})
    return out


@router.post("/simulate/{city}")
def simulate_endpoint(city: str, body: SimulateRequest):
    deps.validate_city(city)
    from backend.actions.simulate import simulate, simulate_city
    if body.hex_id:
        return simulate(city, body.hex_id, body.intervention_id, body.at)
    return simulate_city(city, body.intervention_id, body.at)


@router.get("/why/{city}/{hex_id}")
def why_endpoint(city: str, hex_id: str, t: str | None = Query(default=None),
                 lang: str | None = Query(default=None)):
    deps.validate_city(city)
    from backend.actions.why import why
    return why(city, hex_id, t, lang)


@router.get("/order/{city}")
def order_html(city: str, hex: str = Query(...), intervention: str = Query(...)):
    deps.validate_city(city)
    from backend.actions.evidence import generate_order_html
    html, gen_ms = generate_order_html(city, hex, intervention)
    return HTMLResponse(content=html, headers={"X-Generation-Ms": f"{gen_ms:.0f}"})


@router.post("/actions/{city}/order")
def order_create(city: str, body: OrderRequest):
    deps.validate_city(city)
    from backend.actions.evidence import generate_order_html
    _, gen_ms = generate_order_html(city, body.hex_id, body.intervention_id)
    url = f"/api/order/{city}?hex={body.hex_id}&intervention={body.intervention_id}"
    return {"url": url, "generation_ms": round(gen_ms)}


@router.post("/dispatch/{city}")
def dispatch_endpoint(city: str, inspectors: int = Query(default=10),
                      shift_hours: float = Query(default=8.0)):
    deps.validate_city(city)
    from backend.actions.dispatch import dispatch
    return dispatch(city, inspectors, shift_hours)


def _nn(v):
    """NaN/None -> None (JSON-safe); else float."""
    try:
        f = float(v)
        return None if f != f else round(f, 2)
    except (TypeError, ValueError):
        return None
