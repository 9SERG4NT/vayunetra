"""CPCB National AQI (NAQI) computation (BUILD_SPEC §3.3).

Sub-index by linear interpolation; AQI = max sub-index across pollutants, clamped
0..500. Note (disclosed in UI): this is an hourly AQI proxy on hourly
concentrations — official NAQI uses 24-h averages.

Exact unit-test vectors: pm25 45->75, pm25 120->300, pm25 250->400,
pm10 100->100, pm25 0->0.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.config import load_aqi_breakpoints

_CFG = load_aqi_breakpoints()
BREAKPOINTS: dict[str, list[list[float]]] = {
    "pm25": _CFG["pm25"], "pm10": _CFG["pm10"], "no2": _CFG["no2"],
}
CATEGORIES: list[dict] = _CFG["categories"]


def aqi_subindex(param: str, conc: float) -> int:
    """Rounded integer sub-index for one pollutant concentration (µg/m³)."""
    if conc is None or (isinstance(conc, float) and np.isnan(conc)):
        raise ValueError("concentration is NaN")
    bands = BREAKPOINTS[param]
    for blo, bhi, ilo, ihi in bands:
        if conc <= bhi:
            c = min(max(conc, blo), bhi)
            val = ilo + (ihi - ilo) * (c - blo) / (bhi - blo)
            return int(round(min(max(val, 0.0), 500.0)))
    return 500  # above the top band


def subindex_series(param: str, conc: pd.Series | np.ndarray) -> np.ndarray:
    """Vectorized float sub-index (unrounded) for a concentration array."""
    c = np.asarray(conc, dtype=float)
    out = np.full(c.shape, np.nan)
    for blo, bhi, ilo, ihi in BREAKPOINTS[param]:
        mask = np.isnan(out) & (c <= bhi)
        cc = np.clip(c, blo, bhi)
        out = np.where(mask, ilo + (ihi - ilo) * (cc - blo) / (bhi - blo), out)
    out = np.where(np.isnan(out) & ~np.isnan(c), 500.0, out)  # above top band
    return np.clip(out, 0.0, 500.0)


def category_for(aqi: float) -> tuple[str, str]:
    """Return (label, hex_color) for an AQI value."""
    if aqi is None or (isinstance(aqi, float) and np.isnan(aqi)):
        return ("Unknown", "#64748b")
    for cat in CATEGORIES:
        if aqi <= cat["hi"]:
            return (cat["label"], cat["color"])
    return (CATEGORIES[-1]["label"], CATEGORIES[-1]["color"])


def aqi_from_pollutants(df: pd.DataFrame) -> pd.DataFrame:
    """Given columns among {pm25, pm10, no2}, return aqi / dominant / category.

    AQI = max sub-index; dominant = the pollutant achieving that max.
    """
    params = [p for p in ("pm25", "pm10", "no2") if p in df.columns]
    if not params:
        raise ValueError("aqi_from_pollutants needs at least one of pm25/pm10/no2")

    subs = {p: subindex_series(p, df[p]) for p in params}
    stacked = np.vstack([subs[p] for p in params])  # (n_params, n_rows)
    all_nan = np.isnan(stacked).all(axis=0)
    safe = np.where(np.isnan(stacked), -np.inf, stacked)
    aqi = np.where(all_nan, np.nan, safe.max(axis=0))
    dom_idx = safe.argmax(axis=0)
    dominant = np.array(params)[dom_idx]
    aqi = np.where(all_nan, np.nan, np.round(aqi))
    labels = [category_for(a)[0] if not np.isnan(a) else "Unknown" for a in aqi]
    colors = [category_for(a)[1] if not np.isnan(a) else "#64748b" for a in aqi]
    dominant = np.where(all_nan, "", dominant)

    return pd.DataFrame(
        {"aqi": aqi, "dominant": dominant, "category": labels, "color": colors},
        index=df.index,
    )
