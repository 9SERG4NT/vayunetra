"""Source attribution engine (BUILD_SPEC §8.3) — the innovation.

Triangulated recipe per hex per materialized timestamp:
  1. Temporal decomposition via TreeSHAP on the 24h model (grouped feature shares).
  2. Spatial decomposition via ridge regression on land-use covariates.
  3. Combine into 5 sources + a separately-reported meteorology_modifier.
  4. Wind-sector lift as a directional confidence cross-check.
  5. Confidence badge (high/medium/low).
-> attribution.parquet (wide: one row per ts_utc,hex_id; shares sum to 1±1e-3).
"""
from __future__ import annotations

import json
import logging

import geopandas as gpd
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from backend.config import city_config, geo_city_dir, snap_dir
from backend.features.build import FEATURE_COLUMNS
from backend.geoutils import haversine_km, initial_bearing_deg, wrap_deg
from backend.models.dataset import model_dir

log = logging.getLogger("vayunetra.models.attribution")

SOURCES = ["biomass", "traffic", "industry", "construction_dust", "background"]
SPATIAL_COVARIATES = ["road_km", "industrial_frac", "construction_frac"]
LIFT_THRESHOLD = 1.3
CONF_DIST_KM = 8.0
CONF_MIN_HOURS = 600
LIFT_HALF_ANGLE = 45.0

FEATURE_GROUPS = {
    "biomass": ["fire_load_upwind_24", "fire_count_radius_24"],
    "meteorology": ["temp", "rh", "precip", "pressure", "wind_speed", "wind_u", "wind_v", "blh"],
    "activity": ["hour_sin", "hour_cos", "dow", "is_weekend", "month", "festival_window"],
    "background": ["pm25_lag_1", "pm25_lag_3", "pm25_lag_6", "pm25_lag_12", "pm25_lag_24",
                   "pm25_lag_48", "pm25_roll_mean_24", "pm25_roll_max_24",
                   "pm10_lag_1", "pm10_lag_24", "pm10_roll_mean_24"],
}
_GROUP_IDX = {g: [FEATURE_COLUMNS.index(c) for c in cols] for g, cols in FEATURE_GROUPS.items()}


