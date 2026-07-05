# VayuNetra Makefile.  On Windows, run these from Git Bash (bash is available).
# Every python target runs inside the uv-managed environment via `uv run`.

PY := uv run python
CITIES ?= delhi pune

.PHONY: setup geo data features train evaluate predict actions attribution \
        pipeline api ui demo test snapshot help

help:
	@echo "VayuNetra targets:"
	@echo "  setup     - uv sync + frontend npm install"
	@echo "  geo       - build H3 grid + OSM static hex features"
	@echo "  data      - ingest OpenAQ / Open-Meteo / FIRMS (needs .env keys)"
	@echo "  features  - build station-hour panel + hex nowcast"
	@echo "  train     - train LightGBM forecast models"
	@echo "  evaluate  - backtest vs baselines -> docs/metrics.md"
	@echo "  predict   - inference -> forecasts.parquet"
	@echo "  attribution / actions - attribution + ranked action queue"
	@echo "  pipeline  - geo -> data -> features -> train -> predict -> attribution -> actions"
	@echo "  api       - uvicorn on :8000"
	@echo "  ui        - vite dev server on :5173 (proxies /api -> :8000)"
	@echo "  demo      - api + ui concurrently"
	@echo "  test      - pytest + tsc --noEmit"
	@echo "  snapshot  - tar data/snapshots for hand-off"

setup:
	uv sync
	cd frontend && npm install

geo:
	$(PY) scripts/run_pipeline.py geo --cities $(CITIES)

data:
	$(PY) scripts/run_pipeline.py data --cities $(CITIES)

features:
	$(PY) scripts/run_pipeline.py features --cities $(CITIES)

train:
	$(PY) scripts/run_pipeline.py train --cities $(CITIES)

evaluate:
	$(PY) scripts/run_pipeline.py evaluate --cities $(CITIES)

predict:
	$(PY) scripts/run_pipeline.py predict --cities $(CITIES)

attribution:
	$(PY) scripts/run_pipeline.py attribution --cities $(CITIES)

actions:
	$(PY) scripts/run_pipeline.py actions --cities $(CITIES)

pipeline:
	$(PY) scripts/run_pipeline.py all --cities $(CITIES)

api:
	uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload

ui:
	cd frontend && npm run dev

demo:
	@echo "Starting API (:8000) and UI (:5173). Ctrl-C to stop both."
	uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 & echo $$! > .api.pid; \
	cd frontend && npm run dev; \
	kill `cat ../.api.pid` 2>/dev/null; rm -f ../.api.pid

test:
	uv run pytest -q backend/tests
	cd frontend && npx tsc --noEmit

decide-smoke:
	$(PY) scripts/decide_smoke.py delhi

snapshot:
	tar -czf vayunetra_snapshots.tar.gz -C data snapshots
	@echo "Wrote vayunetra_snapshots.tar.gz"
