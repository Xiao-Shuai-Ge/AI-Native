"""Analyst agent unit tests."""

from uuid import uuid4

import pytest

from agents.analyst import AnalystAgent
from agents.schemas import AnalystSummary
from llm.errors import LLMUnavailableError
from llm.fake import FakeLLMClient


@pytest.mark.asyncio
async def test_analyst_returns_structured_analysis() -> None:
    fake = FakeLLMClient(
        structured_handler=lambda _messages, schema: schema.model_validate(
            {"analysis": "Dapr Workflow provides durable, replayable orchestration."}
        )
    )
    analyst = AnalystAgent()
    result = await analyst.analyze(
        "什么是 Dapr Workflow",
        task_id=uuid4(),
        llm=fake,
        research_notes=["Dapr Workflow persists state via checkpoints."],
    )

    assert isinstance(result, AnalystSummary)
    assert result.analysis
    assert fake.structured_calls


@pytest.mark.asyncio
async def test_analyst_propagates_unavailable_error() -> None:
    fake = FakeLLMClient(error=LLMUnavailableError("provider down"))
    analyst = AnalystAgent()

    with pytest.raises(LLMUnavailableError):
        await analyst.analyze("topic", task_id=uuid4(), llm=fake)
