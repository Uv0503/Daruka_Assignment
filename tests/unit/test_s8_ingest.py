from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ingest import parse_s8_dom_literal_v1

FIXTURE = Path(__file__).parents[1] / "fixtures" / "s8_dom_literal_v1.html"


def test_s8_literal_parser_preserves_required_bodies_and_boundaries() -> None:
    sections = parse_s8_dom_literal_v1(FIXTURE.read_text())

    assert set(sections) == {
        "Water Budgeting and Climate-Resilient Cropping Systems",
        "Farmer Managed Natural Regeneration",
        "Crop Diversification and Intensification",
    }
    assert "available water" in sections["Water Budgeting and Climate-Resilient Cropping Systems"]
    assert "Sahel" in sections["Farmer Managed Natural Regeneration"]
    assert "legumes" in sections["Crop Diversification and Intensification"]
    assert "Perspiciatis" not in " ".join(sections.values())
    assert "unrelated" not in sections["Water Budgeting and Climate-Resilient Cropping Systems"]
    assert "intervening" not in sections["Farmer Managed Natural Regeneration"]
    assert "final unrelated" not in sections["Crop Diversification and Intensification"]


def test_s8_literal_parser_fails_when_required_title_is_missing() -> None:
    html = FIXTURE.read_text().replace("Farmer Managed Natural Regeneration", "FMNR", 1)

    with pytest.raises(ValueError, match="S8 required literal title missing: Farmer Managed Natural Regeneration"):
        parse_s8_dom_literal_v1(html)
