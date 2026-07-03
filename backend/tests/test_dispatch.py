"""Dispatch optimizer acceptance (DECISION_LAYER_SPEC §A2)."""
from pathlib import Path

import pytest

SNAP = Path(__file__).resolve().parents[2] / "data" / "snapshots" / "delhi"


def _require_snapshot():
    if not (SNAP / "actions.json").exists():
        pytest.skip("delhi snapshot not built")


def test_routes_respect_shift_and_beat_naive():
    _require_snapshot()
    from backend.actions.dispatch import dispatch
    d = dispatch("delhi", 4, 8.0)
    for p in d["plan"]:
        assert p["utilisation"] <= 1.0 + 1e-9  # never exceeds the shift budget
    # optimized covered-impact must be >= the geography-blind naive plan
    assert d["totals"]["impact_covered"] >= d["baseline_comparison"]["naive_impact_covered"]


def test_deterministic():
    _require_snapshot()
    from backend.actions.dispatch import dispatch
    a = dispatch("delhi", 6, 8.0)
    b = dispatch("delhi", 6, 8.0)
    assert a["totals"] == b["totals"]
    assert a["baseline_comparison"] == b["baseline_comparison"]


def test_inspector_bounds():
    _require_snapshot()
    from backend.actions.dispatch import dispatch
    assert dispatch("delhi", 999, 8.0)["inspectors"] == 50
    assert dispatch("delhi", 0, 8.0)["inspectors"] == 1
