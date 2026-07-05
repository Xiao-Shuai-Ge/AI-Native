"""Researcher agent unit tests."""

from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import pytest

from agents.researcher import ResearcherAgent
from agents.schemas import ResearcherNotes
from llm.errors import LLMUnavailableError
from llm.fake import FakeLLMClient
from llm.protocol import ChatResponse, ToolCall, ToolDefinition


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
    result, tool_calls = await researcher.research(
        "什么是 Dapr Workflow", task_id=uuid4(), llm=fake
    )

    assert isinstance(result, ResearcherNotes)
    assert result.notes
    assert result.sources
    assert fake.structured_calls
    assert tool_calls == []


@pytest.mark.asyncio
async def test_researcher_propagates_unavailable_error() -> None:
    fake = FakeLLMClient(error=LLMUnavailableError("provider down"))
    researcher = ResearcherAgent()

    with pytest.raises(LLMUnavailableError):
        await researcher.research("topic", task_id=uuid4(), llm=fake)


class _FakeMCPClient:
    @asynccontextmanager
    async def session(self):  # type: ignore[no-untyped-def]
        yield self

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        timeout: float | None = None,
        session: object | None = None,
    ) -> dict[str, Any]:
        return {"result": 4}


@pytest.mark.asyncio
async def test_researcher_runs_tool_loop_before_final_structured_output() -> None:
    tool_call = ToolCall(id="call-1", name="calculator", arguments={"expression": "2+2"})
    fake = FakeLLMClient(
        chat_responses=[
            ChatResponse(content="", tool_calls=[tool_call]),
            ChatResponse(content="2+2 is 4."),
        ],
        structured_handler=lambda _messages, schema: schema.model_validate(
            {"notes": ["2+2 is 4."], "sources": []}
        ),
    )
    researcher = ResearcherAgent()
    tools = [ToolDefinition(name="calculator", description="math", parameters={})]

    result, tool_calls = await researcher.research(
        "what is 2+2",
        task_id=uuid4(),
        llm=fake,
        mcp_client=_FakeMCPClient(),
        tools=tools,
    )

    assert result.notes == ["2+2 is 4."]
    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "calculator"
    assert fake.structured_calls
