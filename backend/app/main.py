"""FastAPI application entry point.

Serves the offline-first API: every read comes from local Parquet/JSON snapshots
(BUILD_SPEC §1.4). When LIVE_MODE=1, APScheduler refreshes snapshots hourly.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import router
from backend.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("vayunetra")


def create_app() -> FastAPI:
    app = FastAPI(
        title="VayuNetra API",
        version="1.0.0",
        description="Urban air-quality intelligence: attribution, forecasting, enforcement evidence.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],  # POST: /refresh, /dispatch, /actions/{city}/order
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")

    if settings.live_mode:
        _start_scheduler(app)
    return app


def _start_scheduler(app: FastAPI) -> None:
    """Hourly snapshot refresh, only when LIVE_MODE=1 (BUILD_SPEC §1.4)."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        from scripts.run_pipeline import refresh_live

        scheduler = BackgroundScheduler(timezone="UTC")
        scheduler.add_job(refresh_live, "interval", hours=1, id="live_refresh")
        scheduler.start()
        app.state.scheduler = scheduler
        log.info("LIVE_MODE=1: hourly snapshot refresh scheduled.")
    except Exception as exc:  # pragma: no cover - scheduler is best-effort
        log.warning("Could not start live scheduler: %s", exc)


app = create_app()
