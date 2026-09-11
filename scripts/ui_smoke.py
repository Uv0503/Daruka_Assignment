"""Headless Streamlit UI-to-backend smoke using Streamlit's own test API."""
from __future__ import annotations

import os
from pathlib import Path


def main() -> int:
    from streamlit.testing.v1 import AppTest
    root = Path(__file__).resolve().parents[1]
    at = AppTest.from_file(str(root / "ui" / "app.py"))
    at.run(timeout=20)
    if at.exception: raise RuntimeError(f"initial UI exception: {at.exception}")
    if not at.title or at.title[0].value != "Biodiversity Intelligence": raise RuntimeError("UI title did not render")
    if not at.chat_input: raise RuntimeError("chat input did not render")
    # Blank is intentional: ordinary text must not silently submit the example
    # profile displayed in the sidebar.
    if at.text_area[0].value:
        raise RuntimeError("structured input unexpectedly has a default profile")
    at.chat_input[0].set_value("SOC is 0.3%, low rainfall, monoculture wheat in a semi-arid region")
    at.run(timeout=45)
    if at.exception: raise RuntimeError(f"chat UI exception: {at.exception}")
    rendered = " ".join(element.value for element in at.markdown if isinstance(element.value, str))
    if "Biodiversity Intelligence response" in rendered: raise RuntimeError("unexpected raw export displayed")
    if not at.subheader: raise RuntimeError("recommendation card did not render")
    print({"status": "passed", "title": at.title[0].value, "recommendation_cards": len(at.subheader), "api_base_url": os.getenv("API_BASE_URL")})
    return 0

if __name__ == "__main__": raise SystemExit(main())