def _wind_dir_from(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Recover meteorological wind_from direction (deg) from u/v components."""
    return (np.degrees(np.arctan2(-u, -v)) + 360.0) % 360.0


def _temporal_shares(model: lgb.Booster, x_row: pd.DataFrame) -> dict[str, float]:
    """Grouped |SHAP| shares (biomass/met/activity/background) at one feature row."""
    contrib = model.predict(x_row[FEATURE_COLUMNS].to_numpy(), pred_contrib=True)[0]
    abs_c = np.abs(contrib[:-1])  # drop base value
    sums = {g: float(abs_c[idx].sum()) for g, idx in _GROUP_IDX.items()}
    total = sum(sums.values()) or 1.0
    return {g: s / total for g, s in sums.items()}


def _spatial_weights(nowcast_t: pd.DataFrame, static: pd.DataFrame) -> pd.DataFrame:
    """Ridge decomposition -> per-hex [traffic, industry, construction, residual] weights."""
    df = nowcast_t.merge(static[["hex_id", *SPATIAL_COVARIATES]], on="hex_id", how="left").fillna(0.0)
    pm = df["pm25"].to_numpy(dtype=float)
    valid = pm > 0
    city_mean = np.nanmean(pm[valid]) if valid.any() else 1.0
    y = np.log(np.clip(pm / max(city_mean, 1e-6), 1e-3, None))

    Z = df[SPATIAL_COVARIATES].to_numpy(dtype=float)
    mu, sd = Z.mean(axis=0), Z.std(axis=0)
    sd[sd == 0] = 1.0
    Zs = (Z - mu) / sd
    coef = Ridge(alpha=1.0).fit(Zs[valid], y[valid]).coef_ if valid.sum() > 5 else np.zeros(3)

    contrib = np.clip(Zs * coef, 0.0, None)  # (n_hex, 3) non-negative
    residual = np.ones((len(df), 1))
    stacked = np.hstack([contrib, residual])
    weights = stacked / stacked.sum(axis=1, keepdims=True)
    return pd.DataFrame({"hex_id": df["hex_id"].to_numpy(),
                         "w_traffic": weights[:, 0], "w_industry": weights[:, 1],
                         "w_construction": weights[:, 2], "w_residual": weights[:, 3]})


def _industrial_centroids(city: str) -> np.ndarray:
    path = geo_city_dir(city) / "osm_industrial.geojson"
    if not path.exists():
        return np.empty((0, 2))
    gdf = gpd.read_file(path)
    if gdf.empty:
        return np.empty((0, 2))
    cent = gdf.geometry.representative_point()
    return np.column_stack([cent.y.to_numpy(), cent.x.to_numpy()])


def _sector_lift(pm25: np.ndarray, wind_from: np.ndarray, bearing: float) -> float:
    """P(pm25>p75 | wind within ±45° of bearing) / P(pm25>p75)."""
    mask = ~np.isnan(pm25) & ~np.isnan(wind_from)
    if mask.sum() < 50 or np.isnan(bearing):
        return float("nan")
    p, w = pm25[mask], wind_from[mask]
    p75 = np.percentile(p, 75)
    base = np.mean(p > p75)
    cond = np.abs(wrap_deg(w - bearing)) <= LIFT_HALF_ANGLE
    if cond.sum() < 10 or base == 0:
        return float("nan")
    return float(np.mean(p[cond] > p75) / base)


def _station_context(city: str, panel: pd.DataFrame, fires: pd.DataFrame,
                     ind_cent: np.ndarray, t: pd.Timestamp, radius_km: float) -> dict[int, dict]:
    """Per-station lift/evidence over trailing windows ending at t."""
    win30 = t - pd.Timedelta(days=30)
    win7 = t - pd.Timedelta(days=7)
    ctx = {}
    for sid, g in panel.groupby("station_id"):
        g = g[(g["ts_utc"] <= t) & (g["ts_utc"] > win30)]
        pm = g["pm25"].to_numpy(dtype=float)
        wdir = _wind_dir_from(g["wind_u"].to_numpy(dtype=float), g["wind_v"].to_numpy(dtype=float))
        slat, slng = g.iloc[0]["lat"], g.iloc[0]["lng"] if len(g) else (np.nan, np.nan)
        valid_hours = int(np.sum(~np.isnan(pm)))

        # biomass geometry: trailing-7d fire centroid within radius
        fire_bear, fire_n, frp_sum = np.nan, 0, 0.0
        if not fires.empty:
            f = fires[(fires["ts_utc"] <= t) & (fires["ts_utc"] > win7)]
            d = haversine_km(slat, slng, f["lat"].to_numpy(), f["lng"].to_numpy()) if len(f) else np.array([])
            near = d <= radius_km if len(d) else np.array([], dtype=bool)
            if near.any():
                fl, fg = f["lat"].to_numpy()[near], f["lng"].to_numpy()[near]
                fire_bear = float(initial_bearing_deg(slat, slng, fl.mean(), fg.mean()))
                fire_n, frp_sum = int(near.sum()), float(f["frp"].to_numpy()[near].sum())
        ind_bear = np.nan
        if len(ind_cent):
            di = haversine_km(slat, slng, ind_cent[:, 0], ind_cent[:, 1])
            j = int(np.argmin(di))
            ind_bear = float(initial_bearing_deg(slat, slng, ind_cent[j, 0], ind_cent[j, 1]))

        ctx[int(sid)] = {
            "biomass_lift": _sector_lift(pm, wdir, fire_bear),
            "industry_lift": _sector_lift(pm, wdir, ind_bear),
            "valid_hours": valid_hours, "fire_n": fire_n, "frp_sum": frp_sum,
            "mean_bearing": fire_bear,
        }
    return ctx


def combine_shares(temporal: dict[str, float], w: dict[str, float]) -> dict[str, float]:
    """Combine temporal shares + spatial weights into 5 normalized source shares.

    biomass = biomass_t; (activity+background) distributed by spatial weights
    (residual -> background); renormalized to sum to 1. Meteorology reported separately.
    """
    pool = temporal["activity"] + temporal["background"]
    five = {"biomass": temporal["biomass"], "traffic": pool * w["w_traffic"],
            "industry": pool * w["w_industry"], "construction_dust": pool * w["w_construction"],
            "background": pool * w["w_residual"]}
    s = sum(five.values()) or 1.0
    return {k: max(v / s, 0.0) for k, v in five.items()}


def _confidence(top_source: str, ctx: dict, dist_km: float) -> str:
    lift = ctx.get(f"{top_source}_lift", float("nan"))
    c1 = top_source not in ("biomass", "industry") or (not np.isnan(lift) and lift >= LIFT_THRESHOLD)
    c2 = dist_km < CONF_DIST_KM
    c3 = ctx.get("valid_hours", 0) >= CONF_MIN_HOURS
    score = int(c1) + int(c2) + int(c3)
    return "high" if score == 3 else "medium" if score == 2 else "low"


def _materialized_timestamps(city: str, nowcast: pd.DataFrame) -> list[pd.Timestamp]:
    stamps = [nowcast["ts_utc"].max()]
    for preset in city_config(city).get("replay_presets", []):
        start = pd.Timestamp(preset["start"], tz="UTC")
        end = pd.Timestamp(preset["end"] + " 23:00", tz="UTC")
        win = nowcast[(nowcast["ts_utc"] >= start) & (nowcast["ts_utc"] <= end)]
        if not win.empty:
            peak_ts = win.groupby("ts_utc")["pm25"].median().idxmax()
            stamps.append(peak_ts)
    return list(dict.fromkeys(stamps))


def attribute_city(city: str) -> dict:
    sdir = snap_dir(city)
    panel = pd.read_parquet(sdir / "features.parquet")
    panel["ts_utc"] = pd.to_datetime(panel["ts_utc"], utc=True)
    nowcast = pd.read_parquet(sdir / "hex_nowcast.parquet")
    nowcast["ts_utc"] = pd.to_datetime(nowcast["ts_utc"], utc=True)
    static = pd.read_parquet(geo_city_dir(city) / "hex_static.parquet")
    fires = pd.read_parquet(sdir / "fires.parquet") if (sdir / "fires.parquet").exists() else pd.DataFrame()
    if not fires.empty:
        fires["ts_utc"] = pd.to_datetime(fires["ts_utc"], utc=True)
    model = lgb.Booster(model_file=str(model_dir(city) / "pm25_h24.txt"))
    ind_cent = _industrial_centroids(city)
    radius_km = float(city_config(city)["fire_radius_km"])

    rows = []
    for t in _materialized_timestamps(city, nowcast):
        rows.extend(_attribute_at(city, t, panel, nowcast, static, fires, model, ind_cent, radius_km))
    out = pd.DataFrame(rows)
    out.to_parquet(sdir / "attribution.parquet", index=False)
    log.info("[%s] attribution rows=%d timestamps=%d", city, len(out),
             out["ts_utc"].nunique() if not out.empty else 0)
    return {"rows": len(out)}


def _attribute_at(city, t, panel, nowcast, static, fires, model, ind_cent, radius_km) -> list[dict]:
    station_rows = panel[panel["ts_utc"] == t]
    if station_rows.empty:
        return []
    ctx = _station_context(city, panel, fires, ind_cent, t, radius_km)
    shares_by_station = {int(r["station_id"]): _temporal_shares(model, station_rows.loc[[i]])
                         for i, r in station_rows.iterrows()}
    st = station_rows.drop_duplicates("station_id")[["station_id", "lat", "lng"]].reset_index(drop=True)

    now_t = nowcast[nowcast["ts_utc"] == t]
    if now_t.empty:
        return []
    weights = _spatial_weights(now_t, static).set_index("hex_id")
    hexes = now_t.merge(static[["hex_id", "lat", "lng"]], on="hex_id", how="left")

    d = haversine_km(hexes["lat"].to_numpy()[:, None], hexes["lng"].to_numpy()[:, None],
                     st["lat"].to_numpy()[None, :], st["lng"].to_numpy()[None, :])
    nearest = d.argmin(axis=1)
    nearest_km = d.min(axis=1)

    out = []
    for k, hx in enumerate(hexes["hex_id"].to_numpy()):
        sid = int(st.iloc[nearest[k]]["station_id"])
        ts = shares_by_station[sid]
        five = combine_shares(ts, weights.loc[hx].to_dict())
        top = max(five, key=five.get)
        cx = ctx.get(sid, {})
        out.append({
            "ts_utc": t, "hex_id": hx, **five,
            "met_modifier": ts["meteorology"], "confidence": _confidence(top, cx, float(nearest_km[k])),
            "evidence_json": json.dumps({
                "fire_n": cx.get("fire_n", 0), "frp_sum": round(cx.get("frp_sum", 0.0), 1),
                "mean_bearing": None if np.isnan(cx.get("mean_bearing", np.nan)) else round(cx["mean_bearing"], 1),
                "biomass_lift": None if np.isnan(cx.get("biomass_lift", np.nan)) else round(cx["biomass_lift"], 2),
                "industry_lift": None if np.isnan(cx.get("industry_lift", np.nan)) else round(cx["industry_lift"], 2),
                "station_km": round(float(nearest_km[k]), 2), "station_id": sid,
            }),
        })
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for c in ("delhi", "pune"):
        print(c, attribute_city(c))
