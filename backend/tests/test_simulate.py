"""Scenario engine acceptance (DECISION_LAYER_SPEC §A1 acceptance).

Ranges everywhere, monotonic efficacy, bounded reductions, triangulated biomass,
inherited (tier-word) confidence, order doc carries the Directed Intervention section.
Uses the real Delhi snapshot (skips cleanly if the pipeline has not been run).
"""
import json
import time
from pathlib import Path

import pytest

from backend.config import load_interventions

SNAP = Path(__file__).resolve().parents[2] / "data" / "snapshots" / "delhi"


def _hotspot_hex():
    actions = SNAP / "actions.json"
    if not actions.exists():
        pytest.skip("delhi snapshot not built")
    items = json.loads(actions.read_text(encoding="utf-8")).get("actions", [])
    if not items:
        pytest.skip("no delhi actions")
    return items[0]["hex"]


def test_interventions_valid():
    ivs = load_interventions()
    assert len(ivs) >= 5
    for iv in ivs.values():
        e = iv["efficacy"]
        assert e[0] <= e[1] <= e[2]
        assert iv["targets"] in {"biomass", "traffic", "industry", "construction_dust", "background"}
        assert "basis" in iv


def test_aqi_after_never_exceeds_now_and_monotonic():
    from backend.actions.simulate import simulate
    hx = _hotspot_hex()
    s = simulate("delhi", hx, "construction_halt")
    assert s["aqi_after"]["mid"] <= s["aqi_now"]
    # higher efficacy removes more -> lower AQI_after
    assert s["aqi_after"]["hi"] <= s["aqi_after"]["lo"]
    # delta ranges are ordered
    assert s["delta_aqi"]["lo"] <= s["delta_aqi"]["mid"] <= s["delta_aqi"]["hi"]


def test_reduction_bounded_by_available_pm():
    from backend.actions.simulate import simulate
    s = simulate("delhi", _hotspot_hex(), "construction_halt")
    for k in ("lo", "mid", "hi"):
        assert 0 <= s["delta_pm"][k] <= s["pm_now"] + 1e-6
        assert s["pm_after"][k] >= 0


def test_confidence_is_tier_word_not_percentage():
    from backend.actions.simulate import simulate
    s = simulate("delhi", _hotspot_hex(), "construction_halt")
    assert s["confidence"] in {"high", "medium", "low"}


def test_biomass_triangulated():
    from backend.actions.simulate import simulate
    s = simulate("delhi", _hotspot_hex(), "biomass_enforcement")
    assert s["method"] == "triangulated"


def test_simulate_warm_latency():
    from backend.actions.simulate import simulate
    hx = _hotspot_hex()
    simulate("delhi", hx, "construction_halt")  # warm caches
    t = time.time()
    simulate("delhi", hx, "construction_halt")
    assert (time.time() - t) < 1.5


def test_order_document_has_directed_section():
    from backend.actions.evidence import generate_order_html
    html, _ = generate_order_html("delhi", _hotspot_hex(), "construction_halt")
    assert "Directed Intervention" in html
    assert "planning estimate" in html.lower()
