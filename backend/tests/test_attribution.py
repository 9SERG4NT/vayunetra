"""Attribution invariants (BUILD_SPEC §8.4 acceptance): shares sum to 1±1e-3, non-negative."""
import pytest

from backend.models.attribution import SOURCES, combine_shares


@pytest.mark.parametrize("temporal,weights", [
    ({"biomass": 0.3, "activity": 0.3, "background": 0.3, "meteorology": 0.1},
     {"w_traffic": 0.4, "w_industry": 0.2, "w_construction": 0.1, "w_residual": 0.3}),
    ({"biomass": 0.0, "activity": 0.5, "background": 0.5, "meteorology": 0.0},
     {"w_traffic": 0.25, "w_industry": 0.25, "w_construction": 0.25, "w_residual": 0.25}),
    ({"biomass": 0.9, "activity": 0.05, "background": 0.03, "meteorology": 0.02},
     {"w_traffic": 0.0, "w_industry": 0.0, "w_construction": 0.0, "w_residual": 1.0}),
])
def test_shares_sum_to_one_nonneg(temporal, weights):
    shares = combine_shares(temporal, weights)
    assert set(shares) == set(SOURCES)
    assert abs(sum(shares.values()) - 1.0) < 1e-3
    assert all(v >= 0 for v in shares.values())


def test_biomass_share_preserved():
    shares = combine_shares(
        {"biomass": 0.5, "activity": 0.2, "background": 0.2, "meteorology": 0.1},
        {"w_traffic": 0.5, "w_industry": 0.2, "w_construction": 0.2, "w_residual": 0.1},
    )
    # biomass should be the largest share here (0.5 temporal vs 0.4 pool distributed)
    assert shares["biomass"] == max(shares.values())
