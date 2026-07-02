"""API schema smoke tests (BUILD_SPEC §11 acceptance)."""
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_cities_shape():
    r = client.get("/api/cities")
    assert r.status_code == 200
    data = r.json()
    ids = {c["id"] for c in data}
    assert {"delhi", "pune"}.issubset(ids)
    for c in data:
        assert set(c) >= {"id", "name", "bbox", "grap", "replay_presets"}
        assert len(c["bbox"]) == 4


def test_unknown_city_404():
    assert client.get("/api/timeline/atlantis").status_code == 404


def test_grid_endpoint_ok():
    r = client.get("/api/grid/delhi")
    assert r.status_code == 200
    body = r.json()
    assert body["city"] == "delhi"
    assert "cells" in body


def test_grap_delhi_shape():
    r = client.get("/api/grap/delhi")
    assert r.status_code == 200
