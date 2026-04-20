from hypothesis import given, strategies as st

from app.tools.decision import apply_decision_rules_tool


@given(score=st.floats(min_value=0, max_value=100))
def test_decision_returns_valid_status_and_confidence(score: float) -> None:
    result = apply_decision_rules_tool(score)
    assert result["status"] in {"PASS", "FAIL", "REVIEW"}
    assert 0.0 <= float(result["confidence"]) <= 1.0


@given(score=st.floats(min_value=75, max_value=100))
def test_high_score_pass(score: float) -> None:
    assert apply_decision_rules_tool(score)["status"] == "PASS"


@given(score=st.floats(min_value=0, max_value=60, exclude_max=True))
def test_low_score_fail(score: float) -> None:
    assert apply_decision_rules_tool(score)["status"] == "FAIL"


def test_review_boundary_at_sixty() -> None:
    assert apply_decision_rules_tool(60.0)["status"] == "REVIEW"


def test_pass_boundary_at_hundred() -> None:
    assert apply_decision_rules_tool(100.0)["status"] == "PASS"
