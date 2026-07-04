"""Analyst agent: synthesizes research notes into a short analysis."""

from __future__ import annotations

from uuid import UUID

from agents.prompts import build_analyst_system_prompt
from agents.roles import ANALYST_ROLE
from agents.schemas import AnalystSummary
from llm.protocol import ChatMessage, ChatRole, LLMClient


class AnalystAgent:
    async def analyze(
        self,
        user_query: str,
        *,
        task_id: UUID,
        llm: LLMClient,
        research_notes: list[str] | None = None,
        subtask: str | None = None,
    ) -> AnalystSummary:
        user_content = f"User query: {user_query}"
        if subtask:
            user_content += f"\nSubtask: {subtask}"
        if research_notes:
            joined_notes = "\n".join(f"- {note}" for note in research_notes)
            user_content += f"\nResearch notes:\n{joined_notes}"
        messages = [
            ChatMessage(
                role=ChatRole.SYSTEM,
                content=build_analyst_system_prompt(ANALYST_ROLE),
            ),
            ChatMessage(role=ChatRole.USER, content=user_content),
        ]
        return await llm.chat_structured(
            messages,
            AnalystSummary,
            task_id=str(task_id),
        )
