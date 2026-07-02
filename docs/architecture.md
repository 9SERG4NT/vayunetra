# VayuNetra — Architecture

VayuNetra turns existing public air-quality signals into **evidence-backed
enforcement actions**. Everything renders offline from local Parquet snapshots;
live third-party APIs only refresh those snapshots.

```mermaid
flowchart TD
    subgraph Sources[Public data sources]
        A1[OpenAQ / CPCB stations]
        A2[NASA FIRMS VIIRS fires]
        A3[Open-Meteo ERA5 + forecast + CAMS]
        A4[OpenStreetMap land use]
    end

    subgraph Ingest[backend/ingest]
        B1[openaq.py]
        B2[firms.py]
        B3[meteo.py]
        B4[overpass.py]
    end

    A1 --> B1
    A2 --> B2
    A3 --> B3
    A4 --> B4

    subgraph Store[data/ Parquet + JSON snapshots]
        C1[measurements / met / cams / fires]
        C2[grid / hex_static]
    end

    B1 --> C1
    B2 --> C1
    B3 --> C1
    B4 --> C2

    subgraph Features[backend/features]
        D1[build.py — station-hour panel + upwind fire load]
        D2[interpolate.py — IDW hex nowcast]
        D3[aqi.py — CPCB NAQI]
    end

    C1 --> D1
    C1 --> D2
    C2 --> D1
    D3 --> D2

    subgraph Models[backend/models]
        E1[train.py — LightGBM per horizon]
        E2[evaluate.py — backtest vs baselines]
        E3[predict.py — forecasts + PI + CAMS blend]
        E4[attribution.py — SHAP + ridge + wind lift]
    end

    D1 --> E1 --> E3
    D1 --> E2
    D2 --> E4
    E1 --> E4

    subgraph Act[backend/actions + advisory]
        F1[ranker.py — enforcement queue]
        F2[evidence.py — HTML/PDF pack]
        F3[grap.py — GRAP staging]
        F4[advisory/generate.py — EN/HI/MR]
    end

    E4 --> F1 --> F2
    E3 --> F3
    D2 --> F4

    subgraph Serve[Serving]
        G1[FastAPI backend/app]
        G2[React + MapLibre + deck.gl UI]
    end

    F1 --> G1
    F2 --> G1
    F3 --> G1
    F4 --> G1
    E3 --> G1
    D2 --> G1
    G1 --> G2
```

## Key design decisions
- **H3 res-8 hexes** replace ward shapefiles — the most fragile external dependency
  is eliminated; a new city is one YAML block.
- **Offline-first**: the UI never blocks on a live API; `LIVE_MODE=1` refreshes
  snapshots hourly via APScheduler.
- **TreeSHAP via LightGBM `pred_contrib`** — exact SHAP values without the
  `shap`/`numba`/`llvmlite` dependency chain (which does not build on Python 3.12).
- **Triangulated attribution** (temporal SHAP + spatial ridge + wind-sector lift)
  with an explicit confidence badge — labelled *evidence-weighted, not regulatory
  source apportionment*.
- **Honest evaluation**: rolling-origin backtest vs persistence / climatology / CAMS;
  results (including shortfalls) are printed, never hidden.
