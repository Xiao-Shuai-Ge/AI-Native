"""Dapr Activity tests for `select_engine` and the CrewAI role activities."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from dapr.ext.workflow import WorkflowActivityContext

from llm.fake import FakeLLMClient
from llm.protocol import ChatMessage, ChatResponse
from workflows.activities.task_activities import (
    _run_crewai_analyst_impl,
    _run_crewai_researcher_impl,
    _run_crewai_writer_impl,
    _select_engine_impl,
)
from workflows.models import (
    CrewAIAnalystInput,
    CrewAIResearcherInput,
    CrewAIWriterInput,
    SelectEngineInput,
)
from workflows.sync_runtime import ActivityRuntime


@pytest.fixture
def activity_runtime() -> ActivityRuntime:
    session_factory = MagicMock()
    session_cm = MagicMock()
    session = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    session_factory.return_value = session_cm

    no_cache_result = MagicMock()
    no_cache_result.scalar_one_or_none.return_value = None
    session.execute.return_value = no_cache_result

    dapr_state = AsyncMock()
    event_publisher = AsyncMock()
    engine = AsyncMock()
    settings = MagicMock()
    dapr_client = AsyncMock()
    dapr_client.get_state.return_value = None

    runtime = ActivityRuntime(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        dapr_state=dapr_state,
        event_publisher=event_publisher,
        loop=asyncio.new_event_loop(),
        dapr_client=dapr_client,
    )

    with patch("workflows.sync_runtime._runtime", runtime):
        yield runtime


def _fake_llm_for_schema(payload_by_schema_hint: dict[str, dict[str, object]]) -> FakeLLMClient:
    def handler(messages: list[ChatMessage]) -> ChatResponse:
        content = " ".join(message.content for message in messages)
        for hint, payload in payload_by_schema_hint.items():
            if hint in content:
                return ChatResponse(content=json.dumps(payload), model="fake-model")
        msg = f"no matching schema hint in prompt: {content[:200]}"
        raise AssertionError(msg)

    return FakeLLMClient(chat_handler=handler)


@pytest.mark.asyncio
async def test_select_engine_persists_choice_and_publishes_event(
    activity_runtime: ActivityRuntime,
) -> None:
    ctx = MagicMock(spec=WorkflowActivityContext)
    task_id = uuid4()
    step_input = SelectEngineInput(
        task_id=task_id,
        session_id=uuid4(),
        user_id="user-1",
        user_query="Compare LangGraph and CrewAI",
    )

    fake_llm = FakeLLMClient(
        structured_handler=lambda _messages, schema: schema.model_validate(
            {"engine": "crewai", "reason": "collaboration needed", "subtasks": {}}
        )
    )
    mock_repo = AsyncMock()

    with (
        patch("workflows.activities.task_activities.TaskRepository", return_value=mock_repo),
        patch(
            "workflows.activities.task_activities.create_llm_client",
            return_value=fake_llm,
        ),
    ):
        result = await _select_engine_impl(step_input)

    assert result.engine_selected == "crewai"
    assert result.reason == "collaboration needed"
    mock_repo.update_task_status.assert_awaited_once()
    _, kwargs = mock_repo.update_task_status.await_args
    assert kwargs["engine_selection_reason"] == "collaboration needed"
    activity_runtime.event_publisher.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_crewai_researcher_skips_when_already_recorded(
    activity_runtime: ActivityRuntime,
) -> None:
    ctx = MagicMock(spec=WorkflowActivityContext)
    step_input = CrewAIResearcherInput(
        task_id=uuid4(),
        session_id=uuid4(),
        user_id="user-1",
        user_query="q",
        engine="crewai",
    )

    cached = MagicMock()
    cached.output_json = {"notes": ["cached note"], "sources": []}
    cached_result = MagicMock()
    cached_result.scalar_one_or_none.return_value = cached
    session = activity_runtime.session_factory.return_value.__aenter__.return_value  # type: ignore[attr-defined]
    session.execute.return_value = cached_result

    mock_repo = AsyncMock()
    with (
        patch("workflows.activities.task_activities.TaskRepository", return_value=mock_repo),
        patch("workflows.activities.task_activities.create_llm_client") as create_client,
    ):
        result = await _run_crewai_researcher_impl(step_input)

    assert result.notes == ["cached note"]
    create_client.assert_not_called()
    mock_repo.record_step.assert_not_awaited()
    activity_runtime.event_publisher.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_crewai_researcher_executes_and_records_step(
    activity_runtime: ActivityRuntime,
) -> None:
    ctx = MagicMock(spec=WorkflowActivityContext)
    step_input = CrewAIResearcherInput(
        task_id=uuid4(),
        session_id=uuid4(),
        user_id="user-1",
        user_query="What is Dapr Workflow?",
        engine="crewai",
    )
    fake_llm = _fake_llm_for_schema(
        {"ResearcherNotes": {"notes": ["note a"], "sources": []}},
    )
    mock_repo = AsyncMock()

    with (
        patch("workflows.activities.task_activities.TaskRepository", return_value=mock_repo),
        patch(
            "workflows.activities.task_activities.create_llm_client",
            return_value=fake_llm,
        ),
    ):
        result = await _run_crewai_researcher_impl(step_input)

    assert result.notes == ["note a"]
    mock_repo.record_step.assert_awaited_once()
    activity_runtime.event_publisher.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_crewai_analyst_executes_and_records_step(
    activity_runtime: ActivityRuntime,
) -> None:
    ctx = MagicMock(spec=WorkflowActivityContext)
    step_input = CrewAIAnalystInput(
        task_id=uuid4(),
        session_id=uuid4(),
        user_id="user-1",
        user_query="What is Dapr Workflow?",
        engine="crewai",
        research_notes=["note a"],
    )
    fake_llm = _fake_llm_for_schema(
        {"AnalystSummary": {"analysis": "synthesized analysis"}},
    )
    mock_repo = AsyncMock()

    with (
        patch("workflows.activities.task_activities.TaskRepository", return_value=mock_repo),
        patch(
            "workflows.activities.task_activities.create_llm_client",
            return_value=fake_llm,
        ),
    ):
        result = await _run_crewai_analyst_impl(step_input)

    assert result.analysis == "synthesized analysis"
    mock_repo.record_step.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_crewai_writer_executes_records_and_updates_report(
    activity_runtime: ActivityRuntime,
) -> None:
    ctx = MagicMock(spec=WorkflowActivityContext)
    step_input = CrewAIWriterInput(
        task_id=uuid4(),
        session_id=uuid4(),
        user_id="user-1",
        user_query="What is Dapr Workflow?",
        engine="crewai",
        research_notes=["note a"],
        analysis="synthesized analysis",
    )
    fake_llm = _fake_llm_for_schema(
        {
            "WriterSummary": {
                "title": "T",
                "summary": "S",
                "markdown": "# T\n\nS",
            }
        },
    )
    mock_repo = AsyncMock()

    with (
        patch("workflows.activities.task_activities.TaskRepository", return_value=mock_repo),
        patch(
            "workflows.activities.task_activities.create_llm_client",
            return_value=fake_llm,
        ),
    ):
        result = await _run_crewai_writer_impl(step_input)

    assert result.report == "# T\n\nS"
    mock_repo.record_step.assert_awaited_once()
    activity_runtime.dapr_state.merge_task_runtime_state.assert_awaited()
