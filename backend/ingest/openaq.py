"""OpenAQ v3 ingestion (BUILD_SPEC §6.1) — REQUIRED source.

Discovers CPCB/government stations in the city bbox, then pulls hourly history:
  primary  = OpenAQ public S3 archive (bucket openaq-data-archive, unsigned),
             downloaded in parallel and aggregated to the hour
  fallback = v3 API rollups /sensors/{id}/hours (or /measurements averaged to hours)
Output: data/snapshots/{city}/measurements.parquet + stations.parquet + latest.parquet.
"""
from __future__ import annotations

import datetime as dt
import gzip
import io
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import pandas as pd

from backend.config import MAX_VALID_CONCENTRATION, city_config, raw_dir, settings, snap_dir
from backend.degrade import log_degradation
from backend.ingest.http import HttpError, get_json

log = logging.getLogger("vayunetra.ingest.openaq")

BASE = "https://api.openaq.org/v3"
ARCHIVE_BUCKET = "openaq-data-archive"
WANTED_PARAMS = {"pm25", "pm10", "no2"}
PARAM_NORMALIZE = {"pm2.5": "pm25", "pm25": "pm25", "pm10": "pm10", "no2": "no2", "no₂": "no2"}
GOV_KEYWORDS = ("gov", "cpcb", "central pollution", "spcb", "pollution control", "reference")
S3_WORKERS = 24

_MIN_INTERVAL = 60.0 / 55.0  # stay <=55 req/min on the API
_last_call = [0.0]


def _throttle() -> None:
    elapsed = time.time() - _last_call[0]
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_call[0] = time.time()


def _get(path: str, params: dict | None = None) -> dict:
    _throttle()
    return get_json(f"{BASE}{path}", headers={"X-API-Key": settings.openaq_api_key}, params=params)


@dataclass
class Station:
    id: int
    name: str
    lat: float
    lng: float
    provider: str
    datetime_last: str
    sensors: list[dict] = field(default_factory=list)  # [{id, parameter}]

    @property
    def sensor_count(self) -> int:
        return len(self.sensors)

    @property
    def is_reference(self) -> bool:
        p = self.provider.lower()
        return any(k in p for k in GOV_KEYWORDS)


def discover_stations(city: str) -> list[Station]:
    """Find stations with pm25/pm10/no2 sensors, rank, and trim to the cap."""
    w, s, e, n = city_config(city)["bbox"]
    payload = _get("/locations", {"bbox": f"{w},{s},{e},{n}", "limit": 1000})
    (raw_dir(city) / "openaq_locations.json").write_text(json.dumps(payload), encoding="utf-8")

    stations: list[Station] = []
    for loc in payload.get("results", []):
        coords = loc.get("coordinates") or {}
        if coords.get("latitude") is None:
            continue
        sensors = [
            {"id": sen["id"], "parameter": PARAM_NORMALIZE.get(sen["parameter"]["name"], sen["parameter"]["name"])}
            for sen in loc.get("sensors", [])
            if sen.get("parameter", {}).get("name") in PARAM_NORMALIZE
        ]
        if not sensors:
            continue
        provider = (loc.get("provider") or {}).get("name") or (loc.get("owner") or {}).get("name", "")
        stations.append(Station(
            id=loc["id"], name=loc.get("name", f"loc-{loc['id']}"),
            lat=coords["latitude"], lng=coords["longitude"], provider=provider or "unknown",
            datetime_last=((loc.get("datetimeLast") or {}).get("utc") or ""), sensors=sensors,
        ))

    stations.sort(key=lambda st: (st.is_reference, st.sensor_count, st.datetime_last), reverse=True)
    kept = stations[: settings.max_stations_per_city]
    log.info("[%s] discovered %d stations, kept %d (%d reference)",
             city, len(stations), len(kept), sum(s.is_reference for s in kept))
    return kept


