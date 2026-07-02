"""LightGBM forecast training (BUILD_SPEC §8.2).

One regressor per (city, horizon) for pm25, fixed params, early stopping on a
chronological validation split. Final models train on all available data and are
saved for inference. Rolling-origin metrics live in evaluate.py.
"""
from __future__ import annotations

import logging

import lightgbm as lgb

from backend.models.dataset import (
    FEATURE_COLUMNS, HORIZONS, LGB_PARAMS, load_panel, model_dir, val_split, xy,
)

log = logging.getLogger("vayunetra.models.train")


def fit_booster(train_df, horizon: int) -> lgb.LGBMRegressor:
    """Fit one LightGBM regressor for a horizon with early stopping."""
    tr, va = val_split(train_df)
    X_tr, y_tr, _ = xy(tr, horizon)
    X_va, y_va, _ = xy(va, horizon)
    model = lgb.LGBMRegressor(**LGB_PARAMS)
    callbacks = [lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)]
    if len(X_va) >= 50:
        model.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], eval_metric="rmse", callbacks=callbacks)
    else:  # too little validation data — fit without early stopping
        model.fit(X_tr, y_tr)
    return model


def train_city(city: str) -> dict[str, int]:
    """Train + persist final pm25 models for all horizons."""
    panel = load_panel(city)
    mdir = model_dir(city)
    trained = 0
    for h in HORIZONS:
        X, y, _ = xy(panel, h)
        if len(X) < 200:
            log.warning("[%s] horizon %dh: only %d rows; skipping", city, h, len(X))
            continue
        model = fit_booster(panel, h)
        model.booster_.save_model(str(mdir / f"pm25_h{h}.txt"))
        trained += 1
        log.info("[%s] trained pm25 h%d on %d rows (best_iter=%s)",
                 city, h, len(X), getattr(model, "best_iteration_", None))
    (mdir / "feature_columns.txt").write_text("\n".join(FEATURE_COLUMNS), encoding="utf-8")
    return {"models": trained}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for c in ("delhi", "pune"):
        print(c, train_city(c))
