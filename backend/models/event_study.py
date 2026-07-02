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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_all(["delhi", "pune"])
