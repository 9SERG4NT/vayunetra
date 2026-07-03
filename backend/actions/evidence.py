"""Evidence pack generation (BUILD_SPEC §9.2).

Self-contained HTML (inline CSS + base64 PNGs) is primary; fpdf2 PDF is secondary.
Contents: header, location map, 72h observed+forecast chart, attribution bar +
confidence, fire/lift evidence table, recommended action + GRAP, draft notice,
method appendix, PRANA-reporting stub. generation_ms is instrumented (the demo stopwatch).
"""
from __future__ import annotations

import base64
import io
import json
import logging
import time
from datetime import datetime, timezone

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import h3  # noqa: E402

from backend.actions.grap import grap_status  # noqa: E402
from backend.config import IST_OFFSET_MINUTES, city_config, geo_city_dir, snap_dir  # noqa: E402
from backend.geoutils import haversine_km, initial_bearing_deg  # noqa: E402
from backend.models.attribution import SOURCES  # noqa: E402

log = logging.getLogger("vayunetra.actions.evidence")
IST = pd.Timedelta(minutes=IST_OFFSET_MINUTES)
CONF_COLOR = {"high": "#16a34a", "medium": "#eab308", "low": "#f97316"}


def _to_ist(ts: pd.Timestamp) -> str:
    return (pd.Timestamp(ts) + IST).strftime("%Y-%m-%d %H:%M IST")


def _png_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _load_action(city: str, action_id: str) -> dict:
    payload = json.loads((snap_dir(city) / "actions.json").read_text(encoding="utf-8"))
    for a in payload["actions"]:
        if a["id"] == str(action_id):
            return a
    raise KeyError(f"action {action_id} not found for {city}")


def _hex_center(hex_id: str) -> tuple[float, float]:
    lat, lng = h3.cell_to_latlng(hex_id)
    return lat, lng


def _trailing_fires(city: str, lat: float, lng: float) -> pd.DataFrame:
    path = snap_dir(city) / "fires.parquet"
    if not path.exists():
        return pd.DataFrame()
    fires = pd.read_parquet(path)
    if fires.empty:
        return fires
    fires["ts_utc"] = pd.to_datetime(fires["ts_utc"], utc=True)
    recent = fires[fires["ts_utc"] > fires["ts_utc"].max() - pd.Timedelta(days=7)].copy()
    if recent.empty:
        return recent
    recent["dist_km"] = haversine_km(lat, lng, recent["lat"].to_numpy(), recent["lng"].to_numpy())
    recent["bearing"] = initial_bearing_deg(lat, lng, recent["lat"].to_numpy(), recent["lng"].to_numpy())
    radius = float(city_config(city)["fire_radius_km"])
    return recent[recent["dist_km"] <= radius].sort_values("dist_km").head(10)


def _map_png(city: str, hex_id: str, lat: float, lng: float) -> str:
    boundary = np.array(h3.cell_to_boundary(hex_id))  # (lat, lng)
    stations = pd.read_parquet(snap_dir(city) / "stations.parquet")
    fires = _trailing_fires(city, lat, lng)

    fig, ax = plt.subplots(figsize=(5.2, 4.2))
    ax.plot(np.append(boundary[:, 1], boundary[0, 1]), np.append(boundary[:, 0], boundary[0, 0]),
            color="#2563eb", lw=2, label="target hex")
    ax.scatter(stations["lng"], stations["lat"], c="#0ea5e9", s=18, label="stations", zorder=3)
    if not fires.empty:
        ax.scatter(fires["lng"], fires["lat"], s=np.clip(fires["frp"] * 2, 8, 120),
                   c="#f97316", alpha=0.7, label="fires (7d)", zorder=2)
    ax.scatter([lng], [lat], marker="*", c="#dc2626", s=160, label="hotspot", zorder=4)
    ax.set_title("Location & evidence map")
    ax.set_xlabel("lon"); ax.set_ylabel("lat"); ax.legend(fontsize=7, loc="upper right")
    try:
        import contextily as cx
        ax.set_xlim(*ax.get_xlim()); ax.set_ylim(*ax.get_ylim())
        cx.add_basemap(ax, crs="EPSG:4326", source=cx.providers.CartoDB.Positron, attribution_size=5)
    except Exception as exc:  # noqa: BLE001 - basemap is best-effort
        ax.text(0.02, 0.02, "(basemap unavailable)", transform=ax.transAxes, fontsize=6, color="#888")
        log.debug("basemap failed: %s", exc)
    return _png_b64(fig)


