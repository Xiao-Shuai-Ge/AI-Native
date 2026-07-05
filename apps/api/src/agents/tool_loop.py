"""Shared ReAct-style tool-calling loop for LangGraph nodes and CrewAI.

Both orchestration engines route every LLM provider through the same
`LLMClient` protocol (AGENTS.md section 2: "所有供应商必须走同一个 LLMClient
接口"), so tool-calling logic lives here once and is reused by
`orchestration/langgraph_engine/nodes.py` and
`orchestration/crewai_engine/llm_bridge.py` instead of relying on
framework-native tool wrappers (LangChain `bind_tools`, CrewAI's built-in
tool objects) that would bypass `LLMClient` (see the Day 7 plan's "已确认的
设计决策"). Only tools explicitly listed in a role's `tool_allowlist` are
ever exposed to the model (AGENTS.md section 7).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from mcp import ClientSession

from agents.roles import RoleConfig
from llm.protocol import ChatMessage, ChatRole, LLMClient, ToolDefinition
from mcp_client.client import MCPClient
from mcp_client.errors import MCPToolError, MCPToolErrorCode
from mcp_client.schema import filter_by_allowlist, to_tool_definition
from orchestration.models import ToolCallRecord

logger = logging.getLogger(__name__)

DEFAULT_MAX_ROUNDS = 4
DEFAULT_TOOL_TIMEOUT_SECONDS = 15.0
MAX_TOOL_RESULT_SUMMARY_CHARS = 2_000


@dataclass
class ToolLoopResult:
    """Outcome of `run_tool_loop`: the full conversation plus an audit trail."""

    messages: list[ChatMessage]
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    final_content: str = ""


async def resolve_role_tools(
    role: RoleConfig,
    *,
    mcp_client: MCPClient,
    session: ClientSession | None = None,
) -> list[ToolDefinition]:
    """Discovers MCP tools and filters them down to the role's allowlist.

    Degrades to "no tools" (rather than failing the whole step) if the MCP
    server is unreachable, so a temporarily-down tool provider never blocks
    the researcher/analyst from producing a text-only answer.
    """
    if not role.tool_allowlist:
        return []
    try:
        discovered = await mcp_client.discover_tools(session=session)
    except MCPToolError:
        logger.warning("tool discovery failed; continuing without tools", extra={"role": role.role})
        return []
    except BaseExceptionGroup:
        logger.warning("tool discovery failed; continuing without tools", extra={"role": role.role})
        return []
    except Exception:
        logger.warning("tool discovery failed; continuing without tools", extra={"role": role.role})
        return []
    allowed = filter_by_allowlist(discovered, role.tool_allowlist)
    return [to_tool_definition(tool) for tool in allowed]


async def run_tool_loop(
    *,
    llm: LLMClient,
    messages: list[ChatMessage],
    tools: list[ToolDefinition],
    mcp_client: MCPClient,
    task_id: str | None = None,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    tool_timeout_seconds: float = DEFAULT_TOOL_TIMEOUT_SECONDS,
    mcp_session: ClientSession | None = None,
) -> ToolLoopResult:
    """Runs "LLM decides -> tool executes -> result fed back" until the model
    stops requesting tools or `max_rounds` is reached (a hard node-level cap,
    per AGENTS.md section 7: "限制每个节点的最大 token、超时和重试次数").
    """
    if not tools:
        response = await llm.chat(messages, task_id=task_id)
        conversation = [*messages, ChatMessage(role=ChatRole.ASSISTANT, content=response.content)]
        return ToolLoopResult(messages=conversation, final_content=response.content)

    conversation = list(messages)
    tool_call_records: list[ToolCallRecord] = []
    allowed_tool_names = {tool.name for tool in tools}

    async def _run_rounds(session: ClientSession) -> ToolLoopResult:
        nonlocal conversation, tool_call_records
        for _round_index in range(max_rounds):
            response = await llm.chat(conversation, task_id=task_id, tools=tools)

            if not response.tool_calls:
                conversation.append(ChatMessage(role=ChatRole.ASSISTANT, content=response.content))
                return ToolLoopResult(
                    messages=conversation,
                    tool_calls=tool_call_records,
                    final_content=response.content,
                )

            conversation.append(
                ChatMessage(
                    role=ChatRole.ASSISTANT,
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )
            for call in response.tool_calls:
                record = ToolCallRecord(
                    tool_name=call.name,
                    arguments=call.arguments,
                    started_at=datetime.now(UTC),
                )
                if call.name not in allowed_tool_names:
                    result_text = json.dumps(
                        {
                            "error_code": MCPToolErrorCode.UNAUTHORIZED.value,
                            "error_message": f"tool '{call.name}' is not in the role allowlist",
                        }
                    )
                    record.error = (
                        f"{MCPToolErrorCode.UNAUTHORIZED.value}: "
                        f"tool '{call.name}' is not in the role allowlist"
                    )
                    logger.warning(
                        "tool_loop.tool_not_allowed",
                        extra={"tool": call.name},
                    )
                else:
                    try:
                        result = await mcp_client.call_tool(
                            call.name,
                            call.arguments,
                            timeout=tool_timeout_seconds,
                            session=session,
                        )
                        result_text = json.dumps(result, ensure_ascii=False)
                        record.result_summary = result_text[:MAX_TOOL_RESULT_SUMMARY_CHARS]
                    except MCPToolError as exc:
                        result_text = json.dumps(
                            {"error_code": exc.code.value, "error_message": exc.message}
                        )
                        record.error = f"{exc.code.value}: {exc.message}"
                        logger.warning(
                            "tool_loop.tool_call_failed",
                            extra={"tool": call.name, "error_code": exc.code.value},
                        )
                record.finished_at = datetime.now(UTC)
                tool_call_records.append(record)
                conversation.append(
                    ChatMessage(role=ChatRole.TOOL, content=result_text, tool_call_id=call.id)
                )

        response = await llm.chat(conversation, task_id=task_id)
        conversation.append(ChatMessage(role=ChatRole.ASSISTANT, content=response.content))
        return ToolLoopResult(
            messages=conversation, tool_calls=tool_call_records, final_content=response.content
        )

    if mcp_session is not None:
        return await _run_rounds(mcp_session)

    async with mcp_client.session() as session:
        return await _run_rounds(session)
