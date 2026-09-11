from __future__ import annotations

import pytest

from app.schemas import ChatRequest, TextExtraction
from app.services.state import (
    active_values,
    canonicalize_values,
    extract_text_patch,
    validate_text_extraction,
)
from app.services.verification import verify_response


def test_contract_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError, match="finite"):
        ChatRequest(session_id="s", site_patch={"climate": {"mean_temperature_c": float("inf")}})


def test_text_extraction_does_not_invent_monthly_or_negative_facts() -> None:
    values, _ = extract_text_patch("Rainfall is 60 mm this month. No pesticide use. No irrigation is available.")
    assert "climate.annual_rainfall_mm" not in values
    assert "pressures.pesticide_use" not in values
    assert values["land.irrigation_available"] is False


def test_deterministic_parser_handles_explicit_annual_and_negated_forms() -> None:
    values, _ = extract_text_patch("Rainfall is 900 mm/year concentrated in four months. Irrigation is not available. I do not use pesticides.")
    assert values["climate.annual_rainfall_mm"] == 900.0
    assert values["land.irrigation_available"] is False
    assert "pressures.pesticide_use" not in values


def test_structured_text_extraction_requires_spans_and_canonical_patch() -> None:
    extraction = TextExtraction.model_validate({"intent": "new_information", "hypothetical": False, "observations": [{"field": "soil.organic_carbon_pct", "value": 0.3, "raw_text": "SOC is 0.3%", "explicit_unit": "%", "is_correction": False}, {"field": "climate.annual_rainfall_mm", "value": 60, "raw_text": "60 mm this month", "explicit_unit": "mm", "is_correction": False}]})
    values, _, warnings = validate_text_extraction(extraction, "SOC is 0.3%; rainfall was 60 mm this month.")
    assert values == {"soil.organic_carbon_pct": 0.3}
    assert warnings


def test_event_backed_active_values_and_canonical_normalization() -> None:
    state = {"current": {"land.use_type": {"value": "crop"}, "climate.rainfall_pattern": {"value": "erratic"}, "cleared": None}}
    assert active_values(state) == {"land.use_type": "crop", "climate.rainfall_pattern": "erratic"}
    assert canonicalize_values({"location.region": "semiarid", "land.use_type": "cropland", "climate.rainfall_pattern": "seasonal"}) == {
        "location.region": "semi-arid region",
        "land.use_type": "crop",
        "climate.rainfall_pattern": "seasonally_dry",
    }


def test_validator_rejects_fabricated_actions_edges_and_predictions() -> None:
    state = {"current": {"land.use_type": {"observation_id": "o1", "value": "crop"}, "soil.ph": {"observation_id": "o2", "value": 6.5}, "climate.rainfall_pattern": {"observation_id": "o3", "value": "low"}}}
    card = {"evidence_id": "good", "review_status": "reviewed"}
    response = {"summary": "Species richness rises 99%", "recommendations": [{"action_id": "bad", "evidence_ids": ["draft"], "used_observation_ids": ["o1"], "interaction_paths": [{"edge_ids": ["fake"], "observation_ids": ["o1"], "evidence_ids": ["draft"]}], "impacted_metrics": [{"estimate_type": "local_model_prediction", "quantitative_estimate": 1}], "action_steps": [], "rationale": "Will double species richness", "tradeoffs": []}]}
    assert verify_response(response, {"good": card}, state, actions={"good_action": {"enabled": True}}, edges=[], supplied_evidence_ids={"good"})
