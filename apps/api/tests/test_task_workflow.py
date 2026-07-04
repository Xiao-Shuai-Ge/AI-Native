"""Workflow orchestration deserialization tests."""

from workflows.models import LangGraphStepResult


def test_langgraph_step_result_model_validate_accepts_activity_dict() -> None:
    payload = {"report": "# Demo Report", "errors": []}
    parsed = LangGraphStepResult.model_validate(payload)
    assert parsed.report == "# Demo Report"
    assert parsed.errors == []
