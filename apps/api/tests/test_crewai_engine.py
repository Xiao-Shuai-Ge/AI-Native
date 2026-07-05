"""CrewAI engine/role-runner tests driven with a fake, deterministic LLM.

These tests build *real* CrewAI `Agent`/`Task`/`Crew` objects (see
`orchestration/crewai_engine/`); only the LLM backend is faked so the tests
stay offline and deterministic (AGENTS.md section 7: "测试默认使用 fake/mock
LLM；真实模型测试必须显式启用").
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest

import orchestration.crewai_engine as crewai_engine_package
from agents.schemas import AnalystSummary, ResearcherNotes, WriterSummary
from llm.fake import FakeLLMClient
from llm.protocol import ChatMessage, ChatResponse, ToolCall
from mcp_client.schema import MCPToolInfo
from orchestration.crewai_engine.engine import CrewAIEngine
from orchestration.crewai_engine.roles_runner import run_analyst, run_researcher, run_writer
from orchestration.models import EngineChoice, TaskRequest, TaskStatus


def test_importing_crewai_engine_redirects_storage_and_disables_telemetry() -> None:
    """Regression test for CrewAI writing its kickoff-replay SQLite cache

    under `$HOME` (e.g. `~/Library/Application Support/<app>`), which crashes
    every role call in environments where that directory isn't writable
    (restricted sandboxes, read-only-HOME containers, CI). See
    `orchestration/crewai_engine/__init__.py`.
    """
    assert crewai_engine_package  # import already happened; env vars are set as a side effect
    assert os.environ.get("CREWAI_STORAGE_DIR") == str(
        Path(tempfile.gettempdir()) / "ainative-crewai-storage"
    )
    assert os.environ.get("CREWAI_DISABLE_TELEMETRY") == "true"


def _joined_content(messages: list[ChatMessage]) -> str:
    return " ".join(message.content for message in messages)


def _fake_llm() -> FakeLLMClient:
    def handler(messages: list[ChatMessage]) -> ChatResponse:
        content = _joined_content(messages)
        payload: dict[str, object]
        if "ResearcherNotes" in content:
            payload = {"notes": ["fact one", "fact two"], "sources": []}
        elif "AnalystSummary" in content:
            payload = {"analysis": "Key findings synthesized from the notes."}
        elif "WriterSummary" in content:
            payload = {
                "title": "Demo Report",
                "summary": "A short summary.",
                "markdown": "# Demo Report\n\nA short summary.",
            }
        else:
            msg = f"unexpected CrewAI task prompt (no known schema hint): {content[:200]}"
            raise AssertionError(msg)
        return ChatResponse(content=json.dumps(payload), model="fake-model")

    return FakeLLMClient(chat_handler=handler)


@pytest.mark.asyncio
async def test_run_researcher_builds_real_agent_task_and_parses_notes() -> None:
    result, tool_calls = await run_researcher(
        "What is Dapr Workflow?",
        task_id=uuid4(),
        llm=_fake_llm(),
    )
    assert isinstance(result, ResearcherNotes)
    assert result.notes == ["fact one", "fact two"]
    assert tool_calls == []


@pytest.mark.asyncio
async def test_run_analyst_builds_real_agent_task_and_parses_analysis() -> None:
    result, tool_calls = await run_analyst(
        "What is Dapr Workflow?",
        task_id=uuid4(),
        llm=_fake_llm(),
        research_notes=["fact one"],
    )
    assert isinstance(result, AnalystSummary)
    assert result.analysis == "Key findings synthesized from the notes."
    assert tool_calls == []


@pytest.mark.asyncio
async def test_run_writer_builds_real_agent_task_and_parses_report() -> None:
    result = await run_writer(
        "What is Dapr Workflow?",
        task_id=uuid4(),
        llm=_fake_llm(),
        research_notes=["fact one"],
        analysis="Key findings.",
    )
    assert isinstance(result, WriterSummary)
    assert result.markdown.startswith("# Demo Report")


@pytest.mark.asyncio
async def test_crewai_engine_runs_full_researcher_analyst_writer_sequence() -> None:
    engine = CrewAIEngine(llm=_fake_llm())
    request = TaskRequest(task_id=uuid4(), user_query="What is Dapr Workflow?")

    result = await engine.run(request)

    assert result.status == TaskStatus.SUCCEEDED
    assert result.engine_selected == EngineChoice.CREWAI
    assert result.report is not None
    assert "Demo Report" in result.report
    assert result.errors == []


@pytest.mark.asyncio
async def test_crewai_engine_reports_failure_when_a_role_raises() -> None:
    def broken_handler(_messages: list[ChatMessage]) -> ChatResponse:
        return ChatResponse(content="not valid json at all", model="fake-model")

    engine = CrewAIEngine(llm=FakeLLMClient(chat_handler=broken_handler))
    request = TaskRequest(task_id=uuid4(), user_query="anything")

    result = await engine.run(request)

    assert result.status == TaskStatus.FAILED
    assert result.report is None
    assert result.errors


class _FakeMCPClient:
    """Minimal MCPClient double: discovers 2 tools, echoes tool call inputs."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    @asynccontextmanager
    async def session(self):  # type: ignore[no-untyped-def]
        yield self

    async def discover_tools(self, *, session: object | None = None) -> list[MCPToolInfo]:
        return [
            MCPToolInfo(name="web_search", description="search", input_schema={}),
            MCPToolInfo(name="calculator", description="math", input_schema={}),
            MCPToolInfo(name="readonly_sql", description="sql", input_schema={}),
        ]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
        *,
        timeout: float | None = None,
        session: object | None = None,
    ) -> dict[str, object]:
        self.calls.append((name, arguments))
        return {"ok": True, "tool": name}


