"""Writer single-agent prototype."""

from __future__ import annotations

from uuid import UUID

from agents.prompts import build_writer_system_prompt
from agents.roles import WRITER_ROLE
from agents.schemas import WriterSummary
from llm.protocol import ChatMessage, ChatRole, LLMClient


class WriterAgent:
    """Day 2 writer prototype that returns structured Markdown summaries."""

    async def summarize(
        self,
        topic: str,
        *,
        task_id: UUID,
        llm: LLMClient,
    ) -> WriterSummary:
        messages = [
            ChatMessage(
                role=ChatRole.SYSTEM,
                content=build_writer_system_prompt(WRITER_ROLE),
            ),
            ChatMessage(
                role=ChatRole.USER,
                content=f"Write a Markdown summary for this topic: {topic}",
            ),
        ]
        result = await llm.chat_structured(
            messages,
            WriterSummary,
            task_id=str(task_id),
        )
        return result
