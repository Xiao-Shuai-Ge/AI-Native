"""Dapr Activity tests for `select_engine` and the CrewAI role activities."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from dapr.ext.workflow import WorkflowActivityContext

from llm.fake import FakeLLMClient
from llm.protocol import ChatMessage, ChatResponse
from orchestration.models import ToolCallRecord
from workflows.activities.task_activities import (
    _commit_crewai_step,
    _run_crewai_analyst_impl,
    _run_crewai_researcher_impl,
    _run_crewai_writer_impl,
    _select_engine_impl,
)
from workflows.models import (
    CrewAIAnalystInput,
    CrewAIResearcherInput,
    CrewAIResearcherResult,
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
async def test_commit_crewai_step_persists_json_safe_output(
    activity_runtime: ActivityRuntime,
) -> None:
    task_id = uuid4()
    started_at = datetime(2026, 7, 5, 7, 12, tzinfo=UTC)
    result = CrewAIResearcherResult(
        notes=["note a"],
        tool_calls=[
            ToolCallRecord(
                tool_name="web_search",
                arguments={"query": "Dapr Workflow"},
                started_at=started_at,
            )
        ],
    )
    mock_repo = AsyncMock()
    mock_repo.record_step.return_value = MagicMock()

    with patch("workflows.activities.task_activities.TaskRepository", return_value=mock_repo):
        committed = await _commit_crewai_step(
            task_id=task_id,
            step_name="researcher",
            engine="crewai",
            idempotency_key=f"{task_id}:researcher:crewai",
            result=result,
            result_type=CrewAIResearcherResult,
        )

    assert committed == result
    output_json = mock_repo.record_step.await_args.kwargs["output_json"]
    assert output_json["tool_calls"][0]["started_at"] == "2026-07-05T07:12:00Z"


@pytest.mark.asyncio
async def test_run_crewai_researcher_uses_peer_output_when_persist_loses_race(
    activity_runtime: ActivityRuntime,
) -> None:
    step_input = CrewAIResearcherInput(
        task_id=uuid4(),
        session_id=uuid4(),
        user_id="user-1",
        user_query="What is Dapr Workflow?",
        engine="crewai",
    )
    fake_llm = _fake_llm_for_schema(
        {"ResearcherNotes": {"notes": ["local note"], "sources": []}},
    )
    mock_repo = AsyncMock()
    mock_repo.record_step.return_value = None

    load_attempt = 0
    session = activity_runtime.session_factory.return_value.__aenter__.return_value  # type: ignore[attr-defined]

    def execute_side_effect(*_args: object, **_kwargs: object) -> MagicMock:
        nonlocal load_attempt
        load_attempt += 1
        result = MagicMock()
        if load_attempt >= 3:
            cached = MagicMock()
            cached.output_json = {"notes": ["peer note"], "sources": []}
            result.scalar_one_or_none.return_value = cached
        else:
            result.scalar_one_or_none.return_value = None
        return result

    session.execute.side_effect = execute_side_effect

    with (
        patch("workflows.activities.task_activities.TaskRepository", return_value=mock_repo),
        patch(
            "workflows.activities.task_activities.create_llm_client",
            return_value=fake_llm,
        ),
    ):
        result = await _run_crewai_researcher_impl(step_input)

    assert result.notes == ["peer note"]
    activity_runtime.event_publisher.publish.assert_not_awaited()


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


@pytest.mark.asyncio
async def test_run_crewai_writer_forwards_subtask_to_role_prompt(
    activity_runtime: ActivityRuntime,
) -> None:
    step_input = CrewAIWriterInput(
        task_id=uuid4(),
        session_id=uuid4(),
        user_id="user-1",
        user_query="What is Dapr Workflow?",
        engine="crewai",
        research_notes=["note a"],
        analysis="synthesized analysis",
        subtask="write an executive summary",
    )
    seen_prompts: list[str] = []

    def handler(messages: list[ChatMessage]) -> ChatResponse:
        content = " ".join(message.content for message in messages)
        seen_prompts.append(content)
        payload = {
            "title": "T",
            "summary": "S",
            "markdown": "# T\n\nS",
        }
        return ChatResponse(content=json.dumps(payload), model="fake-model")

    mock_repo = AsyncMock()

    with (
        patch("workflows.activities.task_activities.TaskRepository", return_value=mock_repo),
        patch(
            "workflows.activities.task_activities.create_llm_client",
            return_value=FakeLLMClient(chat_handler=handler),
        ),
    ):
        await _run_crewai_writer_impl(step_input)

    assert seen_prompts
    assert "子任务：write an executive summary" in seen_prompts[0]