@pytest.mark.asyncio
async def test_crewai_engine_with_tools_produces_at_least_two_tool_calls() -> None:
    """End-to-end CrewAI run where researcher+analyst each call one real tool.

    Exercises the shared `run_tool_loop` + `chat_structured` path and asserts
    both `CrewAIEngine.tool_calls` and the fake MCP client observed >=2 real
    tool invocations, matching the Day 7 acceptance criterion.
    """
    researcher_call = ToolCall(id="call-1", name="web_search", arguments={"query": "dapr"})
    analyst_call = ToolCall(id="call-2", name="calculator", arguments={"expression": "1+1"})
    tool_round_index = 0

    def chat_handler(messages: list[ChatMessage]) -> ChatResponse:
        content = _joined_content(messages)
        if "WriterSummary" in content:
            return ChatResponse(
                content=json.dumps(
                    {
                        "title": "Demo Report",
                        "summary": "A short summary.",
                        "markdown": "# Demo Report\n\nA short summary.",
                    }
                )
            )
        has_tool_result = any(message.role.value == "tool" for message in messages)
        if not has_tool_result:
            nonlocal tool_round_index
            tool_round_index += 1
            if tool_round_index == 1:
                return ChatResponse(content="", tool_calls=[researcher_call])
            if tool_round_index == 2:
                return ChatResponse(content="", tool_calls=[analyst_call])
        return ChatResponse(content="tool round complete")

    def structured_handler(
        messages: list[ChatMessage], schema: type[object]
    ) -> ResearcherNotes | AnalystSummary:
        if schema is ResearcherNotes:
            return ResearcherNotes(notes=["fact from web_search"], sources=[])
        if schema is AnalystSummary:
            return AnalystSummary(analysis="computed via calculator: 1+1=2")
        msg = f"unexpected structured schema: {schema}"
        raise AssertionError(msg)

    mcp_client = _FakeMCPClient()
    engine = CrewAIEngine(
        llm=FakeLLMClient(chat_handler=chat_handler, structured_handler=structured_handler),
        mcp_client=mcp_client,
    )
    request = TaskRequest(task_id=uuid4(), user_query="What is Dapr Workflow?")

    result = await engine.run(request)

    assert result.status == TaskStatus.SUCCEEDED
    assert result.errors == []
    assert len(mcp_client.calls) == 2
    assert {name for name, _args in mcp_client.calls} == {"web_search", "calculator"}
    assert len(engine.tool_calls) == 2
    assert {call.tool_name for call in engine.tool_calls} == {"web_search", "calculator"}


@pytest.mark.asyncio
async def test_crewai_engine_resume_is_explicitly_unsupported() -> None:
    engine = CrewAIEngine(llm=_fake_llm())
    with pytest.raises(NotImplementedError):
        await engine.resume(str(uuid4()))