def _forecast_png(city: str, hex_id: str) -> str:
    nowcast = pd.read_parquet(snap_dir(city) / "hex_nowcast.parquet")
    nowcast["ts_utc"] = pd.to_datetime(nowcast["ts_utc"], utc=True)
    hx = nowcast[nowcast["hex_id"] == hex_id].sort_values("ts_utc")
    hist = hx[hx["ts_utc"] > hx["ts_utc"].max() - pd.Timedelta(hours=72)]

    fig, ax = plt.subplots(figsize=(6.2, 3.4))
    if not hist.empty:
        ax.plot(hist["ts_utc"] + IST, hist["pm25"], color="#334155", lw=1.6, label="observed pm25")
    fc_path = snap_dir(city) / "forecasts.parquet"
    if fc_path.exists():
        fc = pd.read_parquet(fc_path)
        fc = fc[fc["hex_id"] == hex_id].sort_values("horizon_h")
        if not fc.empty:
            fc["ts_utc"] = pd.to_datetime(fc["target_ts"], utc=True)
            ax.plot(fc["ts_utc"] + IST, fc["pm25_pred"], color="#2563eb", marker="o", label="forecast")
            ax.fill_between(fc["ts_utc"] + IST, fc["pi_low"], fc["pi_high"], color="#2563eb", alpha=0.18,
                            label="10–90% PI")
    ax.set_title("72-h observed + forecast (pm25)")
    ax.set_ylabel("µg/m³"); ax.legend(fontsize=7); fig.autofmt_xdate()
    return _png_b64(fig)


def _attribution_png(city: str, hex_id: str) -> tuple[str, dict]:
    attr = pd.read_parquet(snap_dir(city) / "attribution.parquet")
    attr["ts_utc"] = pd.to_datetime(attr["ts_utc"], utc=True)
    latest = attr[attr["ts_utc"] == attr["ts_utc"].max()]
    row = latest[latest["hex_id"] == hex_id]
    row = row.iloc[0] if not row.empty else latest.iloc[0]
    shares = [float(row[s]) for s in SOURCES]

    fig, ax = plt.subplots(figsize=(5.2, 3.2))
    colors = ["#f97316", "#64748b", "#7c3aed", "#a16207", "#94a3b8"]
    ax.bar(SOURCES, shares, color=colors)
    ax.set_title(f"Source attribution — confidence: {row['confidence']}")
    ax.set_ylabel("share"); ax.set_ylim(0, 1); ax.tick_params(axis="x", rotation=30, labelsize=8)
    return _png_b64(fig), {"row": row, "shares": dict(zip(SOURCES, shares))}


def _draft_notice(city: str, action: dict, ev: dict) -> str:
    row = ev["row"]
    top = max(ev["shares"], key=ev["shares"].get)
    text = (
        f"Draft enforcement notice (auto-generated, for officer review). At {action['locality']} "
        f"(hex {action['hex']}), the hourly AQI proxy reads {int(action['aqi'])} "
        f"({row['confidence']}-confidence attribution). The dominant contributing source is "
        f"'{top}' at {ev['shares'][top]*100:.0f}% share. Recommended action: {action['recommended_action']} "
        f"This notice is evidence-weighted (not regulatory source apportionment) and should be "
        f"corroborated on site before formal issuance."
    )
    from backend.advisory.llm import polish  # local import to avoid cycle
    return polish(text, "en")


def _context(city: str, action_id: str) -> dict:
    action = _load_action(city, action_id)
    hex_id = action["hex"]
    lat, lng = _hex_center(hex_id)
    map_png = _map_png(city, hex_id, lat, lng)
    fc_png = _forecast_png(city, hex_id)
    attr_png, ev = _attribution_png(city, hex_id)
    fires = _trailing_fires(city, lat, lng)
    grap = grap_status(city)
    return {"action": action, "hex_id": hex_id, "lat": lat, "lng": lng, "map_png": map_png,
            "fc_png": fc_png, "attr_png": attr_png, "ev": ev, "fires": fires, "grap": grap,
            "notice": _draft_notice(city, action, ev)}


