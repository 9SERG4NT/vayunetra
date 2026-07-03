"""Pydantic response schemas for the VayuNetra API (BUILD_SPEC §11)."""
from __future__ import annotations

from pydantic import BaseModel


class City(BaseModel):
    id: str
    name: str
    bbox: list[float]
    grap: bool
    replay_presets: list[dict]


class TimelineResponse(BaseModel):
    city: str
    timestamps: list[str]
    presets: list[dict]


class GridCell(BaseModel):
    hex_id: str
    pm25: float | None
    aqi: float | None
    category: str | None
    low_coverage: bool


class GridResponse(BaseModel):
    city: str
    t: str
    cells: list[GridCell]


class HistoryPoint(BaseModel):
    t: str
    pm25: float | None
    aqi: float | None


class ForecastPoint(BaseModel):
    h: int
    t: str
    pm25: float | None
    pi_low: float | None
    pi_high: float | None
    aqi: float | None


class ForecastResponse(BaseModel):
    city: str
    hex_id: str
    history_72h: list[HistoryPoint]
    forecast: list[ForecastPoint]


class AttributionResponse(BaseModel):
    city: str
    hex_id: str
    t: str
    shares: dict[str, float]
    met_modifier: float
    confidence: str
    evidence: dict


class Fire(BaseModel):
    lat: float
    lng: float
    frp: float
    age_h: float


class Action(BaseModel):
    id: str
    hex: str
    locality: str
    source: str
    share: float
    confidence: str
    aqi: float
    score: float
    recommended_action: str
    department: str | None = None
    legal_basis: str | None = None
    intervention_id: str | None = None
    grap_context: str | None = None
    created_ts: str


class SimulateRequest(BaseModel):
    hex_id: str | None = None       # null => city-level scenario
    intervention_id: str
    at: str | None = None


class OrderRequest(BaseModel):
    hex_id: str
    intervention_id: str


class ActionsResponse(BaseModel):
    city: str
    created_ts: str | None = None
    actions: list[Action]


class AdvisoryResponse(BaseModel):
    lang: str
    text: str
    generated_by: str


class GrapResponse(BaseModel):
    city: str
    current_stage: int
    predicted_stage_48h: int
    headline_stage: int
    label: str
    actions: list[str]
