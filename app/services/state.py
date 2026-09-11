from __future__ import annotations

import re
from copy import deepcopy
from uuid import uuid4

from app.schemas import SitePatch, TextExtraction

FIELD_UNITS = {"soil.organic_carbon_pct": "%_mass", "soil.ph": "pH", "soil.moisture_vwc_pct": "%_vwc", "climate.annual_rainfall_mm": "mm/year", "climate.mean_temperature_c": "celsius"}


def concept_for_field(field: str) -> str | None:
    if field == "land.use_type": return "land_system"
    if field == "land.crop_system": return "cropping_pattern"
    if field.startswith("climate.") or field in {"soil.moisture_vwc_pct", "soil.moisture_condition", "land.irrigation_available"}: return "water_climate"
    if field == "soil.organic_carbon_pct": return "soil_carbon"
    if field.startswith("soil."): return "soil_condition"
    if field == "biodiversity.habitat_types": return "habitat"
    if field.startswith("biodiversity."): return "biodiversity_condition"
    if field.startswith("pressures."): return "pressure"
    return None


def active_values(state: dict | None) -> dict[str, object]:
    """Return scalar active values from the event-backed state representation."""
    return {
        field: event["value"]
        for field, event in (state or {}).get("current", {}).items()
        if event is not None
    }


def canonicalize_values(values: dict[str, object]) -> dict[str, object]:
    """Normalize equivalent model/user spellings at the state boundary."""
    normalized = dict(values)
    region = normalized.get("location.region")
    if isinstance(region, str):
        compact = " ".join(region.strip().lower().replace("semiarid", "semi-arid").split())
        if compact in {"semi-arid", "semi-arid region"}:
            normalized["location.region"] = "semi-arid region"
    land = normalized.get("land.use_type")
    if isinstance(land, str) and land.strip().lower() in {"cropland", "crop land"}:
        normalized["land.use_type"] = "crop"
    rainfall = normalized.get("climate.rainfall_pattern")
    if rainfall == "seasonal":
        normalized["climate.rainfall_pattern"] = "seasonally_dry"
    return normalized


def flatten_patch(patch: SitePatch) -> dict[str, object]:
    result: dict[str, object] = {}
    for section in ("location", "soil", "climate", "land", "biodiversity", "pressures"):
        item = getattr(patch, section)
        if item is None:
            continue
        for key in item.model_fields_set:
            result[f"{section}.{key}"] = getattr(item, key)
    if "notes" in patch.model_fields_set:
        result["notes"] = patch.notes
    return result


