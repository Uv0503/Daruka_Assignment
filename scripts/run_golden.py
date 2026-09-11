"""Execute the ten specified golden scenarios against the API application.

The suite deliberately uses server templates (no external LLM sampling), while
leaving hybrid retrieval enabled. The resulting JSON is an auditable test
artifact, not a claim of a live-provider evaluation.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app
from app.services.verification import verify_response

ROOT = Path(__file__).resolve().parents[1]


async def session(client: httpx.AsyncClient) -> str:
    response = await client.post("/v1/sessions")
    response.raise_for_status()
    return response.json()["session_id"]


async def chat(client: httpx.AsyncClient, session_id: str, turn: dict) -> dict:
    payload = {"session_id": session_id, "message": turn.get("message", ""), "mode": turn.get("mode", "advice")}
    if "site_patch" in turn:
        payload["site_patch"] = turn["site_patch"]
    response = await client.post("/v1/chat", json=payload)
    response.raise_for_status()
    return response.json()


async def execute(case: dict, client: httpx.AsyncClient) -> dict:
    kind = case["kind"]
    if kind == "invented_number":
        state = {"current": {"land.use_type": {"observation_id": "land", "value": "crop"}, "soil.ph": {"observation_id": "soil", "value": 6.5}, "climate.rainfall_pattern": {"observation_id": "rain", "value": "low"}}}
        fabricated = {"summary": "Species richness rises 99%", "recommendations": [{"action_id": "unknown", "evidence_ids": ["invented"], "used_observation_ids": ["land"], "interaction_paths": [], "action_steps": [], "rationale": "Will double richness", "tradeoffs": [], "impacted_metrics": [{"estimate_type": "local_model_prediction", "quantitative_estimate": 1}]}]}
        errors = verify_response(fabricated, {}, state, actions=app.state.orchestrator.reasoner.actions, edges=app.state.orchestrator.reasoner.edges, supplied_evidence_ids=set())
        assert errors
        return {"status": "rejected_by_validator", "validator_errors": errors}
    if kind == "isolation":
        crop, natural = await session(client), await session(client)
        await chat(client, crop, {"message": "SOC is 0.3%, low rainfall, monoculture wheat"})
        response = await chat(client, natural, {"message": "Natural grassland has habitat diversity and recent land clearing"})
        assert response["current_profile"]["current"].get("land.crop_system") is None
        return response
    original = app.state.orchestrator.retriever.retrieve
    if kind == "empty_corpus":
        app.state.orchestrator.retriever.retrieve = lambda *_args, **_kwargs: {"queries": [], "cards": [], "card_ids": set(), "trace_excerpts": [], "timings": {}, "dense_available": False}
    try:
        sid = await session(client)
        turns = case.get("turns") or [{key: value for key, value in case.items() if key in {"message", "site_patch", "mode"}}]
        response = None
        for turn in turns:
            response = await chat(client, sid, turn)
        assert response is not None
        return response
    finally:
        app.state.orchestrator.retriever.retrieve = original


async def main_async() -> list[dict]:
    cases = [json.loads(line) for line in (ROOT / "tests/golden/cases.jsonl").read_text().splitlines() if line.strip()]
    app.state.orchestrator.llm = None
    app.state.orchestrator.retriever.use_dense = True
    output = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://golden") as client:
        for case in cases:
            response = await execute(case, client)
            actual = response["status"]
            assert actual == case["expected_status"], f"{case['id']}: expected {case['expected_status']}, got {actual}"
            cited = {item for rec in response.get("recommendations", []) for item in rec.get("evidence_ids", [])}
            required = set(case.get("required_evidence_ids", []))
            assert required <= cited, f"{case['id']}: missing required evidence {sorted(required - cited)}"
            output.append({"id": case["id"], "status": actual, "required_evidence_ids": sorted(required), "cited_evidence_ids": sorted(cited), "validator_errors": response.get("validator_errors", [])})
    return output


def main() -> int:
    results = asyncio.run(main_async())
    report = {"mode": "deterministic API suite: server templates, hybrid retrieval enabled, no Groq composition", "cases": results, "passed": len(results), "total": len(results)}
    path = ROOT / "artifacts/golden_results.json"
    path.write_text(json.dumps(report, indent=2))
    print(json.dumps({"passed": report["passed"], "total": report["total"], "artifact": str(path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
