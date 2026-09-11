from app.services.verification import literature_illustration


def test_lnrr_literature_illustration_is_server_computed():
    card = {"evidence_id": "S4-card", "effect": {"measure": "ln_response_ratio", "estimate": 0.34, "ci_lower": 0.15, "ci_upper": 0.53}}
    result = literature_illustration(card)
    assert result["output_relative_percent"] == 40.5
    assert result["output_ci_percent"] == [16.2, 69.9]


def test_relative_percentage_point_arithmetic():
    assert 0.3 * 1.20 == 0.36
    assert 0.36 - 0.3 == 0.06
