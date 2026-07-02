"""Shared dataset helpers for training / evaluation / inference.

Loads the station-hour panel, exposes the fixed LightGBM params, the feature
matrix, and the rolling-origin fold generator (BUILD_SPEC §8.2).
"""
from __future__ import annotations

import pandas as pd

from backend.config import snap_dir
from backend.features.build import FEATURE_COLUMNS, HORIZONS

__all__ = ["FEATURE_COLUMNS", "HORIZONS", "LGB_PARAMS", "load_panel", "xy",
           "rolling_folds", "val_split", "model_dir"]

LGB_PARAMS = dict(
    objective="regression",
    n_estimators=600,
    learning_rate=0.05,
    num_leaves=63,
    min_child_samples=40,
    subsample=0.9,
    colsample_bytree=0.9,
    random_state=42,
    n_jobs=-1,
    verbose=-1,
)

FOLD_WEEKS = 2
N_FOLDS = 4


def model_dir(city: str):
    d = snap_dir(city) / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_panel(city: str) -> pd.DataFrame:
    df = pd.read_parquet(snap_dir(city) / "features.parquet")
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True)
    return df.sort_values(["station_id", "ts_utc"]).reset_index(drop=True)


def xy(df: pd.DataFrame, horizon: int):
    """Return (X, y) for a horizon, dropping rows with a missing target."""
    target = f"y_{horizon}"
    valid = df[target].notna()
    return df.loc[valid, FEATURE_COLUMNS], df.loc[valid, target], df.loc[valid]


def val_split(train: pd.DataFrame, frac: float = 0.15):
    """Chronological validation split for early stopping (last `frac` by time)."""
    train = train.sort_values("ts_utc")
    cut = int(len(train) * (1 - frac))
    return train.iloc[:cut], train.iloc[cut:]


def rolling_folds(df: pd.DataFrame):
    """Yield (train, test) for the last N_FOLDS sequential 2-week test folds.

    Train is everything strictly before each fold's start (BUILD_SPEC §8.2).
    """
    tmax = df["ts_utc"].max()
    fold_span = pd.Timedelta(weeks=FOLD_WEEKS)
    window_start = tmax - fold_span * N_FOLDS
    for i in range(N_FOLDS):
        fold_start = window_start + fold_span * i
        fold_end = fold_start + fold_span
        train = df[df["ts_utc"] < fold_start]
        test = df[(df["ts_utc"] >= fold_start) & (df["ts_utc"] < fold_end)]
        if len(train) and len(test):
            yield i, train, test
