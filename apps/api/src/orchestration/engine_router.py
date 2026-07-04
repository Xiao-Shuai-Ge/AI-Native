"""`auto` engine routing: LLM structured decision with a safe fallback.

Implements AGENTS.md section 8: "`auto` 路由使用结构化 LLM 输出
`{engine, reason, subtasks}`；校验失败时 fallback 到 LangGraph."
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from agents.prompts import build_router_system_prompt
from agents.schemas import EngineRouterDecision
from llm.errors import LLMError
from llm.protocol import ChatMessage, ChatRole, LLMClient
from orchestration.models import EngineChoice

logger = logging.getLogger(__name__)

FALLBACK_ENGINE = EngineChoice.LANGGRAPH


class EngineRoutingResult:
    def __init__(self, *, engine: EngineChoice, reason: str, subtasks: dict[str, str]) -> None:
        self.engine = engine
        self.reason = reason
        self.subtasks = subtasks


class EngineRouter:
    """Selects `langgraph` or `crewai` for `engine=auto` tasks."""

    async def select(self, user_query: str, *, llm: LLMClient, task_id: str) -> EngineRoutingResult:
        messages = [
            ChatMessage(role=ChatRole.SYSTEM, content=build_router_system_prompt()),
            ChatMessage(role=ChatRole.USER, content=f"User query: {user_query}"),
        ]
        try:
            decision = await llm.chat_structured(
                messages,
                EngineRouterDecision,
                task_id=task_id,
            )
        except (LLMError, ValidationError) as exc:
            logger.warning(
                "engine router failed, falling back to langgraph",
                extra={"task_id": task_id, "error": str(exc)},
            )
            return EngineRoutingResult(
                engine=FALLBACK_ENGINE,
                reason=f"fallback: router LLM call failed ({exc})",
                subtasks={},
            )

        return EngineRoutingResult(
            engine=EngineChoice(decision.engine),
            reason=decision.reason,
            subtasks=decision.subtasks,
        )
