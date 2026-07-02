"""Optional data.gov.in live cross-check (BUILD_SPEC §6.4).

Only runs when DATA_GOV_IN_API_KEY is set. Stores latest CPCB readings for
display/cross-check ONLY — never a training dependency.
"""
from __future__ import annotations

import logging

import pandas as pd

from backend.config import settings, snap_dir
from backend.degrade import log_degradation
from backend.ingest.http import HttpError, get_json

log = logging.getLogger("vayunetra.ingest.datagov")

RESOURCE = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"
URL = f"https://api.data.gov.in/resource/{RESOURCE}"

# city id -> data.gov.in state filter value
STATE_FILTER = {"delhi": "Delhi", "pune": "Maharashtra"}


def ingest_datagov(city: str) -> dict[str, int]:
    """Fetch latest CPCB readings for a state; persist datagov_latest.parquet."""
    if not settings.data_gov_in_api_key:
        log.info("[%s] DATA_GOV_IN_API_KEY unset; skipping optional cross-check.", city)
        return {"rows": 0, "skipped": 1}

    params = {
        "api-key": settings.data_gov_in_api_key,
        "format": "json",
        "limit": 2000,
        "filters[state]": STATE_FILTER.get(city, "Delhi"),
    }
    try:
        payload = get_json(URL, params=params)
    except HttpError as exc:
        log_degradation("data.gov.in", f"[{city}] cross-check unavailable: {exc}")
        return {"rows": 0}

    records = payload.get("records", [])
    df = pd.DataFrame(records)
    df.to_parquet(snap_dir(city) / "datagov_latest.parquet", index=False)
    log.info("[%s] data.gov.in latest rows=%d", city, len(df))
    return {"rows": len(df)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for c in ("delhi", "pune"):
        print(c, ingest_datagov(c))
