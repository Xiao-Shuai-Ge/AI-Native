"""FastMCP server exposing the 4 P0 tools over Streamable HTTP.

Each tool wraps a pure `mcp_server.tools.*` implementation. `ToolError` is
caught at this boundary and turned into an MCP tool-call error result whose
message is only ever `code: message` (see `mcp_server/errors.py`) — internal
exception details never reach the caller.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
import httpx
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette

from mcp_server.config import Settings, get_settings
from mcp_server.errors import ToolError
from mcp_server.tools.calculator import CalculatorInput, run_calculator
from mcp_server.tools.code_runner import CodeRunnerInput, DockerSandboxRunner, run_code
from mcp_server.tools.readonly_sql import ReadonlySqlInput, run_query
from mcp_server.tools.web_search import WebSearchInput, search

logger = logging.getLogger(__name__)


class ServerState:
    """Shared resources (HTTP client, DB pool, sandbox runner) for tool calls."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.http_client = httpx.AsyncClient()
        self.sandbox_runner = DockerSandboxRunner(
            image=settings.code_runner_image,
            memory_limit=settings.code_runner_memory_limit,
            cpu_limit=settings.code_runner_cpu_limit,
        )
        self._pg_pool: asyncpg.Pool | None = None

    def get_http_client(self) -> httpx.AsyncClient:
        if self.http_client.is_closed:
            self.http_client = httpx.AsyncClient()
        return self.http_client

    async def get_pg_pool(self) -> asyncpg.Pool:
        if self._pg_pool is None:
            self._pg_pool = await asyncpg.create_pool(
                self.settings.readonly_sql_dsn, min_size=1, max_size=5
            )
        return self._pg_pool

    async def aclose(self) -> None:
        await self.http_client.aclose()
        if self._pg_pool is not None:
            await self._pg_pool.close()


def _tool_error_payload(error: ToolError) -> dict[str, Any]:
    logger.warning(
        "mcp.tool.call failed", extra={"code": error.code.value, "message": error.message}
    )
    return {"error_code": error.code.value, "error_message": error.message}


def create_mcp_server(settings: Settings | None = None) -> FastMCP:
    resolved_settings = settings or get_settings()
    state = ServerState(resolved_settings)

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await state.aclose()

    mcp = FastMCP(
        name="ainative-mcp-server",
        instructions=(
            "AI Native demo tools: calculator, web_search, code_runner, readonly_sql. "
            "Only call a tool if it is explicitly needed to answer the current step."
        ),
        stateless_http=True,
        lifespan=lifespan,
    )

    @mcp.tool(
        name="calculator",
        description="Evaluate a whitelisted arithmetic expression (no arbitrary code execution).",
    )
    def calculator(expression: str) -> dict[str, Any]:
        try:
            return run_calculator(CalculatorInput(expression=expression)).model_dump()
        except ToolError as exc:
            return _tool_error_payload(exc)

    @mcp.tool(
        name="web_search",
        description="Search the web with Bocha/LangSearch and return up to 5 titles, summaries, and URLs.",
    )
    async def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
        try:
            payload = WebSearchInput(query=query, max_results=max_results)
            result = await search(
                payload,
                http_client=state.get_http_client(),
                api_key=resolved_settings.bocha_api_key,
                endpoint=resolved_settings.bocha_search_url,
                timeout=resolved_settings.web_search_timeout_seconds,
            )
            return result.model_dump()
        except ToolError as exc:
            return _tool_error_payload(exc)

    @mcp.tool(
        name="code_runner",
        description=(
            "Run a short Python or Shell snippet inside an isolated, network-less sandbox "
            "container. Use only for small data-processing or calculations."
        ),
    )
    async def code_runner(language: str, code: str, timeout_seconds: float = 5.0) -> dict[str, Any]:
        try:
            payload = CodeRunnerInput(language=language, code=code, timeout_seconds=timeout_seconds)  # type: ignore[arg-type]
            result = await run_code(payload, runner=state.sandbox_runner)
            return result.model_dump()
        except ToolError as exc:
            return _tool_error_payload(exc)

    @mcp.tool(
        name="readonly_sql",
        description="Run a single read-only SELECT query against the demo knowledge base.",
    )
    async def readonly_sql(query: str) -> dict[str, Any]:
        try:
            pool = await state.get_pg_pool()
            result = await run_query(
                ReadonlySqlInput(query=query),
                pool=pool,
                timeout=resolved_settings.readonly_sql_timeout_seconds,
                max_rows=resolved_settings.readonly_sql_max_rows,
            )
            return result.model_dump()
        except ToolError as exc:
            return _tool_error_payload(exc)

    return mcp


def create_app(settings: Settings | None = None) -> Starlette:
    """Returns the ASGI app to serve via uvicorn (Streamable HTTP transport)."""
    mcp = create_mcp_server(settings)
    return mcp.streamable_http_app()
