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

from backend.config import city_config, settings, snap_dir
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


def ingest_fires(city: str, latest: bool = False) -> dict[str, int]:
    """Pull fires for a city's upwind bbox; persist fires.parquet.

    latest=False: full SP archive + NRT tail (initial build).
    latest=True:  NRT tail only (last 10 days), merged into existing fires.parquet — LIVE path.
    """
    cfg = city_config(city)
    bbox = cfg["fires_bbox"]
    today = dt.date.today()

    frames: list[pd.DataFrame] = []
    if not latest:
        for start_date, span in _date_chunks(dt.date.fromisoformat(settings.history_start), today):
            try:
                frames.append(_fetch_csv("VIIRS_SNPP_SP", bbox, start_date, span))
            except HttpError as exc:
                log.warning("[%s] FIRMS SP %s/%d failed: %s", city, start_date, span, exc)
    # NRT tail — archive lags real time (10 days for live, 20 for full build).
    tail_days = 10 if latest else 20
    for start_date, span in _date_chunks(today - dt.timedelta(days=tail_days), today):
        try:
            frames.append(_fetch_csv("VIIRS_NOAA20_NRT", bbox, start_date, span))
        except HttpError as exc:
            log.warning("[%s] FIRMS NRT %s/%d failed: %s", city, start_date, span, exc)

    path = snap_dir(city) / "fires.parquet"
    if not frames:
        if not latest:
            log_degradation("firms", f"[{city}] no fire data retrieved (check FIRMS_MAP_KEY).")
            pd.DataFrame(columns=["ts_utc", "lat", "lng", "frp", "confidence", "satellite"]).to_parquet(path, index=False)
        return {"rows": 0}

    raw = pd.concat(frames, ignore_index=True)
    fires = _build_ts(raw).dropna(subset=["ts_utc"])
    if "confidence" in fires.columns and fires["confidence"].dtype == object:
        fires = fires[fires["confidence"].astype(str).str.lower() != "l"]
    fires = fires.rename(columns={"latitude": "lat", "longitude": "lng"})
    fires = fires[["ts_utc", "lat", "lng", "frp", "confidence", "satellite"]].drop_duplicates()

    if latest and path.exists():
        prev = pd.read_parquet(path)
        prev["ts_utc"] = pd.to_datetime(prev["ts_utc"], utc=True)
        fires = pd.concat([prev, fires], ignore_index=True).drop_duplicates(
            subset=["ts_utc", "lat", "lng", "frp"])
    fires.to_parquet(path, index=False)
    log.info("[%s] fires rows=%d (bbox=%s, latest=%s)", city, len(fires), bbox, latest)
    return {"rows": len(fires)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for c in ("delhi", "pune"):
        print(c, ingest_fires(c))
