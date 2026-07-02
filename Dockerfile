# Backend API image. Serves offline snapshots from data/ (mount or bake in).
FROM python:3.12-slim

# System libs for geopandas/rasterio/contextily wheels are bundled; keep it lean.
RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend/ ./backend/
COPY config/ ./config/
COPY scripts/ ./scripts/
COPY data/ ./data/

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
