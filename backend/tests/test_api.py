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


def test_vulnerability_shape():
    r = client.get("/api/vulnerability/delhi")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"schools", "hospitals"}
    for layer in body.values():
        assert isinstance(layer, list)


def test_refresh_status_shape():
    # GET only — POST /refresh would trigger a real multi-minute network refresh.
    r = client.get("/api/refresh")
    assert r.status_code == 200
    body = r.json()
    assert {"running", "started", "finished", "error"} <= set(body)
    assert isinstance(body["running"], bool)


def test_freshness_shape():
    r = client.get("/api/freshness/delhi")
    assert r.status_code == 200
    body = r.json()
    assert body["city"] == "delhi"
    assert {"latest", "age_hours", "now"} <= set(body)
    if body["age_hours"] is not None:
        assert body["age_hours"] >= 0


def test_freshness_unknown_city_404():
    assert client.get("/api/freshness/atlantis").status_code == 404
