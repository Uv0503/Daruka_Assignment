"""Canonical, strict Pydantic contracts used by API, state and evidence code."""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    # JSON accepts NaN/Infinity in some clients although neither is a usable
    # observation.  Reject them at every API/model boundary.
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Observation(StrictModel):
    observation_id: str
    field: str
    value: float | int | bool | str | list[str] | None = None
    unit: str | None = None
    qualitative_value: str | None = None
    origin: Literal["user_reported", "user_measured", "external_modeled", "derived"]
    source_turn_id: str
    raw_text: str
    sample_depth_cm: float | None = Field(default=None, ge=0)
    period_start: date | None = None
    period_end: date | None = None
    method: str | None = None
    event_seq: int = Field(ge=1)
    operation: Literal["set", "clear"] = "set"

    @field_validator("value")
    @classmethod
    def finite_number(cls, value: Any) -> Any:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("numeric values must be finite")
        return value


class SoilPatch(StrictModel):
    ph: float | None = Field(default=None, ge=0, le=14)
    organic_carbon_pct: float | None = Field(default=None, ge=0, le=100)
    moisture_vwc_pct: float | None = Field(default=None, ge=0, le=100)
    moisture_condition: Literal["low", "adequate", "high", "unknown"] | None = None


class ClimatePatch(StrictModel):
    annual_rainfall_mm: float | None = Field(default=None, ge=0)
    rainfall_pattern: Literal["low", "erratic", "seasonally_dry", "adequate", "unknown"] | None = None
    rainfall_seasonality_detail: str | None = None
    mean_temperature_c: float | None = None


class LocationPatch(StrictModel):
    region: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def coordinate_pair(self) -> LocationPatch:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be supplied together")
        return self


class LandPatch(StrictModel):
    use_type: Literal["crop", "pasture", "forest", "grassland", "wetland", "urban", "other", "unknown"] | None = None
    crop_system: str | None = None
    irrigation_available: bool | None = None
    habitat_cover_pct: float | None = Field(default=None, ge=0, le=100)


class BiodiversityPatch(StrictModel):
    observed_species_richness: int | None = Field(default=None, ge=0)
    habitat_types: list[str] | None = None
    decline_reported: str | None = None


class PressuresPatch(StrictModel):
    pesticide_use: str | None = None
    pollution: str | None = None
    recent_land_clearing: bool | None = None


class SitePatch(StrictModel):
    location: LocationPatch | None = None
    soil: SoilPatch | None = None
    climate: ClimatePatch | None = None
    land: LandPatch | None = None
    biodiversity: BiodiversityPatch | None = None
    pressures: PressuresPatch | None = None
    notes: str | None = Field(default=None, max_length=2000)


class SourceRecord(StrictModel):
    source_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    publisher: str
    publication_year: int | None = None
    url: str
    doi: str | None = None
    source_type: Literal[
        "research_article", "systematic_review", "institutional_report", "institutional_guidance", "dataset"
    ]
    access_status: Literal["verified", "blocked", "metadata_only"]
    license_note: str
    retrieved_at: str | None = None
    content_sha256: str | None = None
    local_path: str | None = None
    kb_version: str


class Effect(StrictModel):
    measure: str
    estimate: float
    ci_lower: float | None = None
    ci_upper: float | None = None
    confidence_interval_level: float | None = None
    unit: str
    comparator: str
    time_horizon_months: float | None = None
    target_population: str


class EvidenceCard(StrictModel):
    evidence_id: str
    source_id: str
    chunk_ids: list[str] = Field(min_length=1)
    review_status: Literal["draft", "reviewed"]
    intervention: str
    metric: str
    claim_summary: str
    relation_type: Literal["association", "mechanism", "experimental_effect", "synthesis", "guidance"]
    effect: Effect | None = None
    geography: str
    ecosystems: list[str]
    applicability_conditions: list[str]
    limitations: list[str]
    locator: str
    reviewer_note: str
    support_excerpt: str


