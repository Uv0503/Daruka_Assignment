from __future__ import annotations

import json
import os

import httpx
import streamlit as st

from ui.components import render_response

st.set_page_config(page_title="Biodiversity Intelligence", layout="wide")
API = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

def create_session() -> str:
    response = httpx.post(f"{API}/v1/sessions", timeout=10); response.raise_for_status()
    return response.json()["session_id"]

if not st.session_state.get("session_id"):
    try: st.session_state.session_id = create_session()
    except Exception:  # noqa: BLE001 - UI renders an actionable local API error
        st.session_state.session_id = None
if "turns" not in st.session_state: st.session_state.turns = []

st.title("Biodiversity Intelligence")
with st.sidebar:
    st.caption("Local single-user evidence console. Session IDs route state; they are not authentication.")
    if st.button("New conversation"):
        try:
            new_session_id = create_session()
        except Exception:  # noqa: BLE001 - preserve existing conversation on connection failure
            st.error("Could not start a conversation. Check the backend connection and try again.")
        else:
            st.session_state.session_id = new_session_id
            st.session_state.turns = []
            st.rerun()
    resume = st.text_input("Resume copied session ID", value=st.session_state.session_id or "")
    if resume: st.session_state.session_id = resume
    st.markdown("### Structured input")
    example = {"soil": {"organic_carbon_pct": 0.3}, "climate": {"rainfall_pattern": "low"}, "land": {"use_type": "crop", "crop_system": "monoculture wheat"}, "location": {"region": "semi-arid region"}}
    st.code(json.dumps(example, indent=2), language="json")
    json_text = st.text_area("site_patch JSON (optional; submitted only with the button below)", value="", height=210, placeholder="Paste a SitePatch JSON object")
    submit_json = st.button("Submit structured profile", disabled=not st.session_state.session_id)
    try:
        health = httpx.get(f"{API}/health", timeout=5).json()
        if health.get("provider_configured"):
            st.success("🟢 AI Scientist Reasoning: Active", icon="🌿")
        else:
            st.warning("⚠️ LLM Offline: Add GROQ_API_KEY in Streamlit Cloud Secrets", icon="⚠️")
        st.caption(f"Corpus: {'ready' if health.get('corpus_ready') else 'unavailable'} | Model: {health.get('model', 'none')}")
    except Exception:  # noqa: BLE001
        st.caption("Backend: Starting up...")

for turn in st.session_state.turns:
    with st.chat_message("user"): st.write(turn["message"])
    with st.chat_message("assistant"): render_response(turn["response"])

message = st.chat_input("Example: SOC is 0.3%, low rainfall, monoculture wheat in a semi-arid region.", disabled=not st.session_state.session_id)
if message is not None or submit_json:
    try: patch = json.loads(json_text) if submit_json and json_text.strip() else None
    except json.JSONDecodeError as exc: st.error(f"Invalid site_patch JSON: {exc}"); st.stop()
    if submit_json and patch is None:
        st.error("Paste a JSON object before submitting it."); st.stop()
    if submit_json and not isinstance(patch, dict):
        st.error("The structured profile must be a JSON object, with fields such as soil, climate or land."); st.stop()
    user_message = message or "Structured profile submitted"
    payload = {"session_id": st.session_state.session_id, "message": message or "", "site_patch": patch, "mode": "hypothetical" if "what if" in (message or "").lower() else "advice"}
    with st.spinner("Validating observations, retrieving reviewed evidence, and checking recommendations…"):
        try:
            result = httpx.post(f"{API}/v1/chat", json=payload, timeout=httpx.Timeout(90, connect=10)); result.raise_for_status(); response = result.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                st.error("This conversation could not be found. Choose New conversation or enter a valid session ID.")
            elif exc.response.status_code == 422:
                st.error("Some supplied fields or units are invalid. Check the structured profile and use explicit units for measurements.")
            else:
                st.error("The backend could not complete this request. Your existing conversation has been preserved.")
            st.stop()
        except httpx.TimeoutException:
            st.error("The response is taking longer than expected. It may still be processing; it has not been submitted a second time.")
            st.stop()
        except Exception:  # noqa: BLE001 - render request failure without retrying the chat POST
            st.error("Could not receive a response. Check the backend connection and try again."); st.stop()
    st.session_state.turns.append({"message": user_message, "response": response})
    st.rerun()
