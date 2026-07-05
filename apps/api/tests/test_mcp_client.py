"""Tests for `mcp_client`: discovery, calling, and error mapping.

Uses `mcp.shared.memory.create_connected_server_and_client_session` to run
the real `mcp_server` FastMCP app in-process over an in-memory transport, so
these tests exercise the actual MCP protocol (tool schemas, structured
content, `isError`) without any network, Docker, or Postgres dependency.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult, TextContent

from mcp_client.client import MCPClient, _parse_call_tool_result
from mcp_client.errors import MCPToolError, MCPToolErrorCode
from mcp_client.schema import MCPToolInfo, filter_by_allowlist, to_tool_definition


def _in_memory_client(server: FastMCP, *, timeout: float = 5.0) -> MCPClient:
    @asynccontextmanager
    async def session_factory():  # type: ignore[no-untyped-def]
        async with create_connected_server_and_client_session(
            server, read_timeout_seconds=timedelta(seconds=timeout)
        ) as session:
            yield session

    return MCPClient(session_factory=session_factory, timeout=timeout)


def _build_test_server() -> FastMCP:
    server = FastMCP(name="test-server")

    @server.tool(name="echo", description="Echoes back the given text.")
    def echo(text: str) -> dict[str, Any]:
        return {"text": text}

    @server.tool(name="failing_tool", description="Always returns a tool error payload.")
    def failing_tool() -> dict[str, Any]:
        return {"error_code": "invalid_input", "error_message": "bad input from test"}

    @server.tool(name="unknown_code_tool", description="Returns an unrecognized error code.")
    def unknown_code_tool() -> dict[str, Any]:
        return {"error_code": "not_a_real_code", "error_message": "mystery failure"}

    return server


@pytest.mark.asyncio
async def test_discover_tools_returns_schema() -> None:
    client = _in_memory_client(_build_test_server())
    tools = await client.discover_tools()

    names = {tool.name for tool in tools}
    assert {"echo", "failing_tool", "unknown_code_tool"} <= names
    echo_tool = next(tool for tool in tools if tool.name == "echo")
    assert echo_tool.description == "Echoes back the given text."
    assert "text" in echo_tool.input_schema.get("properties", {})


@pytest.mark.asyncio
async def test_call_tool_returns_structured_payload() -> None:
    client = _in_memory_client(_build_test_server())
    result = await client.call_tool("echo", {"text": "hello"})
    assert result == {"text": "hello"}


@pytest.mark.asyncio
async def test_call_tool_raises_mapped_error_from_payload() -> None:
    client = _in_memory_client(_build_test_server())
    with pytest.raises(MCPToolError) as excinfo:
        await client.call_tool("failing_tool", {})
    assert excinfo.value.code == MCPToolErrorCode.INVALID_INPUT
    assert "bad input" in excinfo.value.message


@pytest.mark.asyncio
async def test_call_tool_falls_back_to_internal_error_for_unknown_code() -> None:
    client = _in_memory_client(_build_test_server())
    with pytest.raises(MCPToolError) as excinfo:
        await client.call_tool("unknown_code_tool", {})
    assert excinfo.value.code == MCPToolErrorCode.INTERNAL_ERROR


@pytest.mark.asyncio
async def test_call_tool_raises_internal_error_for_unknown_tool() -> None:
    client = _in_memory_client(_build_test_server())
    with pytest.raises(MCPToolError) as excinfo:
        await client.call_tool("does_not_exist", {})
    assert excinfo.value.code == MCPToolErrorCode.INTERNAL_ERROR


def test_parse_call_tool_result_raises_on_is_error() -> None:
    result = CallToolResult(content=[TextContent(type="text", text="boom")], isError=True)
    with pytest.raises(MCPToolError) as excinfo:
        _parse_call_tool_result("some_tool", result)
    assert excinfo.value.code == MCPToolErrorCode.INTERNAL_ERROR


def test_parse_call_tool_result_raises_oversized_response() -> None:
    huge_payload = {"data": "x" * 200_000}
    result = CallToolResult(structuredContent=huge_payload, content=[])
    with pytest.raises(MCPToolError) as excinfo:
        _parse_call_tool_result("some_tool", result)
    assert excinfo.value.code == MCPToolErrorCode.OVERSIZED_RESPONSE


def test_to_tool_definition_defaults_empty_schema() -> None:
    info = MCPToolInfo(name="t", description="d", input_schema={})
    definition = to_tool_definition(info)
    assert definition.parameters == {"type": "object", "properties": {}}


def test_filter_by_allowlist_keeps_only_listed_tools() -> None:
    tools = [
        MCPToolInfo(name="web_search", description="", input_schema={}),
        MCPToolInfo(name="readonly_sql", description="", input_schema={}),
    ]
    filtered = filter_by_allowlist(tools, ["web_search"])
    assert [tool.name for tool in filtered] == ["web_search"]