class SourcePassage(StrictModel):
    chunk_id: str
    source_id: str
    parent_id: str
    text: str
    text_sha256: str
    section: str | None = None
    paragraph_index: int | None = None
    pdf_page_index: int | None = None
    printed_page_label: str | None = None
    embedding_token_count: int
    domain_tags: list[str]
    ecosystem_tags: list[str]
    geography_tags: list[str]
    review_status: Literal["draft", "reviewed"]
    kb_version: str
    raw_path: str
    raw_sha256: str
    locator: str


class SourceParentPassage(StrictModel):
    parent_id: str
    source_id: str
    text: str
    text_sha256: str
    raw_path: str
    raw_sha256: str
    locator: str
    section: str | None = None
    paragraph_index: int | None = None
    pdf_page_index: int | None = None
    kb_version: str


class ChatRequest(StrictModel):
    session_id: str
    message: str = Field(default="", max_length=8000)
    site_patch: SitePatch | None = None
    mode: Literal["advice", "hypothetical"] = "advice"

    @model_validator(mode="after")
    def requires_content(self) -> ChatRequest:
        if not self.message.strip() and self.site_patch is None:
            raise ValueError("message or site_patch is required")
        return self


class ClarifyingQuestion(StrictModel):
    field: str
    question: str
    why_it_matters: str
    answer_options: list[str] | None = None
    blocking: bool


class Citation(StrictModel):
    source_id: str
    title: str
    publisher: str
    year: int | None = None
    url: str
    locator: str
    excerpt: str
    evidence_claim: str
    supporting_evidence_ids: list[str]


class ChatResponse(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    session_id: str
    turn_id: str
    kb_version: str
    status: Literal["clarify", "recommend", "insufficient_evidence", "out_of_scope", "degraded"]
    summary: str
    known_conditions: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    questions: list[ClarifyingQuestion] = Field(default_factory=list, max_length=2)
    recommendations: list[dict[str, Any]] = Field(default_factory=list, max_length=3)
    rejected_alternatives: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list, max_length=12)
    current_profile: dict[str, Any] = Field(default_factory=dict)
    literature_illustrations: list[dict[str, Any]] = Field(default_factory=list)
    trace_id: str
    trace_excerpts: list[dict[str, Any]] = Field(default_factory=list)


class CompositionChoice(StrictModel):
    selected_action_ids: list[str] = Field(max_length=3)
    response_mode: Literal["conditional_evidence_assessment"]


class EvidenceChoice(StrictModel):
    selected_evidence_ids: list[str] = Field(max_length=6)
    focus: Literal["evidence", "comparison", "monitoring", "local_prediction", "site_advice"]


ObservationField = Literal[
    "location.region",
    "location.latitude",
    "location.longitude",
    "soil.ph",
    "soil.organic_carbon_pct",
    "soil.moisture_vwc_pct",
    "soil.moisture_condition",
    "climate.annual_rainfall_mm",
    "climate.rainfall_pattern",
    "climate.rainfall_seasonality_detail",
    "climate.mean_temperature_c",
    "land.use_type",
    "land.crop_system",
    "land.irrigation_available",
    "land.habitat_cover_pct",
    "biodiversity.observed_species_richness",
    "biodiversity.habitat_types",
    "biodiversity.decline_reported",
    "pressures.pesticide_use",
    "pressures.pollution",
    "pressures.recent_land_clearing",
]


class ExtractedObservation(StrictModel):
    """A candidate fact must point to literal user text before activation."""

    field: ObservationField
    value: float | bool | str | list[str] | None
    raw_text: str = Field(min_length=1, max_length=500)
    explicit_unit: str | None = Field(max_length=40)
    is_correction: bool


class TextExtraction(StrictModel):
    intent: Literal["new_information", "question", "correction", "hypothetical", "reset", "out_of_scope"]
    observations: list[ExtractedObservation] = Field(max_length=12)
    hypothetical: bool