def _months_in_window() -> list[tuple[int, int]]:
    start = dt.date.fromisoformat(settings.history_start)
    end = dt.date.today()
    months, cur = [], dt.date(start.year, start.month, 1)
    while cur <= end:
        months.append((cur.year, cur.month))
        cur = dt.date(cur.year + (cur.month // 12), (cur.month % 12) + 1, 1)
    return months


# --- primary path: S3 archive (parallel) ----------------------------------
def _s3_client():
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    return boto3.client("s3", config=Config(signature_version=UNSIGNED, max_pool_connections=S3_WORKERS + 4))


def _list_station_keys(s3, station: Station) -> list[str]:
    keys: list[str] = []
    for year, month in _months_in_window():
        prefix = f"records/csv.gz/locationid={station.id}/year={year}/month={month:02d}/"
        token = None
        while True:
            kw = {"Bucket": ARCHIVE_BUCKET, "Prefix": prefix}
            if token:
                kw["ContinuationToken"] = token
            resp = s3.list_objects_v2(**kw)
            keys += [o["Key"] for o in resp.get("Contents", []) if o["Key"].endswith(".csv.gz")]
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
    return keys


def _download_key(s3, key: str) -> pd.DataFrame:
    body = s3.get_object(Bucket=ARCHIVE_BUCKET, Key=key)["Body"].read()
    return pd.read_csv(io.BytesIO(gzip.decompress(body)))


def _normalize_archive(df: pd.DataFrame, station: Station) -> pd.DataFrame:
    cols = {c.lower(): c for c in df.columns}
    ts_col = cols.get("datetime") or cols.get("date_utc")
    par_col, val_col = cols.get("parameter"), cols.get("value")
    param = df[par_col].astype(str).str.lower().map(lambda p: PARAM_NORMALIZE.get(p, p))
    out = pd.DataFrame({
        "ts_utc": pd.to_datetime(df[ts_col], utc=True, errors="coerce"),
        "parameter": param,
        "value": pd.to_numeric(df[val_col], errors="coerce"),
    })
    out["station_id"] = station.id
    out["station_name"], out["lat"], out["lng"] = station.name, station.lat, station.lng
    return out[out["parameter"].isin(WANTED_PARAMS)]


def _s3_history(s3, stations: list[Station]) -> tuple[pd.DataFrame, set[int]]:
    """Download all stations' archive files in parallel. Return (df, station_ids_with_data)."""
    tasks: list[tuple[Station, str]] = []
    for st in stations:
        try:
            tasks += [(st, key) for key in _list_station_keys(s3, st)]
        except Exception as exc:  # noqa: BLE001
            log.warning("[station %s] S3 listing failed: %s", st.id, exc)
    log.info("S3 archive: %d files across %d stations", len(tasks), len(stations))

    frames, got = [], set()
    with ThreadPoolExecutor(max_workers=S3_WORKERS) as pool:
        futures = {pool.submit(_download_key, s3, key): st for st, key in tasks}
        for fut in as_completed(futures):
            st = futures[fut]
            try:
                norm = _normalize_archive(fut.result(), st)
                if not norm.empty:
                    frames.append(norm)
                    got.add(st.id)
            except Exception as exc:  # noqa: BLE001 - skip individual bad files
                log.debug("skip file for station %s: %s", st.id, exc)
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return df, got


# --- fallback path: v3 API rollups ----------------------------------------
def _api_sensor_hours(sensor_id: int, parameter: str, station: Station) -> pd.DataFrame:
    rows, use_measurements = [], False
    for year, month in _months_in_window():
        frm = dt.date(year, month, 1).isoformat() + "T00:00:00Z"
        nxt = dt.date(year + (month // 12), (month % 12) + 1, 1)
        to = nxt.isoformat() + "T00:00:00Z"
        endpoint, page = ("measurements" if use_measurements else "hours"), 1
        while True:
            try:
                data = _get(f"/sensors/{sensor_id}/{endpoint}",
                            {"datetime_from": frm, "datetime_to": to, "limit": 1000, "page": page})
            except HttpError as exc:
                if endpoint == "hours" and "404" in str(exc):
                    use_measurements, endpoint, page = True, "measurements", 1
                    continue
                log.warning("sensor %s %s failed: %s", sensor_id, endpoint, exc)
                break
            results = data.get("results", [])
            for r in results:
                ts = ((r.get("period") or {}).get("datetimeFrom") or {}).get("utc") or \
                     ((r.get("date") or {}).get("utc"))
                rows.append({"ts_utc": ts, "value": r.get("value")})
            if len(results) < 1000:
                break
            page += 1

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["parameter"] = parameter
    df["station_id"], df["station_name"] = station.id, station.name
    df["lat"], df["lng"] = station.lat, station.lng
    return df


def _api_history(stations: list[Station]) -> pd.DataFrame:
    frames = []
    for st in stations:
        for sen in st.sensors:
            f = _api_sensor_hours(sen["id"], sen["parameter"], st)
            if not f.empty:
                frames.append(f)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# --- normalize / clean -----------------------------------------------------
def _to_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """Floor to the hour and average sub-hourly readings per station-parameter."""
    if df.empty:
        return df
    df = df.dropna(subset=["ts_utc", "value"]).copy()
    df["ts_utc"] = df["ts_utc"].dt.floor("h")
    agg = df.groupby(["station_id", "parameter", "ts_utc"], as_index=False)["value"].mean()
    meta = df[["station_id", "station_name", "lat", "lng"]].drop_duplicates("station_id")
    return agg.merge(meta, on="station_id")


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df[(df["value"] >= 0) & (df["value"] <= MAX_VALID_CONCENTRATION)]
    return df.drop_duplicates(subset=["ts_utc", "station_id", "parameter"])


def fetch_latest(stations: list[Station]) -> pd.DataFrame:
    rows = []
    for st in stations:
        try:
            data = _get(f"/locations/{st.id}/latest")
        except HttpError:
            continue
        for r in data.get("results", []):
            rows.append({"station_id": st.id, "value": r.get("value"),
                         "ts_utc": ((r.get("datetime") or {}).get("utc"))})
    return pd.DataFrame(rows)


def ingest_measurements(city: str) -> dict[str, int]:
    """Full OpenAQ ingestion for a city; persist stations/measurements/latest parquet."""
    stations = discover_stations(city)
    if not stations:
        raise SystemExit(f"HALT: OpenAQ returned no usable stations for {city}.")

    s3_df, got = _s3_history(_s3_client(), stations)
    missing = [st for st in stations if st.id not in got]
    if missing:
        log.info("[%s] %d stations missing from S3; API fallback", city, len(missing))
        api_df = _api_history(missing)
        combined = pd.concat([d for d in (s3_df, api_df) if not d.empty], ignore_index=True)
    else:
        combined = s3_df

    measurements = _clean(_to_hourly(combined))
    sdir = snap_dir(city)
    pd.DataFrame([{"station_id": s.id, "station_name": s.name, "lat": s.lat, "lng": s.lng,
                   "provider": s.provider, "is_reference": s.is_reference,
                   "sensor_count": s.sensor_count} for s in stations]
                 ).to_parquet(sdir / "stations.parquet", index=False)
    measurements.to_parquet(sdir / "measurements.parquet", index=False)
    fetch_latest(stations).to_parquet(sdir / "latest.parquet", index=False)

    if measurements.empty:
        log_degradation("openaq", f"[{city}] no measurements retrieved from S3 or API.")
    log.info("[%s] measurements rows=%d stations=%d", city, len(measurements), len(stations))
    return {"stations": len(stations), "rows": len(measurements)}


# --- live (latest-only) path ----------------------------------------------
def _api_sensor_recent(sensor_id: int, parameter: str, station: Station, days: int) -> pd.DataFrame:
    """Fetch the last `days` of hourly values for one sensor via the v3 API (not S3)."""
    now = dt.datetime.now(dt.timezone.utc)
    frm = (now - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:00:00Z")
    to = now.strftime("%Y-%m-%dT%H:00:00Z")
    rows, endpoint, page = [], "hours", 1
    while True:
        try:
            data = _get(f"/sensors/{sensor_id}/{endpoint}",
                        {"datetime_from": frm, "datetime_to": to, "limit": 1000, "page": page})
        except HttpError as exc:
            if endpoint == "hours" and "404" in str(exc):
                endpoint, page = "measurements", 1
                continue
            log.warning("sensor %s recent failed: %s", sensor_id, exc)
            break
        results = data.get("results", [])
        for r in results:
            ts = ((r.get("period") or {}).get("datetimeFrom") or {}).get("utc") or \
                 ((r.get("date") or {}).get("utc"))
            rows.append({"ts_utc": ts, "value": r.get("value")})
        if len(results) < 1000:
            break
        page += 1
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["parameter"] = parameter
    df["station_id"], df["station_name"] = station.id, station.name
    df["lat"], df["lng"] = station.lat, station.lng
    return df


def ingest_latest(city: str, days: int = 4) -> dict[str, int]:
    """LIVE refresh: pull the last few days of hourly readings from the API and merge
    them into measurements.parquet (keeping newest). Advances the data to ~1 h behind
    real time without re-downloading the multi-month S3 archive.
    """
    stations = discover_stations(city)
    frames = [_api_sensor_recent(sen["id"], sen["parameter"], st, days)
              for st in stations for sen in st.sensors]
    recent = _clean(_to_hourly(pd.concat([f for f in frames if not f.empty], ignore_index=True)
                               if any(not f.empty for f in frames) else pd.DataFrame()))
    sdir = snap_dir(city)
    path = sdir / "measurements.parquet"
    existing = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    if not existing.empty:
        existing["ts_utc"] = pd.to_datetime(existing["ts_utc"], utc=True)
    merged = pd.concat([existing, recent], ignore_index=True)
    if not merged.empty:
        merged = merged.drop_duplicates(subset=["ts_utc", "station_id", "parameter"], keep="last")
        merged = merged.sort_values(["station_id", "parameter", "ts_utc"])
    merged.to_parquet(path, index=False)
    fetch_latest(stations).to_parquet(sdir / "latest.parquet", index=False)

    added = len(merged) - len(existing)
    newest = merged["ts_utc"].max() if not merged.empty else None
    log.info("[%s] LIVE refresh: +%d rows, newest=%s", city, max(added, 0), newest)
    return {"added": max(added, 0), "total": len(merged)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for c in ("delhi", "pune"):
        print(c, ingest_measurements(c))
