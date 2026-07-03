"""Event-study replays (BUILD_SPEC §13, Phase 9).

For each replay preset in the data range, plot city-mean pm25 and the biomass
attribution-share timeline, saving docs/event_{id}.png; append latency stats
(evidence generation_ms distribution) to docs/metrics.md.
"""
from __future__ import annotations

import logging

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from backend.config import DOCS_DIR, city_config, snap_dir  # noqa: E402

log = logging.getLogger("vayunetra.models.event_study")


def _biomass_share_timeline(city: str) -> pd.DataFrame:
    path = snap_dir(city) / "attribution.parquet"
    if not path.exists():
        return pd.DataFrame()
    attr = pd.read_parquet(path)
    attr["ts_utc"] = pd.to_datetime(attr["ts_utc"], utc=True)
    return attr.groupby("ts_utc")[["biomass"]].mean().reset_index()


def event_study(city: str) -> list[str]:
    """Produce event PNGs for replay presets inside the data range. Returns file paths."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    nowcast = pd.read_parquet(snap_dir(city) / "hex_nowcast.parquet")
    if nowcast.empty:
        return []
    nowcast["ts_utc"] = pd.to_datetime(nowcast["ts_utc"], utc=True)
    city_pm = nowcast.groupby("ts_utc")["pm25"].mean()
    biomass = _biomass_share_timeline(city).set_index("ts_utc")["biomass"] if not _biomass_share_timeline(city).empty else pd.Series(dtype=float)

    made = []
    for preset in city_config(city).get("replay_presets", []):
        start, end = pd.Timestamp(preset["start"], tz="UTC"), pd.Timestamp(preset["end"] + " 23:00", tz="UTC")
        pm_win = city_pm[(city_pm.index >= start) & (city_pm.index <= end)]
        if pm_win.empty:
            continue
        fig, ax1 = plt.subplots(figsize=(8, 3.6))
        ax1.plot(pm_win.index, pm_win.values, color="#334155", label="city-mean pm25")
        ax1.set_ylabel("pm25 µg/m³", color="#334155")
        ax1.set_title(f"{city} — {preset['label']}")
        bio_win = biomass[(biomass.index >= start) & (biomass.index <= end)] if len(biomass) else biomass
        if len(bio_win):
            ax2 = ax1.twinx()
            ax2.plot(bio_win.index, bio_win.values, color="#f97316", label="biomass share")
            ax2.set_ylabel("biomass share", color="#f97316"); ax2.set_ylim(0, 1)
        fig.autofmt_xdate()
        out = DOCS_DIR / f"event_{preset['id']}.png"
        fig.savefig(out, dpi=110, bbox_inches="tight"); plt.close(fig)
        made.append(str(out))
        log.info("[%s] wrote %s", city, out.name)
    return made


def latency_stats(city: str, n: int = 5) -> dict:
    """Generate n evidence packs and summarize generation_ms (the demo stopwatch)."""
    from backend.actions.evidence import generate_evidence_html

    import json
    payload = json.loads((snap_dir(city) / "actions.json").read_text(encoding="utf-8"))
    ids = [a["id"] for a in payload.get("actions", [])[:n]]
    times = []
    for aid in ids:
        try:
            _, ms = generate_evidence_html(city, aid)
            times.append(ms)
        except Exception as exc:  # noqa: BLE001
            log.warning("evidence %s failed: %s", aid, exc)
    if not times:
        return {}
    return {"n": len(times), "p50_ms": float(np.percentile(times, 50)),
            "p90_ms": float(np.percentile(times, 90)), "max_ms": float(np.max(times))}


def append_latency_to_metrics(stats_by_city: dict[str, dict]) -> None:
    path = DOCS_DIR / "metrics.md"
    lines = ["", "## Evidence-pack latency (signal → evidence)", ""]
    for city, s in stats_by_city.items():
        if s:
            lines.append(f"- **{city}**: p50 {s['p50_ms']:.0f} ms, p90 {s['p90_ms']:.0f} ms "
                         f"(n={s['n']}, target < 30000 ms).")
    with path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run_all(cities: list[str]) -> None:
    stats = {}
    for c in cities:
        event_study(c)
        stats[c] = latency_stats(c)
    append_latency_to_metrics(stats)
    append_mva_to_metrics(cities)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_all(["delhi", "pune"])


def mva_crosscheck(city: str, share_threshold: float = 0.1, agree_frac: float = 0.5) -> dict:
    """Method M vs Method A agreement for biomass on the highest-fire attribution day.

    Validates the triangulation: on a stubble day, do the model counterfactual and the
    attribution arithmetic agree? (DECISION_LAYER_SPEC §A4.2)
    """
    import lightgbm as lgb

    from backend.config import geo_city_dir, load_interventions
    from backend.features.build import FEATURE_COLUMNS
    from backend.features.interpolate import _idw, _neighbors
    from backend.models.dataset import model_dir

    sdir = snap_dir(city)
    attr = pd.read_parquet(sdir / "attribution.parquet")
    attr["ts_utc"] = pd.to_datetime(attr["ts_utc"], utc=True)
    ts = attr.groupby("ts_utc")["biomass"].mean().idxmax()  # the high-fire day
    attr_t = attr[attr["ts_utc"] == ts].set_index("hex_id")
    hot = attr_t[attr_t["biomass"] > share_threshold]
    if hot.empty:
        return {"city": city, "n": 0, "agreement_pct": None, "ts": str(ts)}

    nowcast = pd.read_parquet(sdir / "hex_nowcast.parquet")
    nowcast["ts_utc"] = pd.to_datetime(nowcast["ts_utc"], utc=True)
    now_t = nowcast[nowcast["ts_utc"] == ts].set_index("hex_id")
    panel = pd.read_parquet(sdir / "features.parquet")
    panel["ts_utc"] = pd.to_datetime(panel["ts_utc"], utc=True)
    panel_t = panel[panel["ts_utc"] == ts].drop_duplicates("station_id")
    if panel_t.empty:
        return {"city": city, "n": 0, "agreement_pct": None, "ts": str(ts)}

    e_mid = load_interventions()["biomass_enforcement"]["efficacy"][1]
    model = lgb.Booster(model_file=str(model_dir(city) / "pm25_h24.txt"))
    X = panel_t[FEATURE_COLUMNS].to_numpy(dtype=float)
    Xm = X.copy()
    for f in ("fire_load_upwind_24", "fire_count_radius_24"):
        Xm[:, FEATURE_COLUMNS.index(f)] *= (1 - e_mid)
    delta_station = np.clip(model.predict(X) - model.predict(Xm), 0, None)

    grid = pd.read_parquet(geo_city_dir(city) / "grid.parquet")
    stations = panel_t[["station_id", "lat", "lng"]].reset_index(drop=True)
    from backend.config import city_config
    nn_idx, weights, _ = _neighbors(grid, stations, float(city_config(city)["idw_max_radius_km"]))
    hex_delta_m = _idw(delta_station, nn_idx, weights)
    hpos = {h: i for i, h in enumerate(grid["hex_id"].to_numpy())}

    agree = []
    for hex_id, row in hot.iterrows():
        if hex_id not in now_t.index or hex_id not in hpos:
            continue
        pm = float(now_t.loc[hex_id, "pm25"])
        a = pm * float(row["biomass"]) * e_mid
        m = float(hex_delta_m[hpos[hex_id]])
        denom = max(a, m, 1e-6)
        agree.append(abs(a - m) <= agree_frac * denom)
    pct = round(100 * np.mean(agree), 1) if agree else None
    return {"city": city, "n": len(agree), "agreement_pct": pct, "ts": str(ts),
            "e_mid": e_mid, "threshold": share_threshold}


def append_mva_to_metrics(cities: list[str]) -> None:
    lines = ["", "## Triangulation cross-check — biomass Method M vs Method A", "",
             "On each city's highest-fire attribution day, fraction of high-biomass hexes where the "
             "model counterfactual (M) and attribution arithmetic (A) agree within 50%.", ""]
    for c in cities:
        try:
            r = mva_crosscheck(c)
            if r["agreement_pct"] is not None:
                lines.append(f"- **{c}**: {r['agreement_pct']}% agreement over {r['n']} hexes "
                             f"(day {r['ts'][:10]}, efficacy_mid {r['e_mid']}).")
            else:
                lines.append(f"- **{c}**: no high-biomass hexes on the replay day (low-fire snapshot).")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"- **{c}**: cross-check unavailable ({exc}).")
    with (DOCS_DIR / "metrics.md").open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
