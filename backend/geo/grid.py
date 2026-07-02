"""H3 res-8 grid construction (BUILD_SPEC §3.2).

Builds every res-8 cell whose area intersects the city bbox, labels each hex with
its nearest well-known locality (no external geocoding), and writes grid.parquet.
"""
from __future__ import annotations

import logging

import h3
import numpy as np
import pandas as pd

from backend.config import city_config, geo_city_dir

log = logging.getLogger("vayunetra.geo.grid")

# Hardcoded landmark localities per city: name -> (lat, lng). Used only to give
# each hex a friendly label; never used as a data source.
LANDMARKS: dict[str, dict[str, tuple[float, float]]] = {
    "delhi": {
        "Anand Vihar": (28.6469, 77.3159),
        "ITO": (28.6289, 77.2410),
        "RK Puram": (28.5645, 77.1750),
        "Dwarka": (28.5921, 77.0460),
        "Rohini": (28.7361, 77.0910),
        "Okhla": (28.5305, 77.2730),
        "Punjabi Bagh": (28.6740, 77.1310),
        "Shadipur": (28.6510, 77.1580),
        "Jahangirpuri": (28.7290, 77.0630),
        "Nehru Nagar": (28.5680, 77.2510),
        "Bawana": (28.7990, 77.0320),
        "Mundka": (28.6820, 77.0300),
        "Najafgarh": (28.6090, 76.9800),
        "Sonia Vihar": (28.7150, 77.2500),
        "Lodhi Road": (28.5910, 77.2270),
    },
    "pune": {
        "Shivajinagar": (18.5308, 73.8475),
        "Kothrud": (18.5074, 73.8077),
        "Hadapsar": (18.5089, 73.9260),
        "Katraj": (18.4529, 73.8600),
        "Bhosari": (18.6298, 73.8470),
        "Nigdi": (18.6510, 73.7690),
        "Hinjewadi": (18.5913, 73.7389),
        "Karve Road": (18.5010, 73.8300),
        "Pashan": (18.5380, 73.7900),
        "Viman Nagar": (18.5679, 73.9143),
        "Kharadi": (18.5510, 73.9410),
        "Chinchwad": (18.6420, 73.7990),
    },
}


def _haversine_km(lat1: np.ndarray, lng1: np.ndarray, lat2: float, lng2: float) -> np.ndarray:
    """Vectorized haversine distance (km) from many points to one point."""
    r = 6371.0088
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lng2 - lng1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def _nearest_localities(lats: np.ndarray, lngs: np.ndarray, city: str) -> list[str]:
    marks = LANDMARKS.get(city, {})
    if not marks:
        return ["" for _ in lats]
    names = list(marks.keys())
    dists = np.column_stack(
        [_haversine_km(lats, lngs, marks[n][0], marks[n][1]) for n in names]
    )
    idx = dists.argmin(axis=1)
    return [names[i] for i in idx]


def build_grid(city: str) -> pd.DataFrame:
    """Build the H3 grid for a city and persist data/geo/{city}/grid.parquet."""
    cfg = city_config(city)
    w, s, e, n = cfg["bbox"]
    res = int(cfg["h3_res"])

    poly = h3.LatLngPoly([(s, w), (n, w), (n, e), (s, e)])
    cells = list(h3.polygon_to_cells(poly, res))
    if not cells:
        raise RuntimeError(f"H3 produced no cells for {city} bbox {cfg['bbox']}")

    centroids = np.array([h3.cell_to_latlng(c) for c in cells], dtype=float)
    lats, lngs = centroids[:, 0], centroids[:, 1]
    localities = _nearest_localities(lats, lngs, city)

    df = pd.DataFrame(
        {"hex_id": cells, "lat": lats, "lng": lngs, "locality": localities}
    ).sort_values("hex_id", ignore_index=True)

    out = geo_city_dir(city) / "grid.parquet"
    df.to_parquet(out, index=False)
    log.info("[%s] grid: %d hexes (res %d) -> %s", city, len(df), res, out.name)
    return df


def hex_boundary_lonlat(hex_id: str) -> list[tuple[float, float]]:
    """Return the hex boundary as (lng, lat) pairs for shapely Polygon construction."""
    return [(lng, lat) for lat, lng in h3.cell_to_boundary(hex_id)]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for c in ("delhi", "pune"):
        build_grid(c)
