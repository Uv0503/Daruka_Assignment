#!/usr/bin/env python3
"""Instrument the LLM boundary and prove retrieved exact passages reach it.

No provider request is made: the capture adapter stands at the same
`LLMClient.structured` boundary and validates the exact user payload passed by
the composer.  This is intentionally stronger than checking a response trace.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.main import app
from app.schemas import CompositionChoice


class CaptureProvider:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def structured(self, *, system: str, user: str, schema: type):  # type: ignore[no-untyped-def]
        payload = json.loads(user)
        self.calls.append({"system": system, "payload": payload, "schema": schema.__name__})
        if schema is not CompositionChoice:
            raise AssertionError(f"unexpected LLM schema: {schema.__name__}")
        return CompositionChoice(
            selected_action_ids=[payload["allowed_action_ids"][0]],
            response_mode="conditional_evidence_assessment",
        )


def state_with_e02_profile() -> dict:
    return {
        "current": {
            "soil.organic_carbon_pct": {"value": 0.3},
            "climate.rainfall_pattern": {"value": "low"},
            "land.use_type": {"value": "crop"},
            "land.crop_system": {"value": "monoculture wheat"},
            "location.region": {"value": "semi-arid region"},
        },
        "history": [], "unresolved_conflicts": [], "last_question_fields": [],
    }


def main() -> int:
    orchestrator = app.state.orchestrator
    state = state_with_e02_profile()
    candidates = ["crop_diversification", "conditional_cover_cropping"]
    packet = orchestrator.retriever.retrieve(state, "Assess options for a water-constrained wheat farm", candidates)
    ranked, _ = orchestrator.reasoner.evaluate(state, packet["card_ids"])
    assert ranked, "fixture has no eligible ranked action"
    original = orchestrator.llm
    capture = CaptureProvider()
    orchestrator.llm = capture
    try:
        choice = orchestrator._compose_choice(state, ranked, packet, "Assess options for a water-constrained wheat farm")
    finally:
        orchestrator.llm = original
    assert choice is not None and capture.calls, "composer did not invoke its provider boundary"
    payload = capture.calls[0]["payload"]
    evidence = payload["reviewed_evidence"]
    expected = {item["id"]: item for item in orchestrator._composer_evidence(packet)}
    assert evidence == list(expected.values()), "provider payload changed after evidence construction"
    assert evidence, "no retrieved evidence supplied to provider"
    assert {item["id"] for item in evidence} <= packet["card_ids"], "provider received evidence outside retrieved packet"
    assert all(item.get("passage") and item.get("locator") and item.get("source_id") for item in evidence), "provider evidence lacks exact passage provenance"
    result = {
        "status": "passed",
        "provider_schema": capture.calls[0]["schema"],
        "retrieved_packet_card_ids": sorted(packet["card_ids"]),
        "provider_evidence": [
            {"id": item["id"], "source_id": item["source_id"], "locator": item["locator"], "passage_characters": len(item["passage"])}
            for item in evidence
        ],
        "assertions": [
            "composer invoked the provider boundary",
            "provider evidence exactly equals composer evidence from the retrieved packet",
            "every provider evidence item has nonempty source_id, locator, and exact passage",
            "no provider evidence ID falls outside packet.card_ids",
        ],
    }
    output = Path(__file__).with_suffix(".json")
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