def _prana_stub(city: str, ctx: dict) -> dict:
    return {
        "report_type": "PRANA_NCAP_hotspot",
        "city": city_config(city)["name"],
        "period": _to_ist(pd.Timestamp.now(tz="UTC")),
        "hotspot": {"hex": ctx["hex_id"], "locality": ctx["action"]["locality"],
                    "lat": round(ctx["lat"], 5), "lng": round(ctx["lng"], 5)},
        "source_category": ctx["action"]["source"],
        "action_recommended": ctx["action"]["recommended_action"],
        "aqi_proxy": ctx["action"]["aqi"],
        "confidence": ctx["ev"]["row"]["confidence"],
        "evidence_refs": json.loads(ctx["ev"]["row"]["evidence_json"]),
    }


def _fire_rows_html(fires: pd.DataFrame) -> str:
    if fires.empty:
        return "<tr><td colspan='4'>No fire detections within radius in the trailing 7 days.</td></tr>"
    out = []
    for _, f in fires.iterrows():
        out.append(f"<tr><td>{_to_ist(f['ts_utc'])}</td><td>{f['dist_km']:.0f}</td>"
                   f"<td>{f['bearing']:.0f}°</td><td>{f['frp']:.1f}</td></tr>")
    return "".join(out)


def generate_evidence_html(city: str, action_id: str) -> tuple[str, float]:
    t0 = time.time()
    ctx = _context(city, action_id)
    a, ev = ctx["action"], ctx["ev"]
    ref = f"VN-{city}-{datetime.now(timezone.utc):%Y%m%d}-{a['id']}"
    ejson = json.loads(ev["row"]["evidence_json"])
    grap_html = ""
    if ctx["grap"]:
        g = ctx["grap"]
        grap_html = (f"<p><b>GRAP:</b> {g['label']} · current stage {g['current_stage']}, "
                     f"predicted 48h stage {g['predicted_stage_48h']}.</p>")
    gen_ms = (time.time() - t0) * 1000
    html = _HTML_TEMPLATE.format(
        ref=ref, city=city_config(city)["name"], locality=a["locality"], hex=ctx["hex_id"],
        ts=_to_ist(pd.Timestamp.now(tz="UTC")), aqi=int(a["aqi"]), confidence=ev["row"]["confidence"],
        conf_color=CONF_COLOR.get(ev["row"]["confidence"], "#64748b"),
        map_png=ctx["map_png"], fc_png=ctx["fc_png"], attr_png=ctx["attr_png"],
        fire_rows=_fire_rows_html(ctx["fires"]),
        biomass_lift=ejson.get("biomass_lift"), industry_lift=ejson.get("industry_lift"),
        station_km=ejson.get("station_km"), station_id=ejson.get("station_id"),
        action=a["recommended_action"], grap_html=grap_html, notice=ctx["notice"],
        prana=json.dumps(_prana_stub(city, ctx), indent=2), gen_ms=f"{gen_ms:.0f}",
    )
    log.info("[%s] evidence %s generated in %.0f ms", city, action_id, gen_ms)
    return html, gen_ms


def generate_evidence_pdf(city: str, action_id: str) -> bytes:
    from fpdf import FPDF

    ctx = _context(city, action_id)
    a = ctx["action"]
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 9, "VayuNetra — Enforcement Evidence Pack", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, f"Ref VN-{city}-{datetime.now(timezone.utc):%Y%m%d}-{a['id']} | "
                         f"{a['locality']} (hex {ctx['hex_id']}) | AQI {int(a['aqi'])} | "
                         f"confidence {ctx['ev']['row']['confidence']}")
    for png in (ctx["map_png"], ctx["fc_png"], ctx["attr_png"]):
        pdf.image(io.BytesIO(base64.b64decode(png)), w=170)
    pdf.set_font("Helvetica", "B", 11)
    pdf.multi_cell(0, 6, "Recommended action")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, a["recommended_action"])
    pdf.multi_cell(0, 6, ctx["notice"])
    out = pdf.output()
    return bytes(out)


