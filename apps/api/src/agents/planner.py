"""Planner: selects a subset of registered roles for a task."""

from __future__ import annotations

from uuid import UUID

from agents.messages import USER_QUERY_PREFIX
from agents.prompts import build_planner_system_prompt
from agents.schemas import PlanOutput
from llm.protocol import ChatMessage, ChatRole, LLMClient


class PlannerAgent:
    """Chooses which registered roles (researcher/analyst/writer) run for a task."""

    async def plan(
        self,
        user_query: str,
        *,
        task_id: UUID,
        llm: LLMClient,
    ) -> PlanOutput:
        messages = [
            ChatMessage(role=ChatRole.SYSTEM, content=build_planner_system_prompt()),
            ChatMessage(
                role=ChatRole.USER,
                content=f"{USER_QUERY_PREFIX}{user_query}",
            ),
        ]
        return await llm.chat_structured(
            messages,
            PlanOutput,
            task_id=str(task_id),
        )
