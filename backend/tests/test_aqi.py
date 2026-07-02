"""AQI unit tests — the exact vectors from BUILD_SPEC §3.3."""
import pandas as pd
import pytest

from backend.features.aqi import aqi_from_pollutants, aqi_subindex, category_for


@pytest.mark.parametrize("param,conc,expected", [
    ("pm25", 45, 75),
    ("pm25", 120, 300),
    ("pm25", 250, 400),
    ("pm10", 100, 100),
    ("pm25", 0, 0),
])
def test_subindex_vectors(param, conc, expected):
    assert aqi_subindex(param, conc) == expected


def test_aqi_is_max_subindex_and_dominant():
    df = pd.DataFrame({"pm25": [45.0], "pm10": [100.0], "no2": [30.0]})
    out = aqi_from_pollutants(df)
    assert out.loc[0, "aqi"] == 100  # pm10 sub-index dominates
    assert out.loc[0, "dominant"] == "pm10"


def test_aqi_clamped_0_500():
    df = pd.DataFrame({"pm25": [-5.0, 9999.0]})
    out = aqi_from_pollutants(df)
    assert out["aqi"].min() >= 0
    assert out["aqi"].max() <= 500


def test_categories():
    assert category_for(45)[0] == "Good"
    assert category_for(250)[0] == "Poor"
    assert category_for(450)[0] == "Severe"
