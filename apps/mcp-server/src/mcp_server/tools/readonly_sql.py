"""`readonly_sql` tool: runs a single read-only `SELECT` against the demo DB.

Per AGENTS.md section 10 ("`readonly_sql` 仅允许单条 `SELECT`，使用只读数据库
用户，并限制行数"): only one `SELECT`/`WITH ... SELECT` statement is
accepted, the connection must use a read-only database role
(`READONLY_SQL_DSN`, see `infra`/migrations for the role grant), and both row
count and execution time are capped.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Protocol

import asyncpg
from pydantic import BaseModel, Field

from mcp_server.errors import ToolError, ToolErrorCode

MAX_QUERY_LENGTH = 2_000
MAX_ROWS = 100
DEFAULT_TIMEOUT_SECONDS = 5.0

_FORBIDDEN_KEYWORDS = (
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "create",
    "grant",
    "revoke",
    "truncate",
    "call",
    "copy",
    "execute",
    "merge",
    "vacuum",
    "lock",
)


class ReadonlySqlInput(BaseModel):
    query: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)


class ReadonlySqlOutput(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int
    truncated: bool


class ConnectionAcquirer(Protocol):
    """Structural subset of `asyncpg.Pool` used here, so tests can fake it."""

    def acquire(self) -> Any: ...


def _strip_sql_literals_and_comments(statement: str) -> str:
    """Removes string literals and comments so keyword scans ignore their contents."""
    result: list[str] = []
    i = 0
    length = len(statement)
    while i < length:
        if statement[i : i + 2] == "--":
            while i < length and statement[i] != "\n":
                i += 1
            continue
        if statement[i : i + 2] == "/*":
            end = statement.find("*/", i + 2)
            i = end + 2 if end != -1 else length
            continue
        if statement[i] in ("'", '"'):
            quote = statement[i]
            i += 1
            while i < length:
                if statement[i] == quote:
                    if i + 1 < length and statement[i + 1] == quote:
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            result.append(" ")
            continue
        result.append(statement[i])
        i += 1
    return "".join(result)


def _validate_single_select(raw_query: str) -> str:
    statement = raw_query.strip()
    if statement.endswith(";"):
        statement = statement[:-1].strip()
    if ";" in statement:
        raise ToolError(ToolErrorCode.INVALID_INPUT, "only a single SQL statement is allowed")
    if not statement:
        raise ToolError(ToolErrorCode.INVALID_INPUT, "query must not be empty")

    first_word = re.split(r"\s+", statement, maxsplit=1)[0].lower()
    if first_word not in {"select", "with"}:
        raise ToolError(ToolErrorCode.INVALID_INPUT, "only SELECT queries are allowed")

    scan_target = _strip_sql_literals_and_comments(statement).lower()
    for keyword in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", scan_target):
            raise ToolError(ToolErrorCode.INVALID_INPUT, f"query must not contain '{keyword}'")
    return statement


async def run_query(
    payload: ReadonlySqlInput,
    *,
    pool: ConnectionAcquirer,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_rows: int = MAX_ROWS,
) -> ReadonlySqlOutput:
    statement = _validate_single_select(payload.query)
    wrapped = f"SELECT * FROM ({statement}) AS mcp_readonly_sql_subquery LIMIT {max_rows + 1}"

    async with pool.acquire() as connection:
        try:
            records = await asyncio.wait_for(connection.fetch(wrapped), timeout=timeout)
        except TimeoutError as exc:
            raise ToolError(ToolErrorCode.TIMEOUT, "query exceeded the time limit") from exc
        except asyncpg.InsufficientPrivilegeError as exc:
            raise ToolError(
                ToolErrorCode.UNAUTHORIZED, "insufficient privileges for this query"
            ) from exc
        except asyncpg.PostgresSyntaxError as exc:
            raise ToolError(ToolErrorCode.INVALID_INPUT, "query has invalid SQL syntax") from exc
        except asyncpg.PostgresError as exc:
            raise ToolError(ToolErrorCode.INTERNAL_ERROR, "query execution failed") from exc

    truncated = len(records) > max_rows
    limited_records = records[:max_rows]
    columns = list(limited_records[0].keys()) if limited_records else []
    rows = [dict(record) for record in limited_records]
    return ReadonlySqlOutput(columns=columns, rows=rows, row_count=len(rows), truncated=truncated)
