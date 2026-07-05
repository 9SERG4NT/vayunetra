"""Pipeline orchestrator: ingest -> features -> train -> predict -> attribution -> actions.

Stage dispatch keeps imports lazy so a single stage never pulls in the whole stack.
Run one stage at a time (via the Makefile) or `all` for the full sequence.

    uv run python scripts/run_pipeline.py <stage> --cities delhi pune

Stages: geo | data | features | train | evaluate | predict | attribution | actions | all
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Allow `python scripts/run_pipeline.py` to import the `backend` package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

log = logging.getLogger("vayunetra.pipeline")

STAGES = ["geo", "data", "features", "train", "evaluate", "predict", "attribution", "actions"]


def stage_geo(cities: list[str]) -> None:
    from backend.geo.grid import build_grid
    from backend.geo.static_features import build_static_features
    from backend.ingest.overpass import fetch_all_layers

    for city in cities:
        build_grid(city)
        fetch_all_layers(city)
        build_static_features(city)


def stage_data(cities: list[str]) -> None:
    from backend.config import require_env_or_halt
    from backend.ingest.firms import ingest_fires
    from backend.ingest.meteo import ingest_meteo
    from backend.ingest.openaq import ingest_measurements

    require_env_or_halt()
    for city in cities:
        ingest_measurements(city)
        ingest_meteo(city)
        ingest_fires(city)


def stage_features(cities: list[str]) -> None:
    from backend.features.build import build_features
    from backend.features.interpolate import build_hex_nowcast

    for city in cities:
        build_features(city)
        build_hex_nowcast(city)


def stage_train(cities: list[str]) -> None:
    from backend.models.train import train_city

    for city in cities:
        train_city(city)


def stage_evaluate(cities: list[str]) -> None:
    from backend.models.evaluate import evaluate_all

    evaluate_all(cities)


def stage_predict(cities: list[str]) -> None:
    from backend.models.predict import predict_city

    for city in cities:
        predict_city(city)


def stage_attribution(cities: list[str]) -> None:
    from backend.models.attribution import attribute_city

    for city in cities:
        attribute_city(city)


def stage_actions(cities: list[str]) -> None:
    from backend.actions.ranker import rank_city

    for city in cities:
        rank_city(city)


_DISPATCH = {
    "geo": stage_geo,
    "data": stage_data,
    "features": stage_features,
    "train": stage_train,
    "evaluate": stage_evaluate,
    "predict": stage_predict,
    "attribution": stage_attribution,
    "actions": stage_actions,
}


def stage_validate(cities: list[str]) -> None:
    from backend.models.event_study import run_all as event_run

    event_run(cities)


def run_all(cities: list[str]) -> None:
    for stage in STAGES:
        log.info("=== stage: %s ===", stage)
        t0 = time.time()
        _DISPATCH[stage](cities)
        log.info("stage %s done in %.1fs", stage, time.time() - t0)
    log.info("=== stage: validate (event study + latency) ===")
    stage_validate(cities)


def stage_data_latest(cities: list[str]) -> None:
    """LIVE ingest: recent-only OpenAQ + forecast met + NRT fires (no S3/archive pull)."""
    from backend.config import require_env_or_halt
    from backend.ingest.firms import ingest_fires
    from backend.ingest.meteo import ingest_meteo
    from backend.ingest.openaq import ingest_latest

    require_env_or_halt()
    for city in cities:
        ingest_latest(city)
        ingest_meteo(city, latest=True)
        ingest_fires(city, latest=True)


def refresh_live(cities: list[str] | None = None) -> dict:
    """LIVE refresh (hourly APScheduler hook / manual trigger): latest-only ingest,
    then re-derive features -> predict -> attribution -> actions. Returns freshness info.
    """
    from backend.actions import simulate as _sim
    from backend.app import deps as _deps
    from backend.config import load_cities

    if cities is None:
        cities = list(load_cities().keys())
    log.info("LIVE refresh for cities: %s", cities)
    t0 = time.time()
    stage_data_latest(cities)
    stage_features(cities)
    stage_predict(cities)
    stage_attribution(cities)
    stage_actions(cities)
    # invalidate API caches so the refreshed snapshots are served immediately
    _deps.read_parquet.cache_clear() if hasattr(_deps.read_parquet, "cache_clear") else None
    _deps._cached_parquet.cache_clear()
    _sim.clear_cache()
    log.info("LIVE refresh done in %.1fs", time.time() - t0)
    return {"cities": cities, "seconds": round(time.time() - t0, 1)}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="VayuNetra pipeline orchestrator")
    parser.add_argument("stage", choices=[*STAGES, "all"], help="pipeline stage to run")
    parser.add_argument("--cities", nargs="+", default=["delhi", "pune"], help="city ids")
    args = parser.parse_args()

    if args.stage == "all":
        run_all(args.cities)
    else:
        _DISPATCH[args.stage](args.cities)


if __name__ == "__main__":
    main()