def extract_text_patch(message: str, current: dict | None = None) -> tuple[dict[str, object], bool, str | None]:
    """Bounded deterministic fallback for explicit, canonical observations."""
    text = message.lower()
    short_answer = re.sub(r"[^a-z\s'-]", "", text).strip()
    active_current = active_values(current)
    answered_fields = set((current or {}).get("current", {}))
    values: dict[str, object] = {}
    hypothetical = bool(re.search(r"\bwhat if\b|\bhypothetical\b", text))
    patterns = [(r"(?:soc|soil organic carbon)\s*(?:is|=|of)?\s*(\d+(?:\.\d+)?)\s*%", "soil.organic_carbon_pct", float), (r"\bph\s*(?:is|=|of)?\s*(\d+(?:\.\d+)?)", "soil.ph", float), (r"annual rainfall\s*(?:is|=|of)?\s*(\d+(?:\.\d+)?)\s*(?:mm|millimet(?:er|re)s?)", "climate.annual_rainfall_mm", float), (r"(\d+(?:\.\d+)?)\s*(?:mm|millimet(?:er|re)s?)\s+annual rainfall", "climate.annual_rainfall_mm", float), (r"rainfall\s*(?:is|=|of)?\s*(\d+(?:\.\d+)?)\s*(?:mm|millimet(?:er|re)s?)\s*(?:/year|per year|annually)", "climate.annual_rainfall_mm", float), (r"(?:temperature|temp)\s*(?:is|=|of)?\s*(-?\d+(?:\.\d+)?)\s*(?:c|°c)", "climate.mean_temperature_c", float)]
    for pattern, field, converter in patterns:
        match = re.search(pattern, text)
        if match:
            values[field] = converter(match.group(1))
    annual_total = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm|millimet(?:er|re)s?)\s*(?:of\s+rainfall\s*)?(?:annually|per year|/year)\b", text)
    if annual_total:
        values["climate.annual_rainfall_mm"] = float(annual_total.group(1))
    soc_total = re.search(r"(?:soc|soil organic carbon)\s*(?:is\s+)?(?:about|around|approximately)\s+(\d+(?:\.\d+)?)\s*%", text)
    if soc_total:
        values["soil.organic_carbon_pct"] = float(soc_total.group(1))
    if re.search(r"\b(?:short|seasonal)\s+monsoon\b", text):
        values["climate.rainfall_seasonality_detail"] = "user reports rainfall during a short or seasonal monsoon"
    if re.search(r"\brain[ -]?fed\b", text):
        values["land.irrigation_available"] = False
    concentrated_total = re.search(
        r"(?:annual\s+rainfall\s*(?:is|=|of)?\s*)?(\d+(?:\.\d+)?)\s*(?:mm|millimet(?:er|re)s?)(?:\s+of\s+rainfall)?\s*[,;]?\s*concentrated\s+in\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+months?",
        text,
    )
    if concentrated_total and not re.search(r"\b(?:monthly|per month|/month)\b", text):
        # This construction reports one rainfall total and explicitly states
        # how that total is distributed through the year. It is distinct from
        # an unqualified "350 mm", whose period remains ambiguous.
        values["climate.annual_rainfall_mm"] = float(concentrated_total.group(1))
        values["climate.rainfall_seasonality_detail"] = f"rainfall concentrated in {concentrated_total.group(2)} months"
    # A correction such as "I meant 0.8%, not 0.3%" is only accepted where
    # the field is unambiguous from the active profile or explicit SOC wording.
    correction = re.search(r"\bi meant\s+(\d+(?:\.\d+)?)\s*%\s*,?\s*not\s+\d+(?:\.\d+)?\s*%", text)
    active_fields = set((current or {}).get("current", {})) | set((current or {}).get("unresolved_conflicts", []))
    if correction and ("soil.organic_carbon_pct" in active_fields or "soc" in text or "organic carbon" in text):
        values["soil.organic_carbon_pct"] = float(correction.group(1))
    if re.search(r"\b(?:soc|soil organic carbon)\s+(?:is\s+)?(?:unknown|not known)\b", text): values["soil.organic_carbon_pct"] = None
    if re.search(r"\bsoil\s+ph\s+(?:is\s+)?(?:unknown|not known)\b", text): values["soil.ph"] = None
    if re.search(r"\bsoil\s+moisture\s+(?:is\s+)?(?:unknown|not known)\b", text): values["soil.moisture_vwc_pct"] = None
    if re.search(r"\bsoil\s+(?:measurements?|values?)\s+(?:are\s+|is\s+)?(?:unknown|not known)\b", text):
        values.update({"soil.organic_carbon_pct": None, "soil.ph": None, "soil.moisture_vwc_pct": None})
    if re.search(r"\blow rainfall\b", text): values["climate.rainfall_pattern"] = "low"
    if re.search(r"\bsemi[ -]?arid(?:\s+region)?\b", text): values["location.region"] = "semi-arid region"
    if "erratic rainfall" in text: values["climate.rainfall_pattern"] = "erratic"
    # A short reply is interpreted only against the already-known land
    # context. This accepts answers to the immediately relevant rainfall
    # question without treating the same adjective in a longer sentence as a
    # site fact.
    unknown_reply = short_answer in {"unknown", "i don't know", "i dont know"}
    prior_question = next(iter((current or {}).get("last_question_fields", [])), None)
    if unknown_reply and prior_question and prior_question not in answered_fields:
        values[prior_question] = None
    elif prior_question == "land.use_type" and short_answer in {"crop", "cropland", "pasture", "forest", "grassland", "wetland", "urban", "other",
                                                                          "another land type", "other land type", "barren", "degraded", "shrubland",
                                                                          "savanna", "orchard", "garden", "agroforestry", "mixed", "another"}:
        values[prior_question] = "crop" if short_answer in {"crop", "cropland"} else (
            "other" if short_answer in {"other", "another land type", "other land type", "another", "barren", "degraded",
                                         "shrubland", "savanna", "orchard", "garden", "agroforestry", "mixed"} else short_answer
        )
    elif prior_question == "land.irrigation_available" and short_answer in {"yes", "available", "irrigation available"}:
        values[prior_question] = True
    elif prior_question == "land.irrigation_available" and short_answer in {"no", "none", "no irrigation", "not available"}:
        values[prior_question] = False
    elif prior_question == "climate.annual_rainfall_mm":
        contextual_rainfall = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:mm|millimet(?:er|re)s?)\s*(?:/year|per year|annually)\s*", text)
        if contextual_rainfall:
            values[prior_question] = float(contextual_rainfall.group(1))
    elif prior_question in {"soil.organic_carbon_pct", "soil.moisture_vwc_pct"}:
        contextual_percent = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*%\s*", text)
        if contextual_percent:
            values[prior_question] = float(contextual_percent.group(1))
    elif prior_question == "soil.ph":
        contextual_ph = re.fullmatch(r"\s*(?:ph\s*)?(\d+(?:\.\d+)?)\s*", text)
        if contextual_ph:
            values[prior_question] = float(contextual_ph.group(1))
    elif prior_question == "land.crop_system" and 0 < len(message.strip()) <= 200 and re.search(r"\b(?:wheat|rice|maize|corn|soybean|crop|rotation|monoculture|intercrop|mixed|fallow)\b", text):
        values[prior_question] = message.strip()
    elif prior_question == "biodiversity.habitat_types" and 0 < len(message.strip()) <= 300 and re.search(r"\b(?:habitat|grassland|forest|woodland|wetland|pasture|hedgerow|margin|scrub|native|semi-natural|fragmented|degraded|intact)\b", text):
        values[prior_question] = [message.strip()]
    elif prior_question == "biodiversity.decline_reported" and 0 < len(message.strip()) <= 300 and re.search(r"\b(?:declin|fewer|increase|decrease|loss|change|none|no change|unknown|concern|insects?|birds?|pollinators?|species)\b", text):
        values[prior_question] = message.strip()
    if (
        not unknown_reply
        and active_current.get("land.use_type")
        and "climate.rainfall_pattern" not in answered_fields
        and short_answer in {"low", "erratic", "seasonal", "seasonally dry", "adequate", "unknown", "i don't know", "i dont know"}
    ):
        values["climate.rainfall_pattern"] = {
            "seasonal": "seasonally_dry",
            "seasonally dry": "seasonally_dry",
            "i don't know": "unknown",
            "i dont know": "unknown",
        }.get(short_answer, short_answer)
    elif unknown_reply and prior_question is None and active_current.get("land.use_type") == "crop":
        # Preserve an explicit unknown against the next unanswered canonical
        # prerequisite. A stored clear event prevents the UI from asking the
        # identical question forever without pretending the value is known.
        if (
            active_current.get("climate.rainfall_pattern") in {"low", "erratic", "seasonally_dry"}
            and "land.irrigation_available" not in answered_fields
        ):
            values["land.irrigation_available"] = None
        elif "land.crop_system" not in answered_fields:
            values["land.crop_system"] = "unknown"
        elif "biodiversity.decline_reported" not in answered_fields:
            values["biodiversity.decline_reported"] = "unknown"
    if "concentrated" in text and "month" in text: values.setdefault("climate.rainfall_seasonality_detail", "rainfall concentrated in part of the year")
    if "monoculture" in text: values["land.crop_system"] = "monoculture"
    only_crop = re.search(r"\b(?:grow|growing|plant|planting)\s+only\s+(wheat|rice|maize|corn|soybean)\b", text)
    if only_crop: values["land.crop_system"] = f"monoculture {only_crop.group(1)}"
    for crop in ("wheat", "rice", "maize", "corn", "soybean"):
        if crop in text:
            crop_system = str(values.get("land.crop_system", ""))
            if crop not in crop_system.split():
                values["land.crop_system"] = f"{crop_system} {crop}".strip()
            values["land.use_type"] = "crop"
    if "cropland" in text or "crop production" in text or short_answer == "crop": values.setdefault("land.use_type", "crop")
    for kind in ("grassland", "wetland", "forest", "pasture"):
        if kind in text: values["land.use_type"] = kind
    if re.search(r"\b(?:use|using|used|apply|applying|applied|concern(?:ed)? about|expos(?:ed|ure) to)\b[^.?!]{0,40}\bpesticides?\b|\bpesticide\s+(?:use|exposure|concern)\b", text) and not re.search(r"\b(no|without|never)\s+(?:use\s+of\s+)?pesticides?|\b(?:do|does|did)\s+not\s+use\s+pesticides?", text): values["pressures.pesticide_use"] = "reported use or concern"
    if "pollution" in text: values["pressures.pollution"] = "reported concern"
    if "land clearing" in text or "land-clearing" in text: values["pressures.recent_land_clearing"] = True
    if "habitat diversity" in text or "habitat types" in text: values["biodiversity.habitat_types"] = ["user-reported habitat diversity"]
    if "biodiversity is declining" in text or "biodiversity decline" in text: values["biodiversity.decline_reported"] = "reported decline"
    if re.search(r"\b(?:fewer|declining|reduced)\b[^.]{0,80}\b(?:insects?|birds?|pollinators?|species)\b", text): values["biodiversity.decline_reported"] = "user reported fewer organisms"
    if re.search(r"\bsoil moisture\s+(?:is\s+)?low\b", text): values["soil.moisture_condition"] = "low"
    if "irrigat" in text:
        if re.search(r"\b(no|without|not)\s+irrigat|\birrigation\s+(?:is\s+)?not\s+available", text): values["land.irrigation_available"] = False
        elif "available" in text or "could" in text: values["land.irrigation_available"] = True
    return canonicalize_values(values), hypothetical, None


