"""Action-aware clarification over normalized, event-backed site state."""
from __future__ import annotations

import re

UNKNOWN_VALUES = {"unknown", "not known", "unsure", "declined"}


def active_values(state: dict) -> dict[str, object]:
    return {field: event["value"] for field, event in state.get("current", {}).items() if event is not None}


def was_answered(state: dict, field: str) -> bool:
    """True for known values, zero, explicit null, and explicit unknown."""
    return field in state.get("current", {}) or field in state.get("declined_questions", [])


def usable_value(values: dict[str, object], field: str) -> bool:
    value = values.get(field)
    if value is None:
        return False
    return not (isinstance(value, str) and value.casefold().strip() in UNKNOWN_VALUES)


class ClarificationService:
    def __init__(self, actions: dict[str, dict], cards: dict[str, dict]):
        self.actions = actions
        self.cards = cards

    def prospective_action(self, state: dict, message: str) -> str | None:
        values = active_values(state)
        land = values.get("land.use_type")
        goal = message.casefold()
        if values.get("pressures.pesticide_use"):
            return "pesticide_pressure_review"
        if land in {"forest", "grassland", "wetland"}:
            return "protect_existing_native_habitat"
        if land in {"crop", "pasture"} and re.search(r"habitat|margin|strip|connect", goal):
            return "locally_appropriate_habitat_strips"
        if land == "crop" and re.search(r"cover crop", goal):
            return "conditional_cover_cropping"
        if land == "crop":
            return "crop_diversification"
        return None

    def _reason(self, action_id: str | None, field: str, retrieved_ids: set[str]) -> str:
        evidence_available = lambda evidence_id: evidence_id in retrieved_ids
        if action_id == "crop_diversification":
            if field == "land.crop_system":
                return "The retrieved diversification synthesis compares diversified cropping with less-diverse systems, so the current crop system is needed to define a relevant comparison."
            if field == "land.irrigation_available" and evidence_available("ev_dryland_water_budget"):
                return "The retrieved ICRISAT water-budget evidence requires cropping choices to fit available water; supplemental irrigation changes that feasibility assessment."
            if field.startswith("climate."):
                return "The crop-diversification action requires the retrieved dryland water-budget evidence to be applied with an explicit seasonal water context."
            return "The retrieved diversification evidence supports a conditional assessment only when the observed biodiversity concern and local cropping context are explicit."
        if action_id == "conditional_cover_cropping":
            return "The retrieved cover-crop evidence distinguishes water use while the cover is growing from possible water conservation after termination, so seasonal water availability is decision-critical."
        if action_id in {"protect_existing_native_habitat", "locally_appropriate_habitat_strips"}:
            return "The retrieved IPBES evidence calls for locally tailored protection, restoration or reconnection, so the existing habitat condition must be known before selecting a design."
        if action_id == "pesticide_pressure_review":
            return "The retrieved pesticide evidence supports exposure assessment rather than assumed causation; this detail determines which exposure pathway should be reviewed."
        return "This observation determines which evidence-backed action class is applicable."

    def questions(
        self,
        state: dict,
        message: str,
        *,
        action_id: str | None = None,
        retrieved_ids: set[str] | None = None,
    ) -> list[dict]:
        values = active_values(state)
        retrieved = retrieved_ids or set()
        if state.get("unresolved_conflicts"):
            field = state["unresolved_conflicts"][0]
            return [{"field": field, "question": "Which of the conflicting values should be used?", "why_it_matters": "The conflicting observation is held separately and cannot change the active profile until you resolve it.", "answer_options": None, "blocking": True}]
        if not usable_value(values, "land.use_type") and not was_answered(state, "land.use_type"):
            return [{"field": "land.use_type", "question": "Is this cropland, pasture, forest, grassland, wetland, or another land type?", "why_it_matters": self._reason(None, "land.use_type", retrieved), "answer_options": ["crop", "pasture", "forest", "grassland", "wetland", "other"], "blocking": True}]

        action_id = action_id or self.prospective_action(state, message)
        land = values.get("land.use_type")
        annual_known = usable_value(values, "climate.annual_rainfall_mm")
        season_known = usable_value(values, "climate.rainfall_seasonality_detail") or usable_value(values, "climate.rainfall_pattern")
        dry_or_seasonal = values.get("climate.rainfall_pattern") in {"low", "erratic", "seasonally_dry"} or (annual_known and usable_value(values, "climate.rainfall_seasonality_detail"))

        if action_id in {"crop_diversification", "conditional_cover_cropping"} and land == "crop":
            has_rainfall_quantity = bool(re.search(r"\b\d+(?:\.\d+)?\s*(?:mm|millimet(?:er|re)s?)\b", message.casefold()))
            explicit_annual = bool(re.search(r"annual|per year|/year|annually", message.casefold()))
            distributed_total = bool(re.search(r"concentrated\s+in\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+months?", message.casefold())) and not bool(re.search(r"monthly|per month|/month", message.casefold()))
            has_period = explicit_annual or distributed_total
            if has_rainfall_quantity and not has_period:
                return [{"field": "climate.annual_rainfall_mm", "question": "What period does the reported rainfall total cover—for example, per year or per month?", "why_it_matters": "The rainfall period is ambiguous, and the water-budget evidence cannot be applied by silently converting it to an annual value.", "answer_options": None, "blocking": True}]
            if not season_known and not was_answered(state, "climate.rainfall_pattern"):
                return [{"field": "climate.rainfall_pattern", "question": "How reliable is water availability through the growing season (low, erratic, seasonal, or adequate)?", "why_it_matters": self._reason(action_id, "climate.rainfall_pattern", retrieved), "answer_options": ["low", "erratic", "seasonally dry", "adequate", "I don't know"], "blocking": False}]
            if dry_or_seasonal and not was_answered(state, "land.irrigation_available"):
                return [{"field": "land.irrigation_available", "question": "Is supplemental irrigation available?", "why_it_matters": self._reason(action_id, "land.irrigation_available", retrieved), "answer_options": ["irrigation available", "no irrigation", "I don't know"], "blocking": False}]
            if action_id == "crop_diversification" and not usable_value(values, "land.crop_system") and not was_answered(state, "land.crop_system"):
                return [{"field": "land.crop_system", "question": "What crop or crop system is currently used (for example, monoculture wheat or a rotation)?", "why_it_matters": self._reason(action_id, "land.crop_system", retrieved), "answer_options": None, "blocking": False}]

        if action_id in {"protect_existing_native_habitat", "locally_appropriate_habitat_strips"} and not usable_value(values, "biodiversity.habitat_types") and not was_answered(state, "biodiversity.habitat_types"):
            return [{"field": "biodiversity.habitat_types", "question": "What habitat or vegetation types are currently present, and do they appear intact, fragmented, or degraded?", "why_it_matters": self._reason(action_id, "biodiversity.habitat_types", retrieved), "answer_options": None, "blocking": False}]
        if action_id and not usable_value(values, "biodiversity.decline_reported") and not was_answered(state, "biodiversity.decline_reported"):
            return [{"field": "biodiversity.decline_reported", "question": "What biodiversity change or ecological concern have you observed, if any?", "why_it_matters": self._reason(action_id, "biodiversity.decline_reported", retrieved), "answer_options": None, "blocking": False}]
        return []
