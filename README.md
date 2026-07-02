# VayuNetra — Urban Air Quality Intelligence

**Signal → attribution → forecast → court-ready enforcement evidence, in seconds.**
Built for the ET AI Hackathon 2.0 · PS 5. Two live cities (Delhi NCT + Pune/PCMC),
zero new sensors, no fabricated data.

> The data exists. The intelligence layer to act on it does not. VayuNetra *is* that layer:
> the closed loop from a monitoring signal to a prioritised, evidence-backed intervention.

![screenshot placeholder](docs/screenshot-command.png)
![screenshot placeholder](docs/screenshot-actions.png)

## What it does
- **Attribution** — hourly, per-hex source shares across biomass / traffic / industry /
  construction dust / background, with a confidence badge. Triangulated from TreeSHAP
  (temporal), spatial ridge on land-use (spatial), and wind-sector lift (directional).
- **Forecasting** — 24/48/72-h pm25 forecasts (LightGBM) with prediction intervals,
  IDW-interpolated onto a ~1 km H3 grid; honest backtests vs persistence, climatology, CAMS.
- **Enforcement** — a ranked action queue (share × severity × persistence × exposure ×
  actionability) and a one-click **evidence pack** (map, trend, fire table, wind-sector
  lift, draft notice, PRANA reporting stub) generated in seconds.
- **Advisory** — citizen health advisories in English / Hindi / Marathi (numbers never
  LLM-generated; optional LLM polish).
- **GRAP** — Delhi GRAP stage plus a 48-h predicted stage.

## Stack
Python 3.11+ (uv) · FastAPI · Parquet + DuckDB · geopandas + H3 · LightGBM ·
matplotlib/fpdf2 (evidence) · Vite + React + TypeScript · MapLibre GL + deck.gl · Recharts.

## Quickstart
```bash
cp .env.example .env          # add the two required keys (see below)
make setup                    # uv sync + frontend npm install
make pipeline                 # geo → data → features → train → evaluate → predict → attribution → actions → validate
make demo                     # API on :8000, UI on :5173
```
Open http://localhost:5173. The UI runs fully offline from `data/snapshots/` — no live
keys are needed at demo time.

### Required keys (both free, ~2 min each)
| Key | Where | Used for |
|---|---|---|
| `OPENAQ_API_KEY` | https://explore.openaq.org/register | CPCB station history + latest (blocking) |
| `FIRMS_MAP_KEY` | https://firms.modaps.eosdis.nasa.gov/api/map_key/ | VIIRS active-fire detections (blocking) |

Optional: `DATA_GOV_IN_API_KEY` (CPCB live cross-check), `LLM_PROVIDER=nim|anthropic`
(+ keys) for advisory polish. Open-Meteo and OpenStreetMap need no key.

## Data sources & licences
| Source | Licence | Role |
|---|---|---|
| OpenAQ (mirrors CPCB) | CC BY 4.0 | station measurements |
| NASA FIRMS VIIRS | NASA open data | fire detections |
| Open-Meteo (ERA5 / forecast / CAMS) | CC BY 4.0 / free tier | meteorology + AQ baseline |
| OpenStreetMap (Overpass) | ODbL | land use (industrial, roads, schools, hospitals) |
| CARTO basemap | © OpenStreetMap © CARTO | map tiles |

## Metrics (real backtest, this build)
Rolling-origin, 4 × 2-week folds. RMSE in µg/m³ (pm25); skill = 1 − RMSE_model/RMSE_persistence.

| City | 24h skill | 48h skill | 72h skill |
|---|---|---|---|
| Delhi | +0.143 | +0.177 | +0.202 |
| Pune | +0.231 | — | — |

The model beats persistence, climatology and raw CAMS at every horizon. See
[docs/metrics.md](docs/metrics.md) for the full table and coverage, and
[docs/DIAGNOSIS.md](docs/DIAGNOSIS.md) where the 24h Delhi skill falls short of the
0.25 target — reported, not hidden.

## Honest limitations
- **Attribution is evidence-weighted, confidence-scored estimation — not regulatory
  source apportionment** (which needs chemical speciation). Every number carries a
  confidence badge and this disclaimer.
- The AQI shown is an **hourly proxy** on hourly concentrations; official CPCB NAQI uses
  24-h averages. Disclosed in the UI footer and every evidence pack.
- 24h Delhi skill (0.143) is below the 0.25 target — persistence is a strong PM2.5
  baseline over a 15-month window. See DIAGNOSIS.md.
- Pune rarely exceeds AQI 200, so its enforcement queue is often empty — the honest,
  cleaner-city outcome, and proof the pipeline generalises.

## What a human still needs to do
Record the demo video · build the deck · deploy (Render/Vercel) · verify the Unstop
Phase-2 deadline.

## Make targets
`setup · geo · data · features · train · evaluate · predict · attribution · actions ·
pipeline · api · ui · demo · test · snapshot`
