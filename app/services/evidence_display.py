"""Deterministic, source-exact excerpts suitable for the public evidence UI."""
from __future__ import annotations

import re

ANCHORS = {
    "ev_diversification_biodiversity": "Diversification practices enhanced biodiversity (lnRR = 0.34",
    "ev_diversification_context": "Variability in responses and occurrence of trade-offs highlight the context dependency",
    "ev_diversification_scope": "cropping systems with less diverse farming practices typical of mainstream agriculture",
    "ev_cover_water_risk": "Cover crops use soil water while they are growing",
    "ev_cover_residue_water": "Once killed, however, cover crop residues may increase water availability",
    "ev_cover_termination": "Time of termination becomes more critical as the probability of precipitation decreases",
    "ev_cover_dryland_limit": "Cover crop use in dryland systems is often limited by moisture availability",
    "ev_pesticide_soil_hazard": "70.5% of tested parameters showed negative effects",
    "ev_pesticide_scope": "nearly 400 studies on the effects of pesticides on non-target invertebrates that develop in the soil",
    "ev_pressure_monitoring": "unique risk profile to each soil-dwelling species",
    "ev_dryland_water_budget": "The theme applies water budgeting approaches",
    "ev_soil_health_context": "Healthy soils are the foundation",
    "ev_crop_climate_context": "stress-tolerant seed varieties adapted to drought, heat",
    "ev_land_change_driver": "changes in land and sea use",
    "ev_habitat_reconnection": "restoring or reconnecting damaged or fragmented habitats where necessary",
    "ev_natural_habitat_scope": "locally tailored choices about conservation, restoration, sustainable use and development connectivity",
    "ev_management_context": "Different types of agricultural practices and systems affect the soil biota",
    "ev_soil_moisture_interaction": "It is related to moisture, temperature and aeration",
    "ev_soil_biology_context": "primary driving agents of nutrient cycling",
}

# Figure SPM.8 exposes species richness only as an extracted chart axis. It is
# valid offline provenance, but not an interpretable public passage.
PUBLICLY_UNSUPPORTED = {"ev_habitat_monitoring"}


def display_claim(card: dict) -> str:
    """Narrow public wording to what the acquired linked parent supports."""
    if card["evidence_id"] == "ev_management_context":
        return "FAO explains that agricultural practices affect soil biota differently, with positive or negative responses depending on the organism group and management."
    return card["claim_summary"]


def _sentence_span(text: str, anchor_start: int, anchor_end: int) -> str:
    before = list(re.finditer(r"[.!?](?:\s|$)", text[:anchor_start]))
    start = before[-1].end() if before else 0
    after = re.search(r"[.!?](?:\s|$)", text[anchor_end:])
    end = anchor_end + after.end() if after else len(text)
    return text[start:end].strip()


def _sentence_sequence(text: str, start: int, count: int) -> str:
    end = start
    for _ in range(count):
        match = re.search(r"[.!?](?:\s|$)", text[end:])
        if not match:
            return text[start:].strip()
        end += match.end()
    return text[start:end].strip()


def _sentence_start(text: str, position: int) -> int:
    before = list(re.finditer(r"[.!?](?:\s|$)", text[:position]))
    return before[-1].end() if before else 0


def complete_display_passage(evidence_id: str, parent_text: str) -> str | None:
    """Return a complete exact source span, or fail closed."""
    if evidence_id in PUBLICLY_UNSUPPORTED:
        return None
    anchor = ANCHORS.get(evidence_id)
    if not anchor:
        return None
    position = parent_text.casefold().find(anchor.casefold())
    if position < 0:
        return None
    if evidence_id in {"ev_habitat_reconnection", "ev_natural_habitat_scope"}:
        start = parent_text.rfind("•", 0, position)
        end = parent_text.find("•", position)
        if start < 0:
            return None
        return parent_text[start:(end if end >= 0 else len(parent_text))].strip()
    preserve_parent = {
        "ev_cover_water_risk", "ev_cover_residue_water", "ev_cover_termination",
        "ev_dryland_water_budget",
        "ev_soil_health_context", "ev_management_context",
        "ev_crop_climate_context", "ev_soil_biology_context",
    }
    if evidence_id in preserve_parent:
        return parent_text.strip()
    if evidence_id == "ev_diversification_context":
        start = parent_text.find("Overall, diversification")
        return parent_text[start:].strip() if start >= 0 else None
    if evidence_id == "ev_soil_moisture_interaction":
        start = parent_text.find("Soil organic matter content is a function")
        return _sentence_sequence(parent_text, start, 3) if start >= 0 else None
    if evidence_id == "ev_pesticide_scope":
        return _sentence_sequence(parent_text, _sentence_start(parent_text, position), 3)
    if evidence_id == "ev_cover_dryland_limit":
        return _sentence_sequence(parent_text, _sentence_start(parent_text, position), 2)
    return _sentence_span(parent_text, position, position + len(anchor))
