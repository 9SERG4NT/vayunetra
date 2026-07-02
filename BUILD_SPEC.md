# VAYUNETRA — ONE-SHOT BUILD SPEC FOR CLAUDE CODE
### ET AI Hackathon 2.0 · PS 5 · Urban Air Quality Intelligence
Version 1.0 · 2 Jul 2026 · Target: fully working prototype from an empty folder in one agent run.

---

## HOW TO USE THIS FILE (human instructions — 10 minutes of your time)

**Step 1 — Get 2 mandatory API keys (both free, ~2 min each):**
1. **OpenAQ**: register at https://explore.openaq.org/register → key appears in account settings. Used for ALL historical + latest station data (OpenAQ mirrors CPCB stations, so data.gov.in becomes optional).
2. **NASA FIRMS MAP_KEY**: https://firms.modaps.eosdis.nasa.gov/api/map_key/ → key emailed instantly. Limit: 5,000 transactions/10 min (we use ~150 total).

Optional keys (skip for v1): `DATA_GOV_IN_API_KEY` (https://data.gov.in — CPCB live cross-check), `TOMTOM_API_KEY` (live traffic), `ANTHROPIC_API_KEY` or NVIDIA NIM creds (LLM-polished advisories; deterministic templates work without any key).

**Step 2 — Kick off:**
```bash
mkdir vayunetra && cd vayunetra && git init
# put this file in the repo root as BUILD_SPEC.md
# create .env with your two keys (see §2.3)
claude
```
Then paste this prompt into Claude Code:

> Read BUILD_SPEC.md fully. Execute Phases 0 through 10 strictly in order, following the EXECUTION PROTOCOL in §1. After each phase, run its acceptance checks and make a git commit `phase-N: <summary>`. Do not skip acceptance checks. Do not fabricate data. If something external fails, follow the failure rules in §1.3. At the end, print the DONE CHECKLIST from §14 with pass/fail per item.

**Step 3 — After the run:** review `docs/metrics.md`, click through the UI (`make demo`), record the demo video, build the deck (deck outline is in the previous planning doc, not here — this file is code-only).

---

## §1. EXECUTION PROTOCOL (rules for the agent)

### 1.1 Order & discipline
- Execute phases 0→10 sequentially. A phase is complete only when its **Acceptance** block passes.
- Commit after every phase. Small, working increments. Never leave the repo in a non-running state at a phase boundary.
- Prefer boring, reliable code. Functions <60 lines. Type hints everywhere. No premature abstraction.
- All times in **UTC** internally; convert to IST (+05:30) only in the UI.

### 1.2 Honesty rules (non-negotiable)
- **Never fabricate or synthesize measurement data.** If an API returns nothing, store nothing and surface the gap in the UI/metrics.
- Every number shown in the UI must be traceable to `data/` files or model outputs.
- If the trained model does NOT beat persistence, do not hide it: print the table, write a `docs/DIAGNOSIS.md` with the failure analysis, and continue (the app still works; the pitch adapts).

### 1.3 Failure rules
- External HTTP: retry 3× with exponential backoff (2s/8s/30s) honoring `Retry-After` and rate-limit headers. After 3 failures: if the resource is **blocking** (OpenAQ historical), HALT and print exactly which key/URL failed. If **non-blocking** (Overpass mirror, contextily tiles, S5P), write a stub that degrades gracefully, log to `docs/DEGRADATIONS.md`, continue.
- Missing required env var → halt immediately at Phase 0 acceptance with a clear message.
- Runtime caps (to bound the one-shot run): max **25 stations per city** (ranked by data completeness), history window **15 months** (2025-04-01 → today), FIRMS pulled in 10-day chunks.

### 1.4 Offline-first principle
The frontend NEVER blocks on live third-party APIs. Everything renders from local Parquet snapshots served by FastAPI. `LIVE_MODE=1` merely refreshes snapshots hourly via APScheduler.

---

## §2. STACK, LAYOUT, ENVIRONMENT

### 2.1 Stack (chosen for one-shot reliability, not familiarity)
| Layer | Choice | Why this and not alternatives |
|---|---|---|
| Python | 3.11+, **uv** for env+deps (`uv init`, `uv add`) | uv is fast and deterministic; no conda/poetry friction |
| API | FastAPI + uvicorn | async, auto-docs at `/docs` |
| Storage | **Parquet files + DuckDB** (query layer) | zero-ops; PostGIS is overkill and risky in one shot |
| Geo | geopandas, shapely, **h3>=4** | H3 hexes replace ward shapefiles entirely — kills the most fragile external dependency |
| ML | **LightGBM**, scikit-learn, **shap** | best tabular perf; SHAP gives attribution for free |
| Plots (server) | matplotlib (+ contextily for basemap tiles, optional) | for evidence-pack PNGs |
| PDF | evidence pack = **self-contained HTML** (primary) + fpdf2 PDF (secondary) | WeasyPrint's system deps (pango/cairo) break one-shot builds — do not use it |
| Scheduler | APScheduler (only when LIVE_MODE=1) | |
| Frontend | **Vite + React 18 + TypeScript**, Tailwind (v4 via `@tailwindcss/vite`; fall back to v3.4+postcss if the plugin errors), **MapLibre GL JS** + **deck.gl** (`@deck.gl/react`, H3HexagonLayer), Recharts | MapLibre = no token on stage; deck.gl renders H3 natively |
| Basemap style | `https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json` (attribution: © OpenStreetMap contributors © CARTO) | keyless, reliable |
| LLM (optional) | provider adapter: Anthropic Messages API **or** NVIDIA NIM (OpenAI-compatible) **or** none → Jinja2 templates | zero keys must still produce a full demo |
| Tests | pytest (backend), `tsc --noEmit` + `vite build` (frontend) | |

### 2.2 Repository layout (create exactly this)
```
vayunetra/
├── BUILD_SPEC.md
├── Makefile
├── .env.example  .env(gitignored)  .gitignore
├── pyproject.toml            # managed by uv
├── config/
│   ├── cities.yaml           # §3.1
│   ├── grap.yaml             # §8.3
│   └── aqi_breakpoints.yaml  # §3.3
├── data/                     # gitignored except .gitkeep
│   ├── raw/{city}/           # api pulls as-received (json/csv.gz)
│   ├── geo/{city}/           # grid.parquet, osm_*.geojson, hex_static.parquet
│   └── snapshots/{city}/     # measurements.parquet, met.parquet, fires.parquet,
│                             # features.parquet, hex_nowcast.parquet, forecasts.parquet,
│                             # attribution.parquet, actions.json, metrics.json
├── backend/
│   ├── app/main.py  app/api.py  app/schemas.py  app/deps.py
│   ├── ingest/openaq.py  meteo.py  firms.py  overpass.py  datagov.py(optional)
│   ├── geo/grid.py  static_features.py
│   ├── features/build.py  interpolate.py  aqi.py
│   ├── models/train.py  evaluate.py  baselines.py  predict.py  attribution.py
│   ├── actions/ranker.py  evidence.py  grap.py
│   ├── advisory/generate.py  llm.py  templates/{en,hi,mr}.md.j2
│   └── tests/
├── frontend/                 # vite app
├── scripts/run_pipeline.py   # orchestrates: ingest→features→train→predict→attrib→actions
└── docs/metrics.md  DEGRADATIONS.md  architecture.md
```

### 2.3 `.env.example`
```env
OPENAQ_API_KEY=            # REQUIRED  https://explore.openaq.org/register
FIRMS_MAP_KEY=             # REQUIRED  https://firms.modaps.eosdis.nasa.gov/api/map_key/
DATA_GOV_IN_API_KEY=       # optional
TOMTOM_API_KEY=            # optional
LLM_PROVIDER=none          # none | anthropic | nim
ANTHROPIC_API_KEY=
NIM_BASE_URL=              # e.g. https://integrate.api.nvidia.com/v1
NIM_API_KEY=
NIM_MODEL=meta/llama-3.1-70b-instruct
LIVE_MODE=0
HISTORY_START=2025-04-01
MAX_STATIONS_PER_CITY=25
```

### 2.4 Makefile targets (implement all)
`setup` (uv sync + frontend `npm install`) · `geo` · `data` · `features` · `train` · `evaluate` · `predict` · `actions` · `pipeline` (all of the above in order) · `api` (uvicorn :8000) · `ui` (vite :5173, proxy `/api`→8000) · `demo` (api+ui concurrently) · `test` · `snapshot` (tar data/snapshots for hand-off).

---

## §3. STATIC CONFIG (write these files verbatim, they are load-bearing)

### 3.1 `config/cities.yaml`
```yaml
delhi:
  name: "Delhi NCT"
  bbox: [76.84, 28.40, 77.35, 28.90]        # W,S,E,N — primary spatial truth; no shapefile needed
  fires_bbox: [73.5, 27.5, 79.0, 32.5]      # upwind stubble corridor (Punjab/Haryana)
  fire_radius_km: 300
  h3_res: 8
  timezone: "Asia/Kolkata"
  grap: true
  replay_presets:
    - {id: diwali_2024, label: "Diwali 2024 replay", start: "2024-10-30", end: "2024-11-03"}   # only if history covers it; else auto-hide
    - {id: stubble_2025, label: "Stubble episode",   start: "2025-11-01", end: "2025-11-15"}
pune:
  name: "Pune + PCMC"
  bbox: [73.68, 18.40, 74.05, 18.75]
  fires_bbox: [72.5, 17.5, 75.5, 20.0]
  fire_radius_km: 120
  h3_res: 8
  timezone: "Asia/Kolkata"
  grap: false
  replay_presets: []
```
Note: `HISTORY_START=2025-04-01` means Diwali **2025** (Oct 20–21) is in-window; Diwali 2024 is not — the code must auto-hide presets outside the data range. Festival windows constant (in `features/build.py`): `FESTIVAL_WINDOWS = [("2024-10-30","2024-11-03"), ("2025-10-18","2025-10-23")]`.

### 3.2 H3 grid (`backend/geo/grid.py`)
- Build all res-8 cells whose centroid falls inside the city bbox: iterate `h3.polygon_to_cells(h3.LatLngPoly([...bbox corners as (lat,lng)...]), 8)` (h3 v4 API: `latlng_to_cell`, `cell_to_latlng`, `cell_to_boundary`).
- Output `data/geo/{city}/grid.parquet`: `hex_id, lat, lng`. Expect ~2,500–4,500 cells for Delhi bbox, ~1,000–2,000 for Pune. A friendly `locality` label per hex: nearest of a small hardcoded landmark list per city (write 12–15 well-known localities with coords per city into the module: e.g. Delhi: Anand Vihar, ITO, RK Puram, Dwarka, Rohini, Okhla, Punjabi Bagh, Shadipur, Jahangirpuri, Nehru Nagar, Bawana, Mundka; Pune: Shivajinagar, Kothrud, Hadapsar, Katraj, Bhosari, Nigdi, Hinjewadi, Karve Road, Pashan) — no external geocoding call.

### 3.3 Indian AQI (`config/aqi_breakpoints.yaml` + `features/aqi.py`)
CPCB NAQI sub-index by linear interpolation `I = Ilo + (Ihi−Ilo)·(C−Blo)/(Bhi−Blo)`, AQI = max sub-index, clamp 0–500. Implement at least PM2.5, PM10, NO2:
```yaml
pm25:  [[0,30,0,50],[31,60,51,100],[61,90,101,200],[91,120,201,300],[121,250,301,400],[251,500,401,500]]
pm10:  [[0,50,0,50],[51,100,51,100],[101,250,101,200],[251,350,201,300],[351,430,301,400],[431,600,401,500]]
no2:   [[0,40,0,50],[41,80,51,100],[81,180,101,200],[181,280,201,300],[281,400,301,400],[401,600,401,500]]
```
Categories: 0–50 Good, 51–100 Satisfactory, 101–200 Moderate, 201–300 Poor, 301–400 Very Poor, 401–500 Severe.
**Unit tests (exact):** pm25 45→75, pm25 120→300, pm25 250→400, pm10 100→100, pm25 0→0. Disclose in UI footer: "hourly AQI proxy computed on hourly concentrations (official NAQI uses 24-h averages)".

---

## §4. PHASE 0 — SCAFFOLD

Tasks: git repo hygiene (`.gitignore`: `.env`, `data/`, `node_modules/`, `dist/`, `__pycache__/`, `*.parquet` under data); `uv init`; `uv add fastapi uvicorn[standard] httpx pandas pyarrow duckdb geopandas shapely h3 lightgbm scikit-learn shap matplotlib contextily fpdf2 jinja2 pyyaml python-dotenv apscheduler pytest tenacity`; write `config/*` from §3; `.env.example`; Makefile; `npm create vite@latest frontend -- --template react-ts`; add `maplibre-gl deck.gl @deck.gl/react @deck.gl/geo-layers @deck.gl/layers recharts`; Tailwind v4 via `@tailwindcss/vite` (fallback v3.4 if plugin fails); vite proxy `/api → http://localhost:8000`.

**Acceptance:** `.env` contains both required keys (halt with message if not) · `make api` serves `GET /api/health → {"status":"ok"}` · `cd frontend && npx tsc --noEmit && npm run build` passes · commit.

---

## §5. PHASE 1 — GEO FOUNDATION (grid + OSM static layers)

### 5.1 Overpass ingestion (`backend/ingest/overpass.py`)
Endpoint: `POST https://overpass-api.de/api/interpreter` with `data=<query>`; on failure retry then switch mirror `https://overpass.kumi.systems/api/interpreter`. Cache raw JSON in `data/raw/{city}/overpass_{layer}.json`; skip refetch if cache exists. One query per layer per city, bbox = `(S,W,N,E)` in Overpass order:

```
[out:json][timeout:180];
(way["landuse"="industrial"]({S},{W},{N},{E}); relation["landuse"="industrial"]({S},{W},{N},{E}););
out geom;
```
Layers and tags: `industrial` (landuse=industrial), `construction` (landuse=construction OR building=construction), `schools` (amenity=school → `out center;` for nodes+ways), `hospitals` (amenity=hospital → `out center;`), `roads_major` (way["highway"~"^(motorway|trunk|primary|secondary)$"] → `out geom;`).
Convert to GeoDataFrames → `data/geo/{city}/osm_{layer}.geojson`.

### 5.2 Static hex features (`backend/geo/static_features.py`)
Per hex (use hex boundary polygon): `road_km` (clipped length of major roads), `industrial_frac` (area fraction), `construction_frac`, `schools_n`, `hospitals_n` (points within hex ∪ its 6 neighbors via `h3.grid_ring`). Output `data/geo/{city}/hex_static.parquet`. Use projected CRS EPSG:32643 for lengths/areas.

**Acceptance:** both cities produce grid + hex_static; Delhi has >0 industrial polygons and >100 schools (else log to DEGRADATIONS and continue); print per-city summary table; commit.

---

## §6. PHASE 2 — HISTORICAL DATA INGESTION

### 6.1 OpenAQ (`backend/ingest/openaq.py`) — REQUIRED
Auth: header `X-API-Key: $OPENAQ_API_KEY`. Rate: ~60 req/min → global limiter: sleep so ≤55 req/min; on 429 sleep `x-ratelimit-reset` seconds.
1. **Discover stations**: `GET https://api.openaq.org/v3/locations?bbox={W},{S},{E},{N}&limit=1000`. From `results[]` keep locations having sensors with parameter name in {pm25, pm10, no2}; record provider/owner names in a log; prefer reference/government providers when trimming to `MAX_STATIONS_PER_CITY` (rank by sensor count + recency of `datetimeLast`).
2. **Hourly history**, primary path (bulk, no rate limits): OpenAQ public S3 archive, bucket `openaq-data-archive`, unsigned access. First verify structure: `aws s3 ls --no-sign-request s3://openaq-data-archive/records/csv.gz/` (or boto3 with `signature_version=UNSIGNED`). Expected layout `records/csv.gz/locationid={id}/year={yyyy}/month={mm}/*.csv.gz`. Download months in window per station, concat.
   **Fallback path** (if bucket layout differs/unreachable): API rollups `GET /v3/sensors/{sensor_id}/hours?datetime_from={ISO}&datetime_to={ISO}&limit=1000&page={n}` looped per sensor per month (if `/hours` 404s, use `/v3/sensors/{sensor_id}/measurements` with same params and average to hours). Budget check: 25 stations × ~3 sensors × 15 months ≈ 1,100+ calls ≈ 25–30 min at 50/min — acceptable; print ETA.
3. Normalize → `data/snapshots/{city}/measurements.parquet`: `ts_utc, station_id, station_name, lat, lng, parameter, value` (µg/m³; drop negatives and values >1500; drop duplicates).
4. **Latest values** (for LIVE_MODE + freshness stamp): `GET /v3/locations/{id}/latest`.

### 6.2 Open-Meteo (`backend/ingest/meteo.py`) — keyless
For each city use a 2×2 grid of met points (bbox corners inset 25%) + centroid → 5 points; store per-point, features use nearest point per hex/station.
- **Historical (ERA5)**: `GET https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lng}&start_date={HISTORY_START}&end_date={today}&hourly=temperature_2m,relative_humidity_2m,precipitation,surface_pressure,wind_speed_10m,wind_direction_10m,boundary_layer_height&timezone=UTC` (if `boundary_layer_height` errors, drop it and log).
- **Forecast**: `https://api.open-meteo.com/v1/forecast?...same hourly...&forecast_days=4&timezone=UTC`.
- **CAMS AQ (baseline + optional blend)**: `https://air-quality-api.open-meteo.com/v1/air-quality?latitude&longitude&hourly=pm2_5,pm10,nitrogen_dioxide&forecast_days=4&past_days=92&timezone=UTC`.
Free ≤10k calls/day; we use <100. → `met.parquet` (`ts_utc, point_id, lat, lng, temp, rh, precip, pressure, wind_speed, wind_dir, blh?`), `cams.parquet`.
Derive wind vectors: `wind_u = −speed·sin(dir·π/180)`, `wind_v = −speed·cos(dir·π/180)` (dir = direction wind comes FROM).

### 6.3 NASA FIRMS (`backend/ingest/firms.py`) — REQUIRED
Historical: `GET https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_MAP_KEY}/VIIRS_SNPP_SP/{W},{S},{E},{N}/10/{start_date}` looping start_date in 10-day steps over the window (SP = standard processing archive). Recent tail: same URL with `VIIRS_NOAA20_NRT/{bbox}/10`. ~50 calls/city — trivial vs 5,000/10-min limit. Columns kept: `latitude, longitude, acq_date, acq_time, frp, confidence, satellite`. Build `ts_utc` from acq_date+acq_time (UTC). → `fires.parquet`. Drop `confidence == 'l'` (low) rows when the confidence column is categorical.

### 6.4 Optional live cross-check (`ingest/datagov.py`)
Only if `DATA_GOV_IN_API_KEY` set: `GET https://api.data.gov.in/resource/3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69?api-key={KEY}&format=json&limit=2000&filters[state]=Delhi` (verify resource id on https://www.data.gov.in/resource/real-time-air-quality-index-various-locations if 404). Store latest only; never a training dependency.

**Acceptance:** print coverage report per city: stations kept, rows in measurements, % missing hours for pm25 per station (drop stations >60% missing), fires row count, met rows. Delhi must have ≥8 usable pm25 stations, Pune ≥4 — else HALT with the coverage report. Commit.

---

## §7. PHASE 3 — FEATURES + SPATIAL LAYER

### 7.1 Station-hour panel (`features/build.py`)
Resample per station-parameter to strict hourly index; interpolate gaps ≤3h linearly, leave longer gaps NaN. Join nearest met point. Compute per station for pm25 (repeat minimal set for pm10):
`lag_1,3,6,12,24,48 · roll_mean_24 · roll_max_24 · temp, rh, precip, pressure, wind_speed, wind_u, wind_v, blh? · hour_sin, hour_cos, dow, is_weekend, month · festival_window (0/1 from FESTIVAL_WINDOWS) · fire_load_upwind_24 · fire_count_radius_24`.

**Upwind fire load (exact formula):** for station at P and each fire f within `fire_radius_km` in the trailing 24h: bearing β = initial bearing P→f; upwind iff `|wrapdeg(β − wind_dir_from)| ≤ 45°` using the station's current-hour wind; contribution `frp / max(dist_km, 5)`; `fire_load_upwind_24 = Σ contributions`; `fire_count_radius_24` = plain count. Vectorize with numpy (precompute station→fire distances/bearings once per city).
Targets: `y_h = pm25(t + h)` for h ∈ {24, 48, 72}. → `features.parquet`.

### 7.2 Hex spatial layer (`features/interpolate.py`)
For each timestamp (and each forecast horizon later): IDW over stations, power 2, k=5 nearest, max radius 15 km (Delhi) / 12 km (Pune); mark hex `low_coverage=true` if nearest station >8 km. Nowcast output → `hex_nowcast.parquet` (`ts_utc, hex_id, pm25, pm10?, aqi, category, low_coverage`). Only materialize timestamps the UI needs: last 14 days hourly + all replay-preset windows + forecast horizons (keeps files small).

**Acceptance:** features.parquet non-empty for both cities with <5% NaN in met columns; spot-print one Delhi station's latest 24h vs its raw values; hex_nowcast renders ≥1,000 hexes for Delhi at latest timestamp. Commit.

---

## §8. PHASE 4 — MODELS: BASELINES, FORECAST, ATTRIBUTION

### 8.1 Baselines (`models/baselines.py`)
(1) **Persistence**: ŷ(t+h) = y(t). (2) **Hour-of-week climatology**: mean of same (dow, hour) over training. (3) **Raw CAMS** pm2_5 at station point (only where cams overlaps the eval window; report separately).

### 8.2 Forecast models (`models/train.py`, `evaluate.py`, `predict.py`)
One LightGBM regressor per (city, pollutant=pm25 [+pm10 if time], horizon ∈ {24,48,72}). Params (fixed, no tuning loops): `n_estimators=600, learning_rate=0.05, num_leaves=63, min_child_samples=40, subsample=0.9, colsample_bytree=0.9, random_state=42`, early stopping 50 on the validation fold.
**Backtest**: rolling-origin — last 8 weeks of data as 4 sequential 2-week test folds; train on everything strictly before each fold. Metrics per horizon: RMSE, MAE, and skill `1 − RMSE_model/RMSE_persistence`. Write `metrics.json` + human table `docs/metrics.md` (model vs persistence vs climatology vs CAMS-where-available). Target: skill ≥ 0.25 at 24h; if not met, apply rule §1.2 (report, diagnose, continue).
**Inference** (`predict.py`): latest features + Open-Meteo forecast met for t+24/48/72 → station predictions → IDW to hexes → `forecasts.parquet` (`hex_id, horizon_h, pm25_pred, pi_low, pi_high, aqi_pred`). Prediction interval: per-horizon empirical residual quantiles (10/90%) from backtest. Optional CAMS blend where CAMS available: `final = 0.7·ML + 0.3·CAMS_bias_corr` with bias correction = mean(obs−cams) over past 92 days at nearest station; skip silently if cams missing.

### 8.3 Attribution engine (`models/attribution.py`) — the innovation; implement EXACTLY this recipe
Sources reported: `{biomass, traffic, industry, construction_dust, background}` + `meteorology_modifier` (shown separately as "dispersion effect", not a source).
1. **Temporal decomposition (SHAP)** on the 24h model at the nearest station, current hour. Feature groups: `biomass = {fire_load_upwind_24, fire_count_radius_24}`; `meteorology = {temp, rh, precip, pressure, wind_*, blh}`; `activity_cycle = {hour_sin, hour_cos, dow, is_weekend, month, festival_window}`; `background_persistence = {all lags, rolls}`. Shares = group Σ|SHAP| / total Σ|SHAP| → `biomass_t, met_t, activity_t, background_t`.
2. **Spatial decomposition**: per city per timestamp, ridge regression (α=1.0, standardized) of hex `log(pm25_hex / city_mean_pm25)` on static covariates `[road_km, industrial_frac, construction_frac]`. Per-hex non-negative contributions `c_traffic, c_industry, c_construction = clip(coef_j · z_j, 0, ∞)`; `c_residual = 1` unit floor; spatial weights = normalized `[c_traffic, c_industry, c_construction, c_residual]`.
3. **Combine**: `biomass = biomass_t`; distribute `(activity_t + background_t)` across `{traffic, industry, construction_dust, background}` by the spatial weights (residual→background); renormalize the 5 sources to 1.0; report `meteorology_modifier = met_t` separately.
4. **Wind-sector lift (confidence check)**: over trailing 30 days at this hex's nearest station: `lift(source) = P(pm25 > p75 | wind_from within ±45° of bearing to nearest source geometry) / P(pm25 > p75)`; compute for biomass (nearest fire-cluster centroid of trailing 7 days) and industry (nearest industrial polygon centroid). 
5. **Confidence**: `high` if (top source's lift ≥ 1.3 when applicable) AND station distance <8 km AND ≥600 valid trailing hours; `medium` if 2 of 3; else `low`.
→ `attribution.parquet` (`ts_utc, hex_id, source, share, confidence, evidence_json`), where evidence_json holds fire count/FRP/mean bearing, lifts, station distance.

### 8.4 GRAP (`actions/grap.py` + `config/grap.yaml`)
Delhi only. Stage from AQI: I 201–300, II 301–400, III 401–450, IV >450. `grap.yaml` lists 3–4 headline actions per stage (Stage I: mechanized sweeping & water sprinkling, strict C&D dust control, PUC enforcement; Stage II: ban coal/firewood & tandoors, DG-set restrictions, parking-fee disincentives; Stage III: halt non-essential construction & demolition, close brick kilns/stone crushers, BS-III petrol/BS-IV diesel LMV restrictions; Stage IV: ban non-essential truck entry, 50% WFH advisories, consider school closure). Predicted stage = stage(max hex-median AQI forecast over next 48h).

**Acceptance:** `make evaluate` prints the metrics table for both cities; unit test: attribution shares sum to 1±0.001 and are non-negative; Diwali/festival replay sanity (only if window in data): mean `biomass+activity` share during festival window > non-festival November mean — print the comparison, warn (not fail) if violated. Commit.

---

## §9. PHASE 5 — ACTIONS: RANKER + EVIDENCE PACKS

### 9.1 Ranker (`actions/ranker.py`) — exact formula
For each hex with current AQI > 200 and each source with share ≥ 0.15:
`score = share × sev × persist × exposure × actionability`
- `sev = clip((aqi − 100)/400, 0, 1)`
- `persist = 0.2 + 0.8 × (fraction of trailing 12 h with hex AQI > 200)`
- `exposure = 0.5 + 0.5 × minmax_norm(schools_n + hospitals_n over city)`
- `actionability = {construction_dust: .9, biomass: .85, industry: .8, traffic: .6, background: .15}`
Top 10 per city → `actions.json`: id, hex, locality, source, share, confidence, score, recommended_action (from a small per-source action map + GRAP stage context for Delhi), created_ts.

### 9.2 Evidence pack (`actions/evidence.py`)
`GET /api/actions/{city}/{id}/evidence` → **self-contained HTML** (inline CSS, base64 PNGs), plus `?format=pdf` via fpdf2 (same content, simpler layout). Contents, in order: header (ref no `VN-{city}-{yyyymmdd}-{id}`, hex, locality, timestamp IST); location map PNG (matplotlib: hex boundary, station markers, trailing-7-day fire points sized by FRP; add contextily Carto basemap, and if tile fetch fails plot without basemap and note it); 72-h observed + forecast chart PNG with PI band; attribution bar chart + confidence badge; evidence table (top 10 fires: datetime, dist km, bearing, FRP | wind-sector lift values | nearest station + distance); recommended action + GRAP stage (Delhi); **draft notice paragraph** (template text with injected numbers; LLM-polished only if provider configured); method & sources appendix (OpenAQ/CPCB, NASA FIRMS VIIRS, Open-Meteo/ERA5-CAMS, OSM; "evidence-weighted, confidence-scored attribution — not regulatory source apportionment"); PRANA-reporting stub (JSON block: city, period, hotspot, source category, action recommended, evidence refs). Instrument and store `generation_ms` — this is the demo stopwatch number.

**Acceptance:** evidence HTML for the top Delhi action opens standalone in a browser with all images; generation < 30 s; pdf variant returns 200. Commit.

---

## §10. PHASE 6 — ADVISORY (`advisory/`)

Deterministic Jinja2 templates `en/hi/mr.md.j2` with ONLY these injected fields: `locality, aqi_now, category, peak_24h_aqi, peak_window_ist, primary_source_label, do_1..do_3, vulnerable_note`. Write natural, correct Hindi and Marathi yourself (short: 60–90 words); numbers are never generated by an LLM. `advisory/llm.py`: adapter with `polish(text, lang) -> text` for provider ∈ {anthropic (Messages API, `claude-sonnet-4-6`, max_tokens 400), nim (OpenAI-compatible chat completions at `NIM_BASE_URL`)}; on `LLM_PROVIDER=none` return input unchanged. Endpoint `GET /api/advisory/{city}/{hex}?lang=en|hi|mr` → `{lang, text, generated_by: template|template+llm}`.

**Acceptance:** all three languages return non-empty text for a Delhi hex with `LLM_PROVIDER=none`; Devanagari renders (UTF-8 end-to-end). Commit.

---

## §11. PHASE 7 — BACKEND API (assemble)

FastAPI, all reads from Parquet via DuckDB. CORS allow localhost:5173. Endpoints (define pydantic schemas in `app/schemas.py`):
```
GET /api/health
GET /api/cities                      → [{id,name,bbox,grap,replay_presets(filtered to data range)}]
GET /api/timeline/{city}             → {timestamps:[iso...], presets:[...]}   # what the scrubber can show
GET /api/grid/{city}?t={iso}         → {t, cells:[{hex_id,pm25,aqi,category,low_coverage}]}
GET /api/forecast/{city}/{hex}       → {history_72h:[{t,pm25,aqi}], forecast:[{h,t,pm25,pi_low,pi_high,aqi}]}
GET /api/attribution/{city}/{hex}?t= → {shares:{...5 sources}, met_modifier, confidence, evidence:{fires_n,frp_sum,mean_bearing,lifts,station_km}}
GET /api/fires/{city}?t=&window_h=24 → [{lat,lng,frp,age_h}]
GET /api/actions/{city}              → ranked queue
GET /api/actions/{city}/{id}/evidence?format=html|pdf
GET /api/advisory/{city}/{hex}?lang=
GET /api/metrics/{city}              → metrics.json passthrough
GET /api/grap/{city}                 → {current_stage, predicted_stage_48h, actions:[...]} (delhi only)
```
`scripts/run_pipeline.py` runs ingest(latest-only when snapshots exist)→features→predict→attribution→actions; APScheduler triggers it hourly iff `LIVE_MODE=1`.

**Acceptance:** every endpoint returns 200 with non-empty payload for delhi; `pytest backend/tests` green (include AQI test vectors from §3.3, shares-sum test, schema smoke tests). Commit.

---

## §12. PHASE 8 — FRONTEND

Three routes (react-router): `/` Command, `/actions`, `/metrics`. Dark theme (slate-950 bg). AQI colors + text labels (color-blind safe): Good #16a34a, Satisfactory #84cc16, Moderate #eab308, Poor #f97316, Very Poor #dc2626, Severe #7f1d1d — always pair color with the category text.

Components:
- **MapView**: MapLibre with the Carto dark style URL (§2.1) + `@deck.gl/react` overlay. `H3HexagonLayer` (`getHexagon: hex_id`, fill by AQI color, opacity 0.55, `pickable`, onClick → select hex); `ScatterplotLayer` for fires (orange, radius ∝ FRP, toggleable); station dots. Initial view: city bbox fit.
- **TimeScrubber**: slider over `/api/timeline` timestamps + preset chips ("Latest", replay presets). Debounced grid refetch.
- **CityToggle**: Delhi ⇄ Pune (refetches everything).
- **GrapChip** (Delhi): current + predicted-48h stage; click → stage actions popover.
- **HexPanel** (right rail, on selection): locality + AQI chip; Recharts `ComposedChart` — 72h history line + forecast line + PI `Area`; attribution donut (`PieChart`) with confidence badge and "dispersion effect" note; evidence mini-list (fires n, FRP, station distance); buttons: **Generate evidence pack** (opens `/evidence` HTML in new tab, shows returned `generation_ms` as "Signal → evidence in X s"), **Advisory** (modal, EN/HI/MR tabs).
- **ActionsPage**: ranked table (locality, source badge, share %, confidence, score bar, AQI) → row click opens evidence.
- **MetricsPage**: render `/api/metrics` as a table: model vs persistence vs climatology vs CAMS per horizon + coverage stats. Footer: data sources + AQI-proxy disclosure.

**Acceptance:** `npm run build` clean; manual flow works end-to-end: load → Delhi grid renders → scrub time → click hex → forecast+attribution → evidence opens → advisory Marathi renders → toggle Pune → grid renders. Commit.

---

## §13. PHASE 9 — VALIDATION ARTIFACTS + PHASE 10 — PACKAGING

**Phase 9:** `backend/models/event_study.py` → for each replay preset in data range: plot city-mean pm25 + biomass share timeline, save `docs/event_{id}.png`; append findings + latency stats (evidence `generation_ms` distribution) to `docs/metrics.md`. Write `docs/architecture.md` with a mermaid flowchart (sources→ingest→parquet→features→models→attribution→actions/advisory→API→UI). README.md: one-liner, screenshots placeholder, quickstart (`cp .env.example .env` → keys → `make setup && make pipeline && make demo`), data source & license table, metrics summary, honest-limitations section.
**Phase 10:** `make test` runs pytest + `tsc --noEmit`; `make snapshot` tars `data/snapshots`; optional `docker-compose.yml` (api + static-built frontend via nginx) — attempt, but do not let Docker failures block; final commit `v1.0-prototype`.

---

## §14. DONE CHECKLIST (agent prints with ✅/❌)
1. Phases 0–10 committed, acceptance passed (list any warnings)
2. `make demo` → full click-through works offline (no live keys needed at runtime)
3. `docs/metrics.md`: 24h skill vs persistence = ___ (Delhi), ___ (Pune); CAMS comparison rows present where data allowed
4. Attribution shares valid; festival sanity-check result: ___
5. Evidence pack generation p50 latency = ___ s (< 30 s)
6. Advisories render in EN/HI/MR with `LLM_PROVIDER=none`
7. `docs/DEGRADATIONS.md` lists every fallback taken (must be honest, may be empty)
8. Coverage report: stations used per city, % missing hours
9. README quickstart verified from clean clone (fresh `.env` needed)
10. Things a human must still do: record video, deck, deploy (Render/Vercel), verify Unstop Phase-2 deadline

---

## §15. QUICK REFERENCE — ALL EXTERNAL CALLS IN ONE TABLE

| API | Auth | Base call | Limit | Used in |
|---|---|---|---|---|
| OpenAQ v3 | `X-API-Key` | `api.openaq.org/v3/locations?bbox=` · `/v3/sensors/{id}/hours` · S3 `openaq-data-archive` (unsigned) | ~60/min (S3: none) | §6.1 |
| Open-Meteo archive | none | `archive-api.open-meteo.com/v1/archive` | 10k/day | §6.2 |
| Open-Meteo forecast | none | `api.open-meteo.com/v1/forecast` | 10k/day | §6.2 |
| Open-Meteo air quality | none | `air-quality-api.open-meteo.com/v1/air-quality` (`past_days=92`) | 10k/day | §6.2 |
| NASA FIRMS | MAP_KEY in path | `firms.modaps.eosdis.nasa.gov/api/area/csv/{KEY}/VIIRS_SNPP_SP/{bbox}/10/{date}` | 5k/10min | §6.3 |
| Overpass | none | `overpass-api.de/api/interpreter` (mirror: kumi.systems) | fair use | §5.1 |
| Carto basemap | none (attribution) | style + tiles URLs | fair use | UI, evidence maps |
| data.gov.in (opt) | api-key param | `api.data.gov.in/resource/3b01bcb8-...ba69` | standard | §6.4 |
| Anthropic/NIM (opt) | key | Messages API / OpenAI-compatible | plan | §10 |

**Explicitly out of scope for the one-shot** (stretch, post-run): Sentinel-5P via Earth Engine, TomTom live traffic (proxy: `road_km` × hardcoded diurnal profile already covers it), WorldPop raster (drop-in at `data/geo/{city}/population.tif` auto-detected by exposure calc if present), deployment.
