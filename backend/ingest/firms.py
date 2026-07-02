"""NASA FIRMS active-fire ingestion (BUILD_SPEC §6.3) — REQUIRED source.

Pulls VIIRS thermal anomalies over the city's upwind fire bbox in 5-day chunks
(the FIRMS area API caps day_range at 5):
  VIIRS_SNPP_SP   = standard-processing archive (history)
  VIIRS_NOAA20_NRT = near-real-time recent tail
Output: data/snapshots/{city}/fires.parquet (ts_utc, lat, lng, frp, confidence, satellite).
"""
from __future__ import annotations

import datetime as dt
import io
import logging

import pandas as pd

from backend.config import city_config, raw_dir, settings, snap_dir
from backend.degrade import log_degradation
from backend.ingest.http import HttpError, get_text

log = logging.getLogger("vayunetra.ingest.firms")

BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
KEEP = ["latitude", "longitude", "acq_date", "acq_time", "frp", "confidence", "satellite"]


def _date_chunks(start: dt.date, end: dt.date, step_days: int = 5) -> list[tuple[str, int]]:
    """Yield (start_date_iso, day_range) covering [start, end] in <=5-day steps.

    NASA FIRMS area API caps day_range at 5 (returns HTTP 400 for larger).
    """
    chunks, cur = [], start
    while cur <= end:
        span = min(step_days, (end - cur).days + 1)
        chunks.append((cur.isoformat(), span))
        cur += dt.timedelta(days=span)
    return chunks


def _fetch_csv(source: str, bbox: list[float], start_date: str, day_range: int) -> pd.DataFrame:
    w, s, e, n = bbox
    url = f"{BASE}/{settings.firms_map_key}/{source}/{w},{s},{e},{n}/{day_range}/{start_date}"
    text = get_text(url, timeout=120)
    if not text or "latitude" not in text.splitlines()[0].lower():
        # FIRMS returns a plain-text error (e.g. "Invalid MAP_KEY") instead of CSV.
        raise HttpError(f"FIRMS non-CSV response: {text[:120]!r}")
    df = pd.read_csv(io.StringIO(text))
    keep = [c for c in KEEP if c in df.columns]
    return df[keep]


def _build_ts(df: pd.DataFrame) -> pd.DataFrame:
    """Combine acq_date + acq_time (HHMM, UTC) into ts_utc."""
    t = df["acq_time"].astype(int).astype(str).str.zfill(4)
    stamp = df["acq_date"].astype(str) + " " + t.str[:2] + ":" + t.str[2:]
    df = df.copy()
    df["ts_utc"] = pd.to_datetime(stamp, utc=True, errors="coerce")
    return df


def ingest_fires(city: str) -> dict[str, int]:
    """Pull archive + NRT fires for a city's upwind bbox; persist fires.parquet."""
    cfg = city_config(city)
    bbox = cfg["fires_bbox"]
    start = dt.date.fromisoformat(settings.history_start)
    today = dt.date.today()

    frames: list[pd.DataFrame] = []
    for start_date, span in _date_chunks(start, today):
        try:
            frames.append(_fetch_csv("VIIRS_SNPP_SP", bbox, start_date, span))
        except HttpError as exc:
            log.warning("[%s] FIRMS SP %s/%d failed: %s", city, start_date, span, exc)
    # Recent tail (last 20 days) from NRT — archive lags real time.
    for start_date, span in _date_chunks(today - dt.timedelta(days=20), today):
        try:
            frames.append(_fetch_csv("VIIRS_NOAA20_NRT", bbox, start_date, span))
        except HttpError as exc:
            log.warning("[%s] FIRMS NRT %s/%d failed: %s", city, start_date, span, exc)

    if not frames:
        log_degradation("firms", f"[{city}] no fire data retrieved (check FIRMS_MAP_KEY).")
        fires = pd.DataFrame(columns=["ts_utc", "lat", "lng", "frp", "confidence", "satellite"])
        fires.to_parquet(snap_dir(city) / "fires.parquet", index=False)
        return {"rows": 0}

    raw = pd.concat(frames, ignore_index=True)
    (raw_dir(city) / "firms_raw.csv").write_text(raw.to_csv(index=False), encoding="utf-8")

    fires = _build_ts(raw).dropna(subset=["ts_utc"])
    if "confidence" in fires.columns and fires["confidence"].dtype == object:
        fires = fires[fires["confidence"].astype(str).str.lower() != "l"]
    fires = fires.rename(columns={"latitude": "lat", "longitude": "lng"})
    fires = fires[["ts_utc", "lat", "lng", "frp", "confidence", "satellite"]].drop_duplicates()

    fires.to_parquet(snap_dir(city) / "fires.parquet", index=False)
    log.info("[%s] fires rows=%d (bbox=%s)", city, len(fires), bbox)
    return {"rows": len(fires)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for c in ("delhi", "pune"):
        print(c, ingest_fires(c))
