"""Writer single-agent prototype."""

from __future__ import annotations

from uuid import UUID

from agents.messages import (
    ANALYSIS_PREFIX,
    RESEARCH_NOTES_PREFIX,
    WRITER_TOPIC_PROMPT,
)
from agents.prompts import build_writer_system_prompt
from agents.roles import WRITER_ROLE, RoleConfig
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
        research_notes: list[str] | None = None,
        analysis: str | None = None,
        role: RoleConfig | None = None,
    ) -> WriterSummary:
        user_content = f"{WRITER_TOPIC_PROMPT}{topic}"
        if research_notes:
            joined_notes = "\n".join(f"- {note}" for note in research_notes)
            user_content += f"\n{RESEARCH_NOTES_PREFIX}\n{joined_notes}"
        if analysis:
            user_content += f"\n{ANALYSIS_PREFIX}\n{analysis}"
        role_config = role or WRITER_ROLE
        messages = [
            ChatMessage(
                role=ChatRole.SYSTEM,
                content=build_writer_system_prompt(role_config),
            ),
            ChatMessage(
                role=ChatRole.USER,
                content=user_content,
            ),
        ]
        result = await llm.chat_structured(
            messages,
            WriterSummary,
            task_id=str(task_id),
        )
        return result
