"""Researcher agent unit tests."""

from uuid import uuid4

import pytest

from agents.researcher import ResearcherAgent
from agents.schemas import ResearcherNotes
from llm.errors import LLMUnavailableError
from llm.fake import FakeLLMClient


@pytest.mark.asyncio
async def test_researcher_returns_structured_notes() -> None:
    fake = FakeLLMClient(
        structured_handler=lambda _messages, schema: schema.model_validate(
            {
                "notes": ["Dapr Workflow persists state via checkpoints."],
                "sources": [{"title": "Dapr docs", "url": "https://docs.dapr.io"}],
            }
        )
    )
    researcher = ResearcherAgent()
    result = await researcher.research("什么是 Dapr Workflow", task_id=uuid4(), llm=fake)

    assert isinstance(result, ResearcherNotes)
    assert result.notes
    assert result.sources
    assert fake.structured_calls


@pytest.mark.asyncio
async def test_researcher_propagates_unavailable_error() -> None:
    fake = FakeLLMClient(error=LLMUnavailableError("provider down"))
    researcher = ResearcherAgent()

    with pytest.raises(LLMUnavailableError):
        await researcher.research("topic", task_id=uuid4(), llm=fake)