def validate_text_extraction(extraction: TextExtraction, message: str) -> tuple[dict[str, object], bool, list[str], str | None]:
    """Turn span-supported model candidates into the same patch used by JSON.

    A model result is advisory. Values outside the canonical patch contract,
    unsupported spans, or ambiguous annual-rainfall units are dropped rather
    than becoming observations.
    """
    nested: dict[str, dict[str, object]] = {}
    warnings: list[str] = []
    lowered = message.casefold()
    for observation in extraction.observations:
        if observation.raw_text.casefold() not in lowered:
            warnings.append(f"Dropped {observation.field}: extraction span was not found in the user text.")
            continue
        if observation.field == "climate.annual_rainfall_mm":
            raw = observation.raw_text.casefold()
            annual_markers = ("annual", "per year", "/year", "annually", "mm/year")
            distributed_total = bool(re.search(r"\bconcentrated\s+in\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+months?\b", raw)) and not any(marker in raw for marker in ("monthly", "per month", "/month"))
            if not any(marker in raw for marker in annual_markers) and not distributed_total:
                warnings.append("Dropped annual rainfall candidate without an explicit annual unit or meaning.")
                continue
            if "month" in raw and not any(marker in raw for marker in annual_markers) and not distributed_total:
                warnings.append("Dropped monthly rainfall candidate; annual rainfall was not inferred.")
                continue
        section, key = observation.field.split(".", 1)
        nested.setdefault(section, {})[key] = observation.value
    try:
        patch = SitePatch.model_validate(nested)
    except ValueError as exc:
        warnings.append(f"Dropped invalid structured extraction: {exc.errors()[0]['msg']}")
        return {}, extraction.hypothetical or extraction.intent == "hypothetical", warnings, extraction.active_goal
    return canonicalize_values(flatten_patch(patch)), extraction.hypothetical or extraction.intent == "hypothetical", warnings, extraction.active_goal


