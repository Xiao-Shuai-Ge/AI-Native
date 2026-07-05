"""Tests for MCP server shared resource lifecycle."""

from __future__ import annotations

import pytest

from mcp_server.config import Settings
from mcp_server.server import ServerState


@pytest.mark.asyncio
async def test_get_http_client_recreates_closed_client() -> None:
    state = ServerState(Settings())
    first = state.get_http_client()
    await first.aclose()

    second = state.get_http_client()

    assert second is not first
    assert not second.is_closed
    await state.aclose()
