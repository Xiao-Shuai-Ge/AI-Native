"""Writer agent unit tests."""

from uuid import uuid4

import pytest

from agents.schemas import WriterSummary
from agents.writer import WriterAgent
from llm.errors import LLMParseError, LLMUnavailableError
from llm.fake import FakeLLMClient


@pytest.mark.asyncio
async def test_writer_returns_markdown_summary_with_fake_llm() -> None:
    fake = FakeLLMClient(
        structured_handler=lambda _messages, schema: schema.model_validate(
            {
                "title": "Dapr Workflow",
                "summary": "Dapr Workflow provides durable orchestration.",
                "markdown": "# Dapr Workflow\n\nDapr Workflow provides durable orchestration.",
            }
        )
    )
    writer = WriterAgent()
    result = await writer.summarize("什么是 Dapr Workflow", task_id=uuid4(), llm=fake)

    assert isinstance(result, WriterSummary)
    assert result.title == "Dapr Workflow"
    assert "Dapr Workflow" in result.markdown
    assert fake.structured_calls


@pytest.mark.asyncio
async def test_writer_propagates_unavailable_error() -> None:
    fake = FakeLLMClient(error=LLMUnavailableError("provider down"))
    writer = WriterAgent()

    with pytest.raises(LLMUnavailableError):
        await writer.summarize("topic", task_id=uuid4(), llm=fake)


@pytest.mark.asyncio
async def test_writer_propagates_parse_error() -> None:
    fake = FakeLLMClient(error=LLMParseError("invalid json"))
    writer = WriterAgent()

    with pytest.raises(LLMParseError):
        await writer.summarize("topic", task_id=uuid4(), llm=fake)
