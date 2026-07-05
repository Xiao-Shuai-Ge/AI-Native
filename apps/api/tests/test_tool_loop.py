"""Tests for the shared ReAct tool-calling loop (`agents/tool_loop.py`)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest

from agents.roles import RESEARCHER_ROLE, WRITER_ROLE
from agents.tool_loop import resolve_role_tools, run_tool_loop
from llm.fake import FakeLLMClient
from llm.protocol import ChatMessage, ChatResponse, ChatRole, ToolCall, ToolDefinition
from mcp_client.errors import MCPToolError, MCPToolErrorCode
from mcp_client.schema import MCPToolInfo


class FakeMCPClient:
    def __init__(
        self,
        *,
        tools: list[MCPToolInfo] | None = None,
        call_results: dict[str, dict[str, Any] | MCPToolError] | None = None,
    ) -> None:
        self._tools = tools or []
        self._call_results = call_results or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    @asynccontextmanager
    async def session(self):  # type: ignore[no-untyped-def]
        yield self

    async def discover_tools(self, *, session: object | None = None) -> list[MCPToolInfo]:
        return self._tools

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        timeout: float | None = None,
        session: object | None = None,
    ) -> dict[str, Any]:
        self.calls.append((name, arguments))
        outcome = self._call_results.get(name)
        if isinstance(outcome, MCPToolError):
            raise outcome
        return outcome or {}


@pytest.mark.asyncio
async def test_run_tool_loop_without_tools_makes_single_call() -> None:
    llm = FakeLLMClient(chat_responses=[ChatResponse(content="plain answer")])
    mcp_client = FakeMCPClient()
    result = await run_tool_loop(
        llm=llm,
        messages=[ChatMessage(role=ChatRole.USER, content="hi")],
        tools=[],
        mcp_client=mcp_client,
    )
    assert result.final_content == "plain answer"
    assert result.tool_calls == []


@pytest.mark.asyncio
async def test_run_tool_loop_executes_tool_and_feeds_result_back() -> None:
    tool_call = ToolCall(id="call-1", name="calculator", arguments={"expression": "2+2"})
    llm = FakeLLMClient(
        chat_responses=[
            ChatResponse(content="", tool_calls=[tool_call]),
            ChatResponse(content="The answer is 4."),
        ]
    )
    mcp_client = FakeMCPClient(call_results={"calculator": {"result": 4}})
    tools = [ToolDefinition(name="calculator", description="math", parameters={})]

    result = await run_tool_loop(
        llm=llm,
        messages=[ChatMessage(role=ChatRole.USER, content="what is 2+2")],
        tools=tools,
        mcp_client=mcp_client,
    )

    assert result.final_content == "The answer is 4."
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "calculator"
    assert result.tool_calls[0].error is None
    assert mcp_client.calls == [("calculator", {"expression": "2+2"})]

    tool_messages = [m for m in result.messages if m.role == ChatRole.TOOL]
    assert len(tool_messages) == 1
    assert tool_messages[0].tool_call_id == "call-1"
    assert "4" in tool_messages[0].content


@pytest.mark.asyncio
async def test_run_tool_loop_records_tool_error_and_continues() -> None:
    tool_call = ToolCall(id="call-1", name="readonly_sql", arguments={"query": "DROP TABLE x"})
    llm = FakeLLMClient(
        chat_responses=[
            ChatResponse(content="", tool_calls=[tool_call]),
            ChatResponse(content="I could not run that query."),
        ]
    )
    mcp_client = FakeMCPClient(
        call_results={
            "readonly_sql": MCPToolError(MCPToolErrorCode.INVALID_INPUT, "only SELECT allowed")
        }
    )
    tools = [ToolDefinition(name="readonly_sql", description="sql", parameters={})]

    result = await run_tool_loop(
        llm=llm,
        messages=[ChatMessage(role=ChatRole.USER, content="drop the table")],
        tools=tools,
        mcp_client=mcp_client,
    )

    assert result.final_content == "I could not run that query."
    assert result.tool_calls[0].error is not None
    assert "invalid_input" in result.tool_calls[0].error


@pytest.mark.asyncio
async def test_run_tool_loop_stops_at_max_rounds() -> None:
    tool_call = ToolCall(id="call-1", name="calculator", arguments={"expression": "1+1"})
    responses = [ChatResponse(content="", tool_calls=[tool_call]) for _ in range(2)]
    responses.append(ChatResponse(content="giving up, final answer"))
    llm = FakeLLMClient(chat_responses=responses)
    mcp_client = FakeMCPClient(call_results={"calculator": {"result": 2}})
    tools = [ToolDefinition(name="calculator", description="math", parameters={})]

    result = await run_tool_loop(
        llm=llm,
        messages=[ChatMessage(role=ChatRole.USER, content="loop forever")],
        tools=tools,
        mcp_client=mcp_client,
        max_rounds=2,
    )

    assert result.final_content == "giving up, final answer"
    assert len(result.tool_calls) == 2


@pytest.mark.asyncio
async def test_run_tool_loop_rejects_tool_outside_allowlist() -> None:
    tool_call = ToolCall(
        id="call-1",
        name="code_runner",
        arguments={"language": "python", "code": "1"},
    )
    llm = FakeLLMClient(
        chat_responses=[
            ChatResponse(content="", tool_calls=[tool_call]),
            ChatResponse(content="Cannot run that tool."),
        ]
    )
    mcp_client = FakeMCPClient(
        call_results={"code_runner": {"stdout": "ok", "stderr": "", "exit_code": 0}}
    )
    tools = [ToolDefinition(name="calculator", description="math", parameters={})]

    result = await run_tool_loop(
        llm=llm,
        messages=[ChatMessage(role=ChatRole.USER, content="run code")],
        tools=tools,
        mcp_client=mcp_client,
    )

    assert result.final_content == "Cannot run that tool."
    assert result.tool_calls[0].error is not None
    assert "unauthorized" in result.tool_calls[0].error
    assert mcp_client.calls == []


@pytest.mark.asyncio
async def test_resolve_role_tools_filters_by_allowlist() -> None:
    mcp_client = FakeMCPClient(
        tools=[
            MCPToolInfo(name="web_search", description="search", input_schema={}),
            MCPToolInfo(name="calculator", description="math", input_schema={}),
            MCPToolInfo(name="readonly_sql", description="sql", input_schema={}),
        ]
    )
    tools = await resolve_role_tools(RESEARCHER_ROLE, mcp_client=mcp_client)
    assert {tool.name for tool in tools} == {"web_search", "calculator"}


@pytest.mark.asyncio
async def test_resolve_role_tools_returns_empty_for_writer() -> None:
    mcp_client = FakeMCPClient(
        tools=[MCPToolInfo(name="web_search", description="search", input_schema={})]
    )
    tools = await resolve_role_tools(WRITER_ROLE, mcp_client=mcp_client)
    assert tools == []
