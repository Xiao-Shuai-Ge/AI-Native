"""MCP client: tool discovery and invocation over the official MCP SDK.

By default connects via Streamable HTTP to whatever `base_url` resolves to
(the Dapr Service Invocation URL in `factory.py`, or `MCP_SERVER_URL`
directly for local dev without Dapr). Tests inject an in-memory
`session_factory` (see `mcp.shared.memory.create_connected_server_and_client_session`)
to exercise the same discovery/call/error-mapping logic without a real
network connection.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import timedelta
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult, TextContent

from mcp_client.errors import MCPToolError, MCPToolErrorCode
from mcp_client.schema import MCPToolInfo

logger = logging.getLogger(__name__)

MAX_RESULT_BYTES = 100_000
DEFAULT_TIMEOUT_SECONDS = 15.0

SessionFactory = Callable[[], AbstractAsyncContextManager[ClientSession]]


def _default_session_factory(
    *, base_url: str, headers: dict[str, str] | None, timeout: float
) -> SessionFactory:
    mcp_url = f"{base_url.rstrip('/')}/mcp"

    @asynccontextmanager
    async def factory() -> AsyncIterator[ClientSession]:
        async with (
            streamablehttp_client(mcp_url, headers=headers, timeout=timeout) as (
                read,
                write,
                _get_session_id,
            ),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            yield session

    return factory


class MCPClient:
    """Discovers and calls MCP tools; maps every failure to `MCPToolError`."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        session_factory: SessionFactory | None = None,
    ) -> None:
        if session_factory is None:
            if base_url is None:
                msg = "base_url is required when session_factory is not provided"
                raise ValueError(msg)
            session_factory = _default_session_factory(
                base_url=base_url, headers=headers, timeout=timeout
            )
        self._session_factory = session_factory
        self._timeout = timeout

    @asynccontextmanager
    async def session(self) -> AsyncIterator[ClientSession]:
        """Yields one initialized MCP session for multiple tool operations."""
        async with self._session_factory() as session:
            yield session

    async def discover_tools(self, *, session: ClientSession | None = None) -> list[MCPToolInfo]:
        if session is not None:
            return await self._discover_tools_with_session(session)
        async with self._session_factory() as owned_session:
            return await self._discover_tools_with_session(owned_session)

    async def _discover_tools_with_session(self, session: ClientSession) -> list[MCPToolInfo]:
        try:
            result = await session.list_tools()
        except TimeoutError as exc:
            raise MCPToolError(MCPToolErrorCode.TIMEOUT, "tool discovery timed out") from exc
        except Exception as exc:  # noqa: BLE001 - mapped to an audit-safe code below
            raise MCPToolError(MCPToolErrorCode.INTERNAL_ERROR, "tool discovery failed") from exc

        return [
            MCPToolInfo(
                name=tool.name,
                description=tool.description or "",
                input_schema=tool.inputSchema or {},
            )
            for tool in result.tools
        ]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        timeout: float | None = None,
        session: ClientSession | None = None,
    ) -> dict[str, Any]:
        if session is not None:
            result = await self._invoke_tool(session, name, arguments, timeout=timeout)
            return _parse_call_tool_result(name, result)

        async with self._session_factory() as owned_session:
            result = await self._invoke_tool(owned_session, name, arguments, timeout=timeout)
        return _parse_call_tool_result(name, result)

    async def _invoke_tool(
        self,
        session: ClientSession,
        name: str,
        arguments: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> CallToolResult:
        effective_timeout = timeout if timeout is not None else self._timeout
        try:
            return await session.call_tool(
                name,
                arguments,
                read_timeout_seconds=timedelta(seconds=effective_timeout),
            )
        except TimeoutError as exc:
            raise MCPToolError(MCPToolErrorCode.TIMEOUT, f"tool '{name}' timed out") from exc
        except MCPToolError:
            raise
        except Exception as exc:  # noqa: BLE001 - mapped to an audit-safe code below
            logger.warning("mcp_client.call_tool transport error", extra={"tool": name})
            raise MCPToolError(
                MCPToolErrorCode.INTERNAL_ERROR, f"tool '{name}' call failed"
            ) from exc


def _parse_call_tool_result(name: str, result: CallToolResult) -> dict[str, Any]:
    if result.isError:
        raise MCPToolError(MCPToolErrorCode.INTERNAL_ERROR, f"tool '{name}' reported an error")

    payload: dict[str, Any] | None = None
    if result.structuredContent:
        payload = dict(result.structuredContent)
    else:
        for block in result.content:
            if isinstance(block, TextContent):
                try:
                    payload = json.loads(block.text)
                except ValueError:
                    continue
                break

    if payload is None:
        raise MCPToolError(
            MCPToolErrorCode.INTERNAL_ERROR, f"tool '{name}' returned an unreadable payload"
        )

    serialized_size = len(json.dumps(payload, ensure_ascii=False))
    if serialized_size > MAX_RESULT_BYTES:
        raise MCPToolError(
            MCPToolErrorCode.OVERSIZED_RESPONSE, f"tool '{name}' response exceeded size limit"
        )

    error_code = payload.get("error_code")
    if error_code is not None:
        message = str(payload.get("error_message", "tool reported an error"))
        try:
            code = MCPToolErrorCode(error_code)
        except ValueError:
            code = MCPToolErrorCode.INTERNAL_ERROR
        raise MCPToolError(code, message)

    return payload
