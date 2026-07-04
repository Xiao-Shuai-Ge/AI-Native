"""Planner agent unit tests."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from agents.planner import PlannerAgent
from agents.schemas import PlanOutput
from llm.errors import LLMUnavailableError
from llm.fake import FakeLLMClient


@pytest.mark.asyncio
async def test_planner_returns_structured_role_selection() -> None:
    fake = FakeLLMClient(
        structured_handler=lambda _messages, schema: schema.model_validate(
            {
                "assigned_roles": ["researcher", "analyst", "writer"],
                "subtasks": {
                    "researcher": "gather background",
                    "analyst": "summarize findings",
                    "writer": "write report",
                },
            }
        )
    )
    planner = PlannerAgent()
    result = await planner.plan("什么是 Dapr Workflow", task_id=uuid4(), llm=fake)

    assert isinstance(result, PlanOutput)
    assert result.assigned_roles == ["researcher", "analyst", "writer"]
    assert fake.structured_calls


@pytest.mark.asyncio
async def test_planner_rejects_unknown_roles() -> None:
    fake = FakeLLMClient(
        structured_handler=lambda _messages, schema: schema.model_validate(
            {"assigned_roles": ["writer", "mystery_role"], "subtasks": {}}
        )
    )
    planner = PlannerAgent()

    with pytest.raises(ValidationError):
        await planner.plan("topic", task_id=uuid4(), llm=fake)


@pytest.mark.asyncio
async def test_planner_propagates_unavailable_error() -> None:
    fake = FakeLLMClient(error=LLMUnavailableError("provider down"))
    planner = PlannerAgent()

    with pytest.raises(LLMUnavailableError):
        await planner.plan("topic", task_id=uuid4(), llm=fake)
