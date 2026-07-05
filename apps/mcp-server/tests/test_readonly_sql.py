"""Unit tests for the `readonly_sql` tool."""

from __future__ import annotations

import asyncpg
import pytest

from mcp_server.errors import ToolError, ToolErrorCode
from mcp_server.tools.readonly_sql import ReadonlySqlInput, run_query


class FakeRecord(dict):
    """asyncpg.Record supports both `dict(record)` and `.keys()`."""


class FakeConnection:
    def __init__(self, records: list[dict] | Exception) -> None:
        self._records = records
        self.last_query: str | None = None

    async def fetch(self, query: str) -> list[dict]:
        self.last_query = query
        if isinstance(self._records, Exception):
            raise self._records
        return [FakeRecord(r) for r in self._records]


class FakeAcquireContext:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self._connection

    async def __aexit__(self, *exc_info: object) -> None:
        return None


class FakePool:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    def acquire(self) -> FakeAcquireContext:
        return FakeAcquireContext(self._connection)


@pytest.mark.asyncio
async def test_run_query_returns_rows() -> None:
    connection = FakeConnection([{"id": 1, "title": "Dapr"}, {"id": 2, "title": "MCP"}])
    pool = FakePool(connection)
    result = await run_query(ReadonlySqlInput(query="SELECT id, title FROM kb_articles"), pool=pool)
    assert result.row_count == 2
    assert result.columns == ["id", "title"]
    assert result.truncated is False


@pytest.mark.asyncio
async def test_run_query_marks_truncated_when_over_max_rows() -> None:
    connection = FakeConnection([{"id": i} for i in range(5)])
    pool = FakePool(connection)
    result = await run_query(
        ReadonlySqlInput(query="SELECT id FROM kb_articles"), pool=pool, max_rows=3
    )
    assert result.row_count == 3
    assert result.truncated is True


@pytest.mark.asyncio
async def test_run_query_wraps_statement_to_enforce_limit() -> None:
    connection = FakeConnection([])
    pool = FakePool(connection)
    await run_query(ReadonlySqlInput(query="SELECT 1"), pool=pool, max_rows=10)
    assert connection.last_query is not None
    assert "LIMIT 11" in connection.last_query
    assert "SELECT 1" in connection.last_query


@pytest.mark.asyncio
async def test_run_query_allows_forbidden_keyword_inside_string_literal() -> None:
    connection = FakeConnection([{"title": "delete me later"}])
    pool = FakePool(connection)
    result = await run_query(
        ReadonlySqlInput(query="SELECT title FROM kb_articles WHERE title LIKE '%delete%'"),
        pool=pool,
    )
    assert result.row_count == 1


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM kb_articles",
        "DROP TABLE kb_articles",
        "UPDATE kb_articles SET title = 'x'",
        "SELECT 1; DROP TABLE kb_articles;",
        "INSERT INTO kb_articles VALUES (1)",
    ],
)
@pytest.mark.asyncio
async def test_run_query_rejects_non_select_statements(query: str) -> None:
    pool = FakePool(FakeConnection([]))
    with pytest.raises(ToolError) as excinfo:
        await run_query(ReadonlySqlInput(query=query), pool=pool)
    assert excinfo.value.code == ToolErrorCode.INVALID_INPUT


def test_input_rejects_empty_query() -> None:
    with pytest.raises(ValueError):
        ReadonlySqlInput(query="")


@pytest.mark.asyncio
async def test_run_query_raises_timeout_error() -> None:
    class SlowConnection(FakeConnection):
        async def fetch(self, query: str) -> list[dict]:
            raise TimeoutError

    pool = FakePool(SlowConnection([]))
    with pytest.raises(ToolError) as excinfo:
        await run_query(ReadonlySqlInput(query="SELECT 1"), pool=pool)
    assert excinfo.value.code == ToolErrorCode.TIMEOUT


@pytest.mark.asyncio
async def test_run_query_raises_unauthorized_error() -> None:
    connection = FakeConnection(asyncpg.InsufficientPrivilegeError("permission denied"))
    pool = FakePool(connection)
    with pytest.raises(ToolError) as excinfo:
        await run_query(ReadonlySqlInput(query="SELECT * FROM secret_table"), pool=pool)
    assert excinfo.value.code == ToolErrorCode.UNAUTHORIZED
