# Forecast metrics — VayuNetra

Rolling-origin backtest: last 8 weeks as four sequential 2-week folds; train strictly before each fold. RMSE/MAE in µg/m³ (pm25). Skill = 1 − RMSE_model/RMSE_persistence.

## delhi

| Horizon | Model RMSE | Persistence RMSE | Climatology RMSE | CAMS RMSE | Model MAE | Skill vs persistence |
|---|---|---|---|---|---|---|
| 24h | 30.2 | 35.3 | 57.1 | 103.7 | 21.4 | +0.143 |
| 48h | 30.2 | 36.7 | 56.9 | 104.6 | 21.9 | +0.177 |
| 72h | 30.3 | 37.9 | 57.2 | 105.1 | 21.8 | +0.202 |

Coverage: 25 stations (25 reference), 234719 pm25 rows, range 2025-03-31 19:00:00+00:00 → 2026-06-28 18:00:00+00:00.

## pune

| Horizon | Model RMSE | Persistence RMSE | Climatology RMSE | CAMS RMSE | Model MAE | Skill vs persistence |
|---|---|---|---|---|---|---|
| 24h | 21.7 | 28.3 | 30.8 | 22.4 | 8.8 | +0.231 |
| 48h | 24.1 | 29.2 | 31.0 | 22.6 | 11.4 | +0.174 |
| 72h | 22.7 | 31.0 | 30.6 | 21.8 | 11.0 | +0.268 |

Coverage: 19 stations (16 reference), 114026 pm25 rows, range 2025-03-31 19:00:00+00:00 → 2026-06-28 18:00:00+00:00.

> Disclosure: hourly AQI proxy computed on hourly concentrations (official CPCB NAQI uses 24-h averages).

## Evidence-pack latency (signal → evidence)

- **delhi**: p50 1767 ms, p90 7858 ms (n=5, target < 30000 ms).

## Triangulation cross-check — biomass Method M vs Method A

On each city's highest-fire attribution day, fraction of high-biomass hexes where the model counterfactual (M) and attribution arithmetic (A) agree within 50%.

- **delhi**: 82.0% agreement over 2863 hexes (day 2025-11-11, efficacy_mid 0.5).
- **pune**: no high-biomass hexes on the replay day (low-fire snapshot).