_HTML_TEMPLATE = """<!doctype html><html><head><meta charset="utf-8">
<title>VayuNetra Evidence {ref}</title><style>
body{{font-family:system-ui,Segoe UI,Roboto,sans-serif;max-width:860px;margin:24px auto;color:#0f172a;padding:0 16px}}
h1{{font-size:20px;margin:0}} h2{{font-size:15px;border-bottom:1px solid #e2e8f0;padding-bottom:4px;margin-top:28px}}
.meta{{color:#475569;font-size:13px}} .badge{{display:inline-block;padding:2px 10px;border-radius:999px;color:#fff;font-size:12px;background:{conf_color}}}
img{{max-width:100%;border:1px solid #e2e8f0;border-radius:8px}} table{{border-collapse:collapse;width:100%;font-size:13px}}
td,th{{border:1px solid #e2e8f0;padding:5px 8px;text-align:left}} .stamp{{background:#ecfeff;border:1px solid #a5f3fc;border-radius:8px;padding:8px 12px;font-weight:600}}
pre{{background:#0f172a;color:#e2e8f0;padding:12px;border-radius:8px;overflow:auto;font-size:12px}}
.notice{{background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:12px}}
</style></head><body>
<h1>VayuNetra — Enforcement Evidence Pack</h1>
<p class="meta">Ref <b>{ref}</b> · {city} · {locality} · hex {hex} · generated {ts}</p>
<p>Hourly AQI proxy: <b>{aqi}</b> · Attribution confidence: <span class="badge">{confidence}</span></p>
<p class="stamp">⏱ Signal → court-ready evidence in {gen_ms} ms</p>
<h2>Location &amp; evidence map</h2><img src="data:image/png;base64,{map_png}">
<h2>72-hour observed + forecast</h2><img src="data:image/png;base64,{fc_png}">
<h2>Source attribution</h2><img src="data:image/png;base64,{attr_png}">
<h2>Evidence — trailing-7-day fires (top 10) &amp; wind-sector lift</h2>
<table><tr><th>Datetime (IST)</th><th>Dist km</th><th>Bearing</th><th>FRP</th></tr>{fire_rows}</table>
<p class="meta">Wind-sector lift — biomass: {biomass_lift} · industry: {industry_lift}. Nearest station #{station_id} at {station_km} km.</p>
<h2>Recommended action</h2><p>{action}</p>{grap_html}
<h2>Draft notice</h2><div class="notice">{notice}</div>
<h2>PRANA reporting stub</h2><pre>{prana}</pre>
<h2>Method &amp; sources</h2>
<p class="meta">Data: OpenAQ/CPCB stations, NASA FIRMS VIIRS active fires, Open-Meteo ERA5 + CAMS,
OpenStreetMap land use. Attribution is <b>evidence-weighted, confidence-scored — not regulatory
source apportionment</b>. Hourly AQI proxy uses hourly concentrations (official CPCB NAQI uses 24-h averages).</p>
</body></html>"""


# --- Directed Intervention ORDER document (DECISION_LAYER_SPEC §A1.4) --------
def _locality_for(city: str, hex_id: str) -> str:
    grid = pd.read_parquet(geo_city_dir(city) / "grid.parquet")
    m = grid[grid["hex_id"] == hex_id]
    return str(m.iloc[0]["locality"]) if not m.empty else hex_id


