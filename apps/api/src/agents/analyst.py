"""Analyst agent: synthesizes research notes into a short analysis."""

from __future__ import annotations

from uuid import UUID

from agents.messages import (
    RESEARCH_NOTES_PREFIX,
    STRUCTURED_JSON_PROMPT,
    SUBTASK_PREFIX,
    USER_QUERY_PREFIX,
)
from agents.prompts import build_analyst_system_prompt
from agents.roles import ANALYST_ROLE, RoleConfig
from agents.schemas import AnalystSummary
from agents.tool_loop import run_tool_loop
from llm.protocol import ChatMessage, ChatRole, LLMClient, ToolDefinition
from mcp_client.client import MCPClient
from orchestration.models import ToolCallRecord


class AnalystAgent:
    async def analyze(
        self,
        user_query: str,
        *,
        task_id: UUID,
        llm: LLMClient,
        research_notes: list[str] | None = None,
        subtask: str | None = None,
        role: RoleConfig | None = None,
        mcp_client: MCPClient | None = None,
        tools: list[ToolDefinition] | None = None,
    ) -> tuple[AnalystSummary, list[ToolCallRecord]]:
        user_content = f"{USER_QUERY_PREFIX}{user_query}"
        if subtask:
            user_content += f"\n{SUBTASK_PREFIX}{subtask}"
        if research_notes:
            joined_notes = "\n".join(f"- {note}" for note in research_notes)
            user_content += f"\n{RESEARCH_NOTES_PREFIX}\n{joined_notes}"
        role_config = role or ANALYST_ROLE
        messages = [
            ChatMessage(
                role=ChatRole.SYSTEM,
                content=build_analyst_system_prompt(role_config),
            ),
            ChatMessage(role=ChatRole.USER, content=user_content),
        ]

        tool_calls: list[ToolCallRecord] = []
        if tools and mcp_client is not None:
            loop_result = await run_tool_loop(
                llm=llm,
                messages=messages,
                tools=tools,
                mcp_client=mcp_client,
                task_id=str(task_id),
            )
            messages = [
                *loop_result.messages,
                ChatMessage(
                    role=ChatRole.USER,
                    content=STRUCTURED_JSON_PROMPT,
                ),
            ]
            tool_calls = loop_result.tool_calls

        summary = await llm.chat_structured(
            messages,
            AnalystSummary,
            task_id=str(task_id),
        )
        return summary, tool_calls
