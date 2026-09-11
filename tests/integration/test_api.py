import asyncio

import httpx

from app.main import app


async def exercise(callback):
    app.state.orchestrator.llm = None
    app.state.orchestrator.retriever.use_dense = False
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await callback(client)


async def create(client):
    response = await client.post("/v1/sessions")
    assert response.status_code == 200
    return response.json()["session_id"]


def e02_patch():
    return {"soil": {"organic_carbon_pct": 0.3}, "climate": {"rainfall_pattern": "low"}, "land": {"use_type": "crop", "crop_system": "monoculture wheat"}, "location": {"region": "semi-arid region"}}


def test_health_and_e02_recommendation():
    async def scenario(c):
        session = await create(c)
        assert (await c.get("/health")).json()["corpus_ready"] is True
        data = (await c.post("/v1/chat", json={"session_id": session, "message": "", "site_patch": e02_patch(), "mode": "advice"})).json()
        assert data["status"] == "recommend"
        assert {r["action_id"] for r in data["recommendations"]} & {"crop_diversification", "conditional_cover_cropping"}
        assert data["literature_illustrations"][0]["output_relative_percent"] == 40.5
        assert {"S4", "S5"} <= {citation["source_id"] for citation in data["citations"]}
    asyncio.run(exercise(scenario))


def test_text_json_correction_hypothesis_and_invalid_ph():
    async def scenario(c):
        first, second = await create(c), await create(c)
        one = (await c.post("/v1/chat", json={"session_id": first, "message": "SOC is 0.3%, low rainfall, monoculture wheat in a semi-arid region", "mode": "advice"})).json()
        two = (await c.post("/v1/chat", json={"session_id": second, "message": "", "site_patch": e02_patch(), "mode": "advice"})).json()
        assert {f: e["value"] for f, e in one["current_profile"]["current"].items() if e} == {f: e["value"] for f, e in two["current_profile"]["current"].items() if e}
        corrected = (await c.post("/v1/chat", json={"session_id": second, "message": "Annual rainfall is 900 mm concentrated in four months", "mode": "advice"})).json()
        assert corrected["current_profile"]["current"]["climate.annual_rainfall_mm"]["value"] == 900.0
        hypothetical = (await c.post("/v1/chat", json={"session_id": second, "message": "What if I could irrigate?", "mode": "hypothetical"})).json()
        assert hypothetical["current_profile"]["current"].get("land.irrigation_available") is None
        invalid = (await c.post("/v1/chat", json={"session_id": second, "message": "pH is 18", "mode": "advice"})).json()
        assert invalid["status"] == "clarify" and "between 0 and 14" in invalid["summary"]
    asyncio.run(exercise(scenario))


def test_null_omitted_conflict_and_negative_text_semantics():
    async def scenario(c):
        session = await create(c)
        first = (await c.post("/v1/chat", json={"session_id": session, "message": "SOC is 0.3%, low rainfall, monoculture wheat", "mode": "advice"})).json()
        assert first["current_profile"]["current"]["soil.organic_carbon_pct"]["value"] == 0.3
        # Omitted fields preserve state; explicit JSON null clears the field.
        omitted = (await c.post("/v1/chat", json={"session_id": session, "message": "No irrigation is available", "mode": "advice"})).json()
        assert omitted["current_profile"]["current"]["soil.organic_carbon_pct"]["value"] == 0.3
        assert omitted["current_profile"]["current"]["land.irrigation_available"]["value"] is False
        cleared = (await c.post("/v1/chat", json={"session_id": session, "message": "", "site_patch": {"soil": {"organic_carbon_pct": None}}, "mode": "advice"})).json()
        assert cleared["current_profile"]["current"]["soil.organic_carbon_pct"] is None
        monthly = (await c.post("/v1/chat", json={"session_id": session, "message": "Rainfall is 60 mm this month", "mode": "advice"})).json()
        assert monthly["current_profile"]["current"].get("climate.annual_rainfall_mm") is None
        conflict = (await c.post("/v1/chat", json={"session_id": session, "message": "SOC is 0.8%", "site_patch": {"soil": {"organic_carbon_pct": 0.2}}, "mode": "advice"})).json()
        assert conflict["status"] == "clarify"
        resolved = (await c.post("/v1/chat", json={"session_id": session, "message": "I meant 0.8%, not 0.2%", "mode": "advice"})).json()
        assert resolved["current_profile"]["current"]["soil.organic_carbon_pct"]["value"] == 0.8
    asyncio.run(exercise(scenario))


def test_session_isolation_and_natural_habitat_guard():
    async def scenario(c):
        crop, grass = await create(c), await create(c)
        await c.post("/v1/chat", json={"session_id": crop, "message": "SOC is 0.3%, low rainfall, monoculture wheat", "mode": "advice"})
        result = (await c.post("/v1/chat", json={"session_id": grass, "message": "Natural grassland has habitat diversity and recent land clearing", "mode": "advice"})).json()
        assert result["current_profile"]["current"].get("land.crop_system") is None
        assert all(rec["action_id"] not in {"crop_diversification", "conditional_cover_cropping"} for rec in result["recommendations"])
    asyncio.run(exercise(scenario))


def test_provider_failure_is_explicitly_degraded():
    class FailingProvider:
        def structured(self, **_kwargs):
            raise RuntimeError("simulated provider outage")

    async def scenario(c):
        session = await create(c)
        result = (await c.post("/v1/chat", json={"session_id": session, "message": "", "site_patch": e02_patch(), "mode": "advice"})).json()
        assert result["status"] == "recommend"
        assert any("Provider composition failed" in item for item in result["limitations"])

    original = app.state.orchestrator.llm
    app.state.orchestrator.llm = FailingProvider()
    try:
        async def run(c):
            # exercise intentionally sets llm=None, so this direct client
            # retains the injected failure and keeps retrieval deterministic.
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                return await scenario(client)
        asyncio.run(run(None))
    finally:
        app.state.orchestrator.llm = original


def test_follow_up_answers_use_scalar_state_and_advance_questions():
    async def scenario(c):
        session = await create(c)
        first = (await c.post("/v1/chat", json={"session_id": session, "message": "cropland"})).json()
        assert first["questions"][0]["field"] == "climate.rainfall_pattern"
        second = (await c.post("/v1/chat", json={"session_id": session, "message": "erratic"})).json()
        assert second["current_profile"]["current"]["climate.rainfall_pattern"]["value"] == "erratic"
        assert second["questions"][0]["field"] == "land.irrigation_available"
        third = (await c.post("/v1/chat", json={"session_id": session, "message": "I don't know"})).json()
        assert "land.irrigation_available" in third["current_profile"]["current"]
        assert third["questions"][0]["field"] == "land.crop_system"

    asyncio.run(exercise(scenario))


def test_retrieval_run_insufficient_response_keeps_context_and_trace():
    async def scenario(c):
        session = await create(c)
        result = (await c.post("/v1/chat", json={"session_id": session, "message": "Cropland, SOC is 0.3%, biodiversity decline"})).json()
        assert result["status"] == "clarify"
        assert result["recommendations"] == []
        assert result["trace_excerpts"]
        assert result["citations"]
        assert result["limitations"]  # At least one limitation is always set

    asyncio.run(exercise(scenario))