class StateService:
    def apply(self, state: dict, values: dict[str, object], turn_id: str, raw_text: str, *, hypothetical: bool = False) -> tuple[dict, list[dict]]:
        target = deepcopy(state) if hypothetical else state
        events: list[dict] = []
        for field, value in values.items():
            if field == "notes":
                target["notes"].append({"text": value, "turn_id": turn_id})
                continue
            target["last_event_seq"] += 1
            operation = "clear" if value is None else "set"
            event = {"observation_id": f"obs_{uuid4().hex[:12]}", "field": field, "value": value, "unit": FIELD_UNITS.get(field), "qualitative_value": value if isinstance(value, str) else None, "origin": "user_reported", "source_turn_id": turn_id, "raw_text": raw_text, "sample_depth_cm": None, "period_start": None, "period_end": None, "method": None, "event_seq": target["last_event_seq"], "operation": operation}
            target["current"][field] = event if operation == "set" else None
            target["last_question_fields"] = [asked for asked in target.get("last_question_fields", []) if asked != field]
            if operation == "clear" and field not in target["declined_questions"]:
                target["declined_questions"].append(field)
            elif operation == "set" and field in target["declined_questions"]:
                target["declined_questions"].remove(field)
            events.append(event)
        if hypothetical:
            state["hypothetical"] = {"current": target["current"], "description": raw_text}
        
        # Persist active_goal logic: only update if explicitly provided, else keep existing
        if "active_goal" in values:
            target["active_goal"] = values["active_goal"]
        
        return target, events

    @staticmethod
    def concept_count(state: dict) -> int:
        concepts = set()
        for field, event in state["current"].items():
            if event is None or event.get("value") is None or str(event.get("value", "")).casefold() == "unknown":
                continue
            concept = concept_for_field(field)
            if concept: concepts.add(concept)
        return len(concepts)
