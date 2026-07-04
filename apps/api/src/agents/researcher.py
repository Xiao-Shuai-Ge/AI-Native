"""Researcher agent: produces short factual notes for a query."""

from __future__ import annotations

from uuid import UUID

from agents.prompts import build_researcher_system_prompt
from agents.roles import RESEARCHER_ROLE, RoleConfig
from agents.schemas import ResearcherNotes
from llm.protocol import ChatMessage, ChatRole, LLMClient


class ResearcherAgent:
    async def research(
        self,
        user_query: str,
        *,
        task_id: UUID,
        llm: LLMClient,
        subtask: str | None = None,
        role: RoleConfig | None = None,
    ) -> ResearcherNotes:
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
        return await llm.chat_structured(
            messages,
            ResearcherNotes,
            task_id=str(task_id),
        )
