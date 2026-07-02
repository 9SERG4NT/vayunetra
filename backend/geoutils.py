"""Vectorized geodesy helpers (haversine distance, initial bearing, angle wrap).

Used by feature engineering, attribution, and evidence packs so the fire-geometry
math is defined once.
"""
from __future__ import annotations

import numpy as np

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1, lng1, lat2, lng2) -> np.ndarray:
    """Great-circle distance in km. Inputs broadcast (scalars or arrays)."""
    lat1, lng1, lat2, lng2 = map(np.asarray, (lat1, lng1, lat2, lng2))
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lng2 - lng1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def initial_bearing_deg(lat1, lng1, lat2, lng2) -> np.ndarray:
    """Initial bearing (degrees, 0-360) from point 1 to point 2. Broadcasts."""
    lat1, lng1, lat2, lng2 = map(np.asarray, (lat1, lng1, lat2, lng2))
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dlmb = np.radians(lng2 - lng1)
    x = np.sin(dlmb) * np.cos(p2)
    y = np.cos(p1) * np.sin(p2) - np.sin(p1) * np.cos(p2) * np.cos(dlmb)
    return (np.degrees(np.arctan2(x, y)) + 360.0) % 360.0


def wrap_deg(x) -> np.ndarray:
    """Wrap an angle difference to [-180, 180]."""
    return (np.asarray(x, dtype=float) + 180.0) % 360.0 - 180.0
