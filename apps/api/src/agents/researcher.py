"""Researcher agent: produces short factual notes for a query."""

from __future__ import annotations

from uuid import UUID

from agents.prompts import build_researcher_system_prompt
from agents.roles import RESEARCHER_ROLE, RoleConfig
from agents.schemas import ResearcherNotes
from agents.tool_loop import run_tool_loop
from llm.protocol import ChatMessage, ChatRole, LLMClient, ToolDefinition
from mcp_client.client import MCPClient
from orchestration.models import ToolCallRecord


class ResearcherAgent:
    async def research(
        self,
        user_query: str,
        *,
        task_id: UUID,
        llm: LLMClient,
        subtask: str | None = None,
        role: RoleConfig | None = None,
        mcp_client: MCPClient | None = None,
        tools: list[ToolDefinition] | None = None,
    ) -> tuple[ResearcherNotes, list[ToolCallRecord]]:
        user_content = f"User query: {user_query}"
        if subtask:
            user_content += f"\nSubtask: {subtask}"
        role_config = role or RESEARCHER_ROLE
        messages = [
            ChatMessage(
                role=ChatRole.SYSTEM,
                content=build_researcher_system_prompt(role_config),
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
                    content="Now produce your final answer as the required structured JSON.",
                ),
            ]
            tool_calls = loop_result.tool_calls

        notes = await llm.chat_structured(
            messages,
            ResearcherNotes,
            task_id=str(task_id),
        )
        return notes, tool_calls
