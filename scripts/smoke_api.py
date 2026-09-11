"""Local HTTP smoke: health plus fresh-session text/JSON equivalence."""
from __future__ import annotations

import httpx

BASE = "http://127.0.0.1:8765"
PATCH = {"soil": {"organic_carbon_pct": 0.3}, "climate": {"rainfall_pattern": "low"}, "land": {"use_type": "crop", "crop_system": "monoculture wheat"}, "location": {"region": "semi-arid region"}}

def create(client): return client.post(f"{BASE}/v1/sessions").json()["session_id"]
def fields(response): return {field: event["value"] for field, event in response["current_profile"]["current"].items() if event}
def main():
    with httpx.Client(timeout=30, trust_env=False) as client:
        health = client.get(f"{BASE}/health"); text_session, json_session = create(client), create(client)
        text = client.post(f"{BASE}/v1/chat", json={"session_id": text_session, "message": "SOC is 0.3%, low rainfall, monoculture wheat in a semi-arid region", "mode": "advice"}).json()
        structured = client.post(f"{BASE}/v1/chat", json={"session_id": json_session, "message": "", "site_patch": PATCH, "mode": "advice"}).json()
        omitted = client.post(f"{BASE}/v1/chat", json={"session_id": json_session, "message": "No irrigation is available", "mode": "advice"}).json()
        cleared = client.post(f"{BASE}/v1/chat", json={"session_id": json_session, "message": "", "site_patch": {"soil": {"organic_carbon_pct": None}}, "mode": "advice"}).json()
        isolated_session = create(client)
        isolated = client.post(f"{BASE}/v1/chat", json={"session_id": isolated_session, "message": "Natural grassland has habitat diversity and recent land clearing", "mode": "advice"}).json()
    result = {"health": health.status_code, "healthy": health.json().get("status") == "healthy", "text_status": text["status"], "json_status": structured["status"], "profiles_equivalent": fields(text) == fields(structured), "text_actions": [r["action_id"] for r in text["recommendations"]], "json_actions": [r["action_id"] for r in structured["recommendations"]], "omitted_preserves_soc": fields(omitted).get("soil.organic_carbon_pct") == 0.3, "explicit_null_clears_soc": cleared["current_profile"]["current"].get("soil.organic_carbon_pct") is None, "session_isolated": isolated["current_profile"]["current"].get("land.crop_system") is None, "numeric_illustrations": len(structured["literature_illustrations"])}
    assert result["health"] == 200 and result["healthy"]
    assert result["text_status"] == result["json_status"] == "recommend"
    assert result["profiles_equivalent"]
    assert result["omitted_preserves_soc"] and result["explicit_null_clears_soc"] and result["session_isolated"]
    print(result)

if __name__ == "__main__": main()
