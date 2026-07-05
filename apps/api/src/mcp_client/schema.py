"""Converts MCP tool metadata into the shapes needed by each consumer.

`llm.protocol.ToolDefinition` is used by both the LangGraph tool loop and the
CrewAI bridge (see `agents/tool_loop.py`) so the two engines share one
tool-calling code path instead of maintaining separate tool schema
translations (AGENTS.md section 8: "两个引擎共用...实现").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from llm.protocol import ToolDefinition


@dataclass
class MCPToolInfo:
    """A tool discovered from the MCP server, with its raw JSON schema kept."""

    name: str
    description: str
    input_schema: dict[str, Any]


def to_tool_definition(tool: MCPToolInfo) -> ToolDefinition:
    return ToolDefinition(
        name=tool.name,
        description=tool.description,
        parameters=tool.input_schema or {"type": "object", "properties": {}},
    )


def filter_by_allowlist(tools: list[MCPToolInfo], allowlist: list[str]) -> list[MCPToolInfo]:
    """Returns only the tools whose name is in `allowlist`.

    Enforces AGENTS.md section 7 ("Agent 只能调用显式 allowlist 中的工具") at
    the schema-conversion boundary, before any tool definition ever reaches
    an LLM prompt or a CrewAI Agent.
    """
    allowed = set(allowlist)
    return [tool for tool in tools if tool.name in allowed]
