"""OSM land-use ingestion via Overpass API (BUILD_SPEC §5.1).

One query per layer per city. Raw JSON cached under data/raw/{city}; parsed
GeoDataFrames written to data/geo/{city}/osm_{layer}.geojson. Overpass is a
non-blocking source: on failure we log a degradation and write an empty layer.
"""
from __future__ import annotations

import json
import logging

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon

from backend.config import city_config, geo_city_dir, raw_dir
from backend.degrade import log_degradation
from backend.ingest.http import HttpError, request

log = logging.getLogger("vayunetra.ingest.overpass")

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# layer -> ("polygon" | "point" | "line")
LAYER_GEOM = {
    "industrial": "polygon",
    "construction": "polygon",
    "schools": "point",
    "hospitals": "point",
    "roads_major": "line",
}


def build_query(layer: str, bbox: list[float]) -> str:
    """Return an Overpass QL query. bbox given W,S,E,N; Overpass wants (S,W,N,E)."""
    w, s, e, n = bbox
    b = f"{s},{w},{n},{e}"
    head = "[out:json][timeout:180];"
    if layer == "industrial":
        return f'{head}(way["landuse"="industrial"]({b});relation["landuse"="industrial"]({b}););out geom;'
    if layer == "construction":
        return (
            f'{head}(way["landuse"="construction"]({b});relation["landuse"="construction"]({b});'
            f'way["building"="construction"]({b}););out geom;'
        )
    if layer == "schools":
        return f'{head}(node["amenity"="school"]({b});way["amenity"="school"]({b}););out center;'
    if layer == "hospitals":
        return f'{head}(node["amenity"="hospital"]({b});way["amenity"="hospital"]({b}););out center;'
    if layer == "roads_major":
        return (
            f'{head}(way["highway"~"^(motorway|trunk|primary|secondary)$"]({b}););out geom;'
        )
    raise ValueError(f"unknown layer {layer}")


def _fetch_raw(city: str, layer: str, query: str) -> dict:
    """Fetch (or load cached) Overpass JSON for a layer, trying both mirrors."""
    cache = raw_dir(city) / f"overpass_{layer}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    last_err: Exception | None = None
    for url in ENDPOINTS:
        try:
            resp = request("POST", url, data={"data": query}, timeout=200)
            data = resp.json()
            cache.write_text(json.dumps(data), encoding="utf-8")
            return data
        except (HttpError, ValueError) as exc:
            last_err = exc
            log.warning("[%s] overpass %s failed on %s: %s", city, layer, url, exc)
    raise HttpError(f"all overpass mirrors failed for {layer}: {last_err}")


def _polygons(elements: list[dict]) -> list[Polygon]:
    polys: list[Polygon] = []
    for el in elements:
        geom = el.get("geometry")
        if geom and len(geom) >= 3:
            ring = [(p["lon"], p["lat"]) for p in geom]
            try:
                polys.append(Polygon(ring))
            except Exception:  # noqa: BLE001 - skip malformed rings
                continue
        for member in el.get("members", []):  # relation outers
            mg = member.get("geometry")
            if member.get("role") == "outer" and mg and len(mg) >= 3:
                try:
                    polys.append(Polygon([(p["lon"], p["lat"]) for p in mg]))
                except Exception:  # noqa: BLE001
                    continue
    return [p for p in polys if p.is_valid and not p.is_empty]


def _points(elements: list[dict]) -> list[Point]:
    pts: list[Point] = []
    for el in elements:
        if el.get("type") == "node" and "lat" in el:
            pts.append(Point(el["lon"], el["lat"]))
        elif "center" in el:
            pts.append(Point(el["center"]["lon"], el["center"]["lat"]))
    return pts


def _lines(elements: list[dict]) -> list[LineString]:
    lines: list[LineString] = []
    for el in elements:
        geom = el.get("geometry")
        if geom and len(geom) >= 2:
            try:
                lines.append(LineString([(p["lon"], p["lat"]) for p in geom]))
            except Exception:  # noqa: BLE001
                continue
    return lines


def _to_gdf(layer: str, data: dict) -> gpd.GeoDataFrame:
    elements = data.get("elements", [])
    kind = LAYER_GEOM[layer]
    if kind == "polygon":
        geoms = _polygons(elements)
    elif kind == "point":
        geoms = _points(elements)
    else:
        geoms = _lines(elements)
    return gpd.GeoDataFrame({"geometry": geoms}, crs="EPSG:4326")


def fetch_layer(city: str, layer: str) -> gpd.GeoDataFrame:
    """Fetch and persist one OSM layer as GeoJSON. Empty on non-blocking failure."""
    out = geo_city_dir(city) / f"osm_{layer}.geojson"
    query = build_query(layer, city_config(city)["bbox"])
    try:
        data = _fetch_raw(city, layer, query)
        gdf = _to_gdf(layer, data)
    except HttpError as exc:
        log_degradation("overpass", f"[{city}] layer '{layer}' unavailable: {exc}. Wrote empty layer.")
        gdf = gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326")
    gdf.to_file(out, driver="GeoJSON")
    log.info("[%s] osm %s: %d features -> %s", city, layer, len(gdf), out.name)
    return gdf


def fetch_all_layers(city: str) -> dict[str, int]:
    """Fetch all OSM layers for a city; return {layer: feature_count}."""
    return {layer: len(fetch_layer(city, layer)) for layer in LAYER_GEOM}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for c in ("delhi", "pune"):
        print(c, fetch_all_layers(c))
