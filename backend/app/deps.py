"""API data-access helpers.

Reads offline snapshots (Parquet/JSON). DuckDB is used for the filtered Parquet
queries (grid by timestamp, fires by window); small JSON/metrics files load directly.
A tiny mtime-keyed cache avoids re-reading large Parquet on every request.
"""
from __future__ import annotations

import json
from functools import lru_cache

import duckdb
import pandas as pd
from fastapi import HTTPException

from backend.config import geo_city_dir, load_cities, snap_dir

_DUCK = duckdb.connect(database=":memory:")


def validate_city(city: str) -> str:
    if city not in load_cities():
        raise HTTPException(status_code=404, detail=f"unknown city '{city}'")
    return city


def snap_file(city: str, name: str):
    return snap_dir(city) / name


def geo_file(city: str, name: str):
    return geo_city_dir(city) / name


@lru_cache(maxsize=64)
def _cached_parquet(path_str: str, mtime: float) -> pd.DataFrame:
    return pd.read_parquet(path_str)


def read_parquet(path) -> pd.DataFrame:
    """Read a Parquet file with an mtime-keyed cache; empty frame if absent."""
    if not path.exists():
        return pd.DataFrame()
    return _cached_parquet(str(path), path.stat().st_mtime).copy()


def read_json(path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def duck_query(sql: str, params: list) -> pd.DataFrame:
    """Run a DuckDB query (parquet paths embedded in SQL) and return a DataFrame."""
    return _DUCK.execute(sql, params).df()


def require_file(path, hint: str):
    if not path.exists():
        raise HTTPException(status_code=503, detail=f"{hint} not available yet — run the pipeline.")
    return path
