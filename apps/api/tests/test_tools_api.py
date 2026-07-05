"""Tests for `GET /api/tools`."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from mcp_client.errors import MCPToolError, MCPToolErrorCode
from mcp_client.schema import MCPToolInfo


class _FakeMCPClient:
    def __init__(self, tools: list[MCPToolInfo] | None = None, error: MCPToolError | None = None):
        self._tools = tools or []
        self._error = error

    async def discover_tools(self) -> list[MCPToolInfo]:
        if self._error is not None:
            raise self._error
        return self._tools


@pytest.mark.asyncio
async def test_list_tools_returns_discovered_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _FakeMCPClient(
        tools=[
            MCPToolInfo(name="calculator", description="math", input_schema={"type": "object"}),
            MCPToolInfo(name="web_search", description="search", input_schema={}),
        ]
    )
    monkeypatch.setattr("api.routes.tools.create_mcp_client", lambda _settings: fake_client)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/tools")

    assert response.status_code == 200
    body = response.json()
    names = {tool["name"] for tool in body["tools"]}
    assert names == {"calculator", "web_search"}


@pytest.mark.asyncio
async def test_list_tools_returns_503_when_mcp_server_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeMCPClient(
        error=MCPToolError(MCPToolErrorCode.INTERNAL_ERROR, "connection refused")
    )
    monkeypatch.setattr("api.routes.tools.create_mcp_client", lambda _settings: fake_client)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/tools")

    assert response.status_code == 503
