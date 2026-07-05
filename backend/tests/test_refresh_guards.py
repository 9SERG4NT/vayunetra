"""Concurrency guards on the LIVE refresh funnel (scripts/run_pipeline.refresh_live).

Both guards bail out before any ingest/network work, so these tests are fast and
deterministic: no HTTP calls, no snapshot writes.
"""
import time

from scripts import run_pipeline as rp


def test_refresh_skipped_when_lock_held():
    assert rp._refresh_lock.acquire(blocking=False)
    try:
        out = rp.refresh_live()
        assert out == {"skipped": "already_running"}
    finally:
        rp._refresh_lock.release()


def test_refresh_skipped_within_min_interval():
    prev = rp._last_refresh_done[0]
    rp._last_refresh_done[0] = time.time()  # pretend a refresh just finished
    try:
        out = rp.refresh_live()
        assert out.get("skipped") == "too_soon"
        assert 0 < out["retry_after_s"] <= rp.MIN_REFRESH_INTERVAL_S
    finally:
        rp._last_refresh_done[0] = prev
