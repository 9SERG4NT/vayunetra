"""Central configuration: paths, environment, and static YAML config loaders.

Every module imports from here so paths and settings are defined once.
All times are UTC internally; IST conversion happens only in the UI / evidence packs.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# --- Paths -----------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
GEO_DIR = DATA_DIR / "geo"
SNAP_DIR = DATA_DIR / "snapshots"
DOCS_DIR = ROOT / "docs"

# Load .env once at import time (no-op if the file is absent).
load_dotenv(ROOT / ".env")

IST_OFFSET_MINUTES = 330  # +05:30


def _as_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Runtime settings sourced from environment variables."""

    openaq_api_key: str = os.getenv("OPENAQ_API_KEY", "").strip()
    firms_map_key: str = os.getenv("FIRMS_MAP_KEY", "").strip()
    data_gov_in_api_key: str = os.getenv("DATA_GOV_IN_API_KEY", "").strip()
    tomtom_api_key: str = os.getenv("TOMTOM_API_KEY", "").strip()
    llm_provider: str = os.getenv("LLM_PROVIDER", "none").strip() or "none"
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "").strip()
    nim_base_url: str = os.getenv("NIM_BASE_URL", "").strip()
    nim_api_key: str = os.getenv("NIM_API_KEY", "").strip()
    nim_model: str = os.getenv("NIM_MODEL", "meta/llama-3.1-70b-instruct").strip()
    live_mode: bool = os.getenv("LIVE_MODE", "0").strip() in {"1", "true", "True"}
    history_start: str = os.getenv("HISTORY_START", "2025-04-01").strip() or "2025-04-01"
    max_stations_per_city: int = _as_int("MAX_STATIONS_PER_CITY", 25)


settings = Settings()

# Data-quality / runtime caps (see BUILD_SPEC §1.3).
HISTORY_MONTHS = 15
MAX_VALID_CONCENTRATION = 1500.0  # µg/m³ — drop physically implausible readings
MISSING_HOUR_DROP_THRESHOLD = 0.60  # drop a station if >60% of pm25 hours missing
PROJECTED_CRS = "EPSG:32643"  # UTM 43N — for lengths/areas over Delhi & Pune


def check_required_env() -> list[str]:
    """Return a list of missing REQUIRED env vars (empty means all present)."""
    missing = []
    if not settings.openaq_api_key:
        missing.append("OPENAQ_API_KEY")
    if not settings.firms_map_key:
        missing.append("FIRMS_MAP_KEY")
    return missing


def require_env_or_halt() -> None:
    """Halt the pipeline with a clear message if required keys are absent."""
    missing = check_required_env()
    if missing:
        raise SystemExit(
            "HALT (BUILD_SPEC §1.3): missing required environment variable(s): "
            + ", ".join(missing)
            + "\n  Add them to .env (copy from .env.example):\n"
            "    OPENAQ_API_KEY  -> https://explore.openaq.org/register\n"
            "    FIRMS_MAP_KEY   -> https://firms.modaps.eosdis.nasa.gov/api/map_key/"
        )


# --- YAML config loaders (cached) -----------------------------------------
@lru_cache(maxsize=1)
def load_cities() -> dict[str, dict[str, Any]]:
    with open(CONFIG_DIR / "cities.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_aqi_breakpoints() -> dict[str, Any]:
    with open(CONFIG_DIR / "aqi_breakpoints.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_grap() -> dict[str, Any]:
    with open(CONFIG_DIR / "grap.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def city_config(city: str) -> dict[str, Any]:
    cities = load_cities()
    if city not in cities:
        raise KeyError(f"Unknown city '{city}'. Known: {sorted(cities)}")
    return cities[city]


# --- Per-city directory helpers (created on demand) ------------------------
def raw_dir(city: str) -> Path:
    p = RAW_DIR / city
    p.mkdir(parents=True, exist_ok=True)
    return p


def geo_city_dir(city: str) -> Path:
    p = GEO_DIR / city
    p.mkdir(parents=True, exist_ok=True)
    return p


def snap_dir(city: str) -> Path:
    p = SNAP_DIR / city
    p.mkdir(parents=True, exist_ok=True)
    return p
