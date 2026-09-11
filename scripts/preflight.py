"""Explicit, no-secret Phase 0 Groq structured-output compatibility check."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.schemas import CompositionChoice, TextExtraction
from app.services.llm_client import LLMClient


def main() -> int:
    settings = get_settings()
    print(f"Python/runtime configuration: model={settings.llm_model}; base_url={settings.llm_base_url}")
    if not settings.provider_configured:
        print("BLOCKED: GROQ_API_KEY is not configured; no provider request was sent.")
        return 2
    try:
        client = LLMClient(settings)
        extraction = client.structured(
            system="Extract only explicit facts. Every raw_text must be a literal substring. Return the required schema.",
            user="SOC is 0.3% and annual rainfall is 900 mm.",
            schema=TextExtraction,
        )
        reply = client.structured(
            system="Select only from the supplied action allowlist. Return the required JSON schema.",
            user='{"allowed_action_ids":["crop_diversification"],"request":"choose one eligible action"}',
            schema=CompositionChoice,
        )
    except Exception as exc:  # noqa: BLE001 - expected provider boundary errors are reported without secrets
        print(f"FAILED: Chat Completions strict JSON-schema check: {type(exc).__name__}: {exc}")
        return 1
    extracted = {item.field: item.value for item in extraction.observations}
    if extracted.get("soil.organic_carbon_pct") != 0.3 or extracted.get("climate.annual_rainfall_mm") != 900:
        print("FAILED: extraction schema did not return the expected explicit observations.")
        return 1
    if any(item.raw_text not in "SOC is 0.3% and annual rainfall is 900 mm." for item in extraction.observations):
        print("FAILED: extraction returned an unsupported raw-text span.")
        return 1
    if reply.selected_action_ids != ["crop_diversification"] or reply.response_mode != "conditional_evidence_assessment":
        print("FAILED: returned JSON did not satisfy the semantic smoke assertion.")
        return 1
    print("PASSED: Groq Chat Completions strict JSON-schema response validated locally.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
