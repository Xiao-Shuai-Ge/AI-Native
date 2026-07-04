"""`EngineRouter` unit tests (auto engine selection + fallback)."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from llm.errors import LLMUnavailableError
from llm.fake import FakeLLMClient
from orchestration.engine_router import FALLBACK_ENGINE, EngineRouter
from orchestration.models import EngineChoice


@pytest.mark.asyncio
async def test_router_selects_structured_engine_decision() -> None:
    fake = FakeLLMClient(
        structured_handler=lambda _messages, schema: schema.model_validate(
            {
                "engine": "crewai",
                "reason": "role-play collaboration fits best",
                "subtasks": {"researcher": "look into topic"},
            }
        )
    )
    decision = await EngineRouter().select("some query", llm=fake, task_id="task-1")

    assert decision.engine == EngineChoice.CREWAI
    assert decision.reason == "role-play collaboration fits best"
    assert decision.subtasks == {"researcher": "look into topic"}
    assert fake.structured_calls


@pytest.mark.asyncio
async def test_router_falls_back_to_langgraph_on_invalid_engine_name() -> None:
    def _invalid_decision(_messages: object, schema: type[BaseModel]) -> BaseModel:
        # Triggers EngineRouterDecision's field_validator -> ValidationError.
        return schema.model_validate({"engine": "not-a-real-engine", "reason": "x"})

    fake = FakeLLMClient(structured_handler=_invalid_decision)

    decision = await EngineRouter().select("some query", llm=fake, task_id="task-2")

    assert decision.engine == FALLBACK_ENGINE
    assert decision.engine == EngineChoice.LANGGRAPH
    assert decision.reason.startswith("fallback:")


@pytest.mark.asyncio
async def test_router_falls_back_to_langgraph_when_llm_unavailable() -> None:
    fake = FakeLLMClient(error=LLMUnavailableError("provider down"))

    decision = await EngineRouter().select("some query", llm=fake, task_id="task-3")

    assert decision.engine == EngineChoice.LANGGRAPH
    assert "provider down" in decision.reason