def generate_order_html(city: str, hex_id: str, intervention_id: str) -> tuple[str, float]:
    """Order = evidence pack + a 'Directed Intervention' section (planning estimates)."""
    from backend.actions.simulate import simulate

    t0 = time.time()
    sc = simulate(city, hex_id, intervention_id)
    lat, lng = _hex_center(hex_id)
    locality = _locality_for(city, hex_id)
    ref = f"VN-ORDER-{city}-{datetime.now(timezone.utc):%Y%m%d}-{intervention_id}"
    review_by = _to_ist(pd.Timestamp.now(tz="UTC") + pd.Timedelta(hours=sc["time_to_impact_h"][1]))
    da = sc["delta_aqi"]
    directed = _DIRECTED_TEMPLATE.format(
        label=sc["label"], department=sc["department"], legal_basis=sc["legal_basis"],
        aqi_now=sc["aqi_now"], da_lo=da["lo"], da_mid=da["mid"], da_hi=da["hi"],
        tti_lo=sc["time_to_impact_h"][0], tti_hi=sc["time_to_impact_h"][1], cost=sc["cost_tier"],
        method=sc["method"], confidence=sc["confidence"], review_by=review_by,
        conf_color=CONF_COLOR.get(sc["confidence"], "#64748b"),
        person_hours=f"{sc['exposure']['person_hours_avoided']['mid']:,}",
        schools=sc["exposure"]["schools_affected"], hospitals=sc["exposure"]["hospitals_affected"],
    )
    html = _ORDER_TEMPLATE.format(
        ref=ref, city=city_config(city)["name"], locality=locality, hex=hex_id,
        ts=_to_ist(pd.Timestamp.now(tz="UTC")), map_png=_map_png(city, hex_id, lat, lng),
        fc_png=_forecast_png(city, hex_id), attr_png=_attribution_png(city, hex_id)[0],
        directed=directed,
    )
    gen_ms = (time.time() - t0) * 1000
    log.info("[%s] order %s/%s generated in %.0f ms", city, hex_id, intervention_id, gen_ms)
    return html, gen_ms


_DIRECTED_TEMPLATE = """<div class="directed">
<h2>Directed Intervention (planning estimate)</h2>
<table>
<tr><th>Intervention</th><td>{label}</td></tr>
<tr><th>Responsible department</th><td>{department}</td></tr>
<tr><th>Legal basis</th><td>{legal_basis}</td></tr>
<tr><th>Current AQI (proxy)</th><td>{aqi_now}</td></tr>
<tr><th>Model-implied ΔAQI</th><td><b>{da_mid}</b> (range {da_lo}–{da_hi}) · method: {method}</td></tr>
<tr><th>Confidence</th><td><span class="badge" style="background:{conf_color}">{confidence}</span></td></tr>
<tr><th>Time to impact</th><td>{tti_lo}–{tti_hi} h · cost: {cost}</td></tr>
<tr><th>Exposure in relief zone</th><td>{schools} schools, {hospitals} hospitals · ~{person_hours} person-hours avoided (proxy)</td></tr>
<tr><th>Review by</th><td><b>{review_by}</b></td></tr>
</table>
<p class="disclaimer">These are <b>planning estimates</b> from attribution × editable priors (config/interventions.yaml),
model-implied — <b>not</b> a causal guarantee. Corroborate on site before formal issuance.</p>
</div>"""

_ORDER_TEMPLATE = """<!doctype html><html><head><meta charset="utf-8">
<title>VayuNetra Order {ref}</title><style>
body{{font-family:system-ui,Segoe UI,Roboto,sans-serif;max-width:860px;margin:24px auto;color:#0f172a;padding:0 16px}}
h1{{font-size:20px;margin:0}} h2{{font-size:15px;border-bottom:1px solid #e2e8f0;padding-bottom:4px;margin-top:28px}}
.meta{{color:#475569;font-size:13px}} img{{max-width:100%;border:1px solid #e2e8f0;border-radius:8px}}
table{{border-collapse:collapse;width:100%;font-size:13px}} td,th{{border:1px solid #e2e8f0;padding:6px 9px;text-align:left}}
.badge{{display:inline-block;padding:2px 10px;border-radius:999px;color:#fff;font-size:12px}}
.directed{{background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;padding:8px 16px;margin-top:20px}}
.disclaimer{{background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:10px;font-size:12px}}
</style></head><body>
<h1>VayuNetra — Directed Intervention Order</h1>
<p class="meta">Ref <b>{ref}</b> · {city} · {locality} · hex {hex} · issued {ts}</p>
{directed}
<h2>Location &amp; evidence map</h2><img src="data:image/png;base64,{map_png}">
<h2>72-hour observed + forecast</h2><img src="data:image/png;base64,{fc_png}">
<h2>Source attribution</h2><img src="data:image/png;base64,{attr_png}">
<h2>Method &amp; sources</h2>
<p class="meta">Data: OpenAQ/CPCB, NASA FIRMS VIIRS, Open-Meteo ERA5+CAMS, OpenStreetMap.
Attribution is evidence-weighted, confidence-scored — not regulatory apportionment. Intervention outcomes
are planning estimates (correlational model + literature priors), designed for prioritisation.</p>
</body></html>"""
