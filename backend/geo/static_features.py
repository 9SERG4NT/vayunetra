"""Static per-hex land-use features (BUILD_SPEC §5.2).

For each res-8 hex: road_km (clipped major-road length), industrial_frac,
construction_frac (area fractions), and schools_n / hospitals_n counted within
the hex and its 6 neighbors. Lengths/areas computed in projected CRS EPSG:32643.
"""
from __future__ import annotations

import logging
from collections import Counter

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
from shapely.geometry import Polygon

from backend.config import PROJECTED_CRS, city_config, geo_city_dir
from backend.geo.grid import hex_boundary_lonlat

log = logging.getLogger("vayunetra.geo.static")


def _hex_gdf(grid: pd.DataFrame) -> gpd.GeoDataFrame:
    polys = [Polygon(hex_boundary_lonlat(h)) for h in grid["hex_id"]]
    gdf = gpd.GeoDataFrame(
        {"hex_id": grid["hex_id"].to_numpy()}, geometry=polys, crs="EPSG:4326"
    )
    return gdf.to_crs(PROJECTED_CRS)


def _load_layer(city: str, layer: str) -> gpd.GeoDataFrame:
    path = geo_city_dir(city) / f"osm_{layer}.geojson"
    if not path.exists():
        return gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326").to_crs(PROJECTED_CRS)
    gdf = gpd.read_file(path)
    if gdf.empty or gdf.geometry.isna().all():
        return gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326").to_crs(PROJECTED_CRS)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    return gdf.to_crs(PROJECTED_CRS)


def _clipped_line_km(hexes: gpd.GeoDataFrame, roads: gpd.GeoDataFrame) -> pd.Series:
    """Sum of major-road length (km) clipped into each hex."""
    if roads.empty:
        return pd.Series(0.0, index=hexes["hex_id"])
    inter = gpd.overlay(
        roads[["geometry"]], hexes[["hex_id", "geometry"]], how="intersection", keep_geom_type=True
    )
    if inter.empty:
        return pd.Series(0.0, index=hexes["hex_id"])
    inter["km"] = inter.geometry.length / 1000.0
    return inter.groupby("hex_id")["km"].sum()


def _area_fraction(hexes: gpd.GeoDataFrame, polys: gpd.GeoDataFrame) -> pd.Series:
    """Fraction of each hex covered by the given polygon layer."""
    if polys.empty:
        return pd.Series(0.0, index=hexes["hex_id"])
    inter = gpd.overlay(
        polys[["geometry"]], hexes[["hex_id", "geometry"]], how="intersection", keep_geom_type=True
    )
    if inter.empty:
        return pd.Series(0.0, index=hexes["hex_id"])
    inter["area"] = inter.geometry.area
    covered = inter.groupby("hex_id")["area"].sum()
    hex_area = hexes.set_index("hex_id").geometry.area
    frac = (covered / hex_area).clip(upper=1.0)
    return frac


def _point_counts(grid: pd.DataFrame, points: gpd.GeoDataFrame, res: int) -> pd.Series:
    """Count points within each hex ∪ its 6 neighbors (h3 grid_disk k=1)."""
    if points.empty:
        return pd.Series(0, index=grid["hex_id"])
    pts_wgs = points.to_crs("EPSG:4326")
    cell_of = Counter(
        h3.latlng_to_cell(geom.y, geom.x, res)
        for geom in pts_wgs.geometry
        if geom is not None and not geom.is_empty
    )
    counts = {}
    for hex_id in grid["hex_id"]:
        neighborhood = h3.grid_disk(hex_id, 1)  # hex + 6 neighbors
        counts[hex_id] = int(sum(cell_of.get(c, 0) for c in neighborhood))
    return pd.Series(counts)


def build_static_features(city: str) -> pd.DataFrame:
    """Compute static hex features and persist data/geo/{city}/hex_static.parquet."""
    res = int(city_config(city)["h3_res"])
    grid = pd.read_parquet(geo_city_dir(city) / "grid.parquet")
    hexes = _hex_gdf(grid)

    road_km = _clipped_line_km(hexes, _load_layer(city, "roads_major"))
    ind_frac = _area_fraction(hexes, _load_layer(city, "industrial"))
    con_frac = _area_fraction(hexes, _load_layer(city, "construction"))
    schools_n = _point_counts(grid, _load_layer(city, "schools"), res)
    hospitals_n = _point_counts(grid, _load_layer(city, "hospitals"), res)

    out = grid[["hex_id", "lat", "lng", "locality"]].copy()
    out["road_km"] = out["hex_id"].map(road_km).fillna(0.0).to_numpy()
    out["industrial_frac"] = out["hex_id"].map(ind_frac).fillna(0.0).to_numpy()
    out["construction_frac"] = out["hex_id"].map(con_frac).fillna(0.0).to_numpy()
    out["schools_n"] = out["hex_id"].map(schools_n).fillna(0).astype(int).to_numpy()
    out["hospitals_n"] = out["hex_id"].map(hospitals_n).fillna(0).astype(int).to_numpy()

    path = geo_city_dir(city) / "hex_static.parquet"
    out.to_parquet(path, index=False)
    log.info(
        "[%s] hex_static: %d hexes | roads>0: %d | industrial>0: %d | schools sum: %d",
        city, len(out), int((out.road_km > 0).sum()),
        int((out.industrial_frac > 0).sum()), int(out.schools_n.sum()),
    )
    return out


def summary_table(city: str) -> str:
    df = pd.read_parquet(geo_city_dir(city) / "hex_static.parquet")
    return (
        f"[{city}] hexes={len(df)} road_km_sum={df.road_km.sum():.0f} "
        f"industrial_hexes={(df.industrial_frac > 0).sum()} "
        f"construction_hexes={(df.construction_frac > 0).sum()} "
        f"schools_total={df.schools_n.sum()} hospitals_total={df.hospitals_n.sum()}"
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for c in ("delhi", "pune"):
        build_static_features(c)
        print(summary_table(c))
