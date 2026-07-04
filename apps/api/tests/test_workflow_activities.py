"""Workflow activity unit tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from dapr.ext.workflow import WorkflowActivityContext
from pydantic import BaseModel

from agents.schemas import PlanOutput, WriterSummary
from llm.fake import FakeLLMClient
from llm.protocol import ChatMessage
from orchestration.models import TaskStatus
from persistence.models import TaskRecord
from workflows.activities.task_activities import (
    delayed_step,
    execute_step,
    finalize_task,
    initialize_task,
    mark_task_failed,
    run_langgraph_graph,
)
from workflows.models import (
    DelayedStepInput,
    FinalizeTaskInput,
    LangGraphStepInput,
    StepActivityInput,
    TaskFailureInput,
    TaskWorkflowInput,
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

    dapr_state = AsyncMock()
    event_publisher = AsyncMock()
    engine = AsyncMock()
    settings = MagicMock()
    dapr_client = AsyncMock()
    dapr_client.get_blob.return_value = None
    dapr_client.get_blob_entry.return_value = (None, None)
    dapr_client.get_state.return_value = None
    dapr_client.save_blob_cas.return_value = True

    runtime = ActivityRuntime(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        dapr_state=dapr_state,
        event_publisher=event_publisher,
        loop=MagicMock(),
        dapr_client=dapr_client,
    )

    with patch("workflows.sync_runtime._runtime", runtime):
        yield runtime


def _wf_input() -> TaskWorkflowInput:
    task_id = uuid4()
    session_id = uuid4()
    return TaskWorkflowInput(
        task_id=task_id,
        session_id=session_id,
        user_id="user-1",
        user_query="activity test",
        engine_requested="auto",
        workflow_id=f"wf-{task_id}",
        thread_id=str(task_id),
        delay_seconds=0.0,
    )


def _task_record(wf_input: TaskWorkflowInput, *, status: str) -> TaskRecord:
    now = datetime.now(tz=UTC)
    return TaskRecord(
        id=wf_input.task_id,
        session_id=wf_input.session_id,
        user_id=wf_input.user_id,
        user_query=wf_input.user_query,
        engine_requested=wf_input.engine_requested,
        status=status,
        workflow_id=wf_input.workflow_id,
        thread_id=wf_input.thread_id,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_initialize_task_updates_status(activity_runtime: ActivityRuntime) -> None:
    wf_input = _wf_input()
    ctx = MagicMock(spec=WorkflowActivityContext)

    mock_repo = AsyncMock()
    mock_repo.get_task.return_value = _task_record(wf_input, status=TaskStatus.QUEUED.value)
    mock_repo.update_task_status = AsyncMock()

    with patch("workflows.activities.task_activities.TaskRepository", return_value=mock_repo):
        result = await initialize_task(ctx, wf_input)

    assert result.status == "running"
    mock_repo.update_task_status.assert_awaited_once()
    activity_runtime.event_publisher.publish.assert_awaited()


@pytest.mark.asyncio
async def test_execute_step_is_idempotent(activity_runtime: ActivityRuntime) -> None:
    wf_input = _wf_input()
    ctx = MagicMock(spec=WorkflowActivityContext)
    step_input = StepActivityInput(
        task_id=wf_input.task_id,
        session_id=wf_input.session_id,
        user_id=wf_input.user_id,
        engine="auto",
        step_name="plan",
    )

    with patch(
        "workflows.activities.task_activities._step_exists",
        new=AsyncMock(return_value=True),
    ):
        result = await execute_step(ctx, step_input)

    assert result.created is False
    assert result.step_name == "plan"
    activity_runtime.event_publisher.publish.assert_not_awaited()
    activity_runtime.dapr_state.merge_task_runtime_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_initialize_task_skips_when_already_running(
    activity_runtime: ActivityRuntime,
) -> None:
    wf_input = _wf_input()
    ctx = MagicMock(spec=WorkflowActivityContext)

    mock_repo = AsyncMock()
    mock_repo.get_task.return_value = _task_record(wf_input, status=TaskStatus.RUNNING.value)

    with patch("workflows.activities.task_activities.TaskRepository", return_value=mock_repo):
        result = await initialize_task(ctx, wf_input)

    assert result.status == "running"
    mock_repo.update_task_status.assert_not_awaited()
    activity_runtime.event_publisher.publish.assert_not_awaited()


def _finalize_input(wf_input: TaskWorkflowInput, *, report: str | None = None) -> FinalizeTaskInput:
    return FinalizeTaskInput(
        task_id=wf_input.task_id,
        session_id=wf_input.session_id,
        user_id=wf_input.user_id,
        engine=wf_input.engine_requested,
        report=report,
    )


@pytest.mark.asyncio
async def test_finalize_task_skips_when_already_succeeded(
    activity_runtime: ActivityRuntime,
) -> None:
    wf_input = _wf_input()
    ctx = MagicMock(spec=WorkflowActivityContext)

    mock_repo = AsyncMock()
    record = _task_record(wf_input, status=TaskStatus.SUCCEEDED.value)
    record.report = "existing report"
    mock_repo.get_task.return_value = record

    with patch("workflows.activities.task_activities.TaskRepository", return_value=mock_repo):
        result = await finalize_task(ctx, _finalize_input(wf_input))

    assert result.report == "existing report"
    mock_repo.update_task_status.assert_not_awaited()
    activity_runtime.event_publisher.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_delayed_step_skips_sleep_when_step_exists(activity_runtime: ActivityRuntime) -> None:
    wf_input = _wf_input()
    ctx = MagicMock(spec=WorkflowActivityContext)
    step_input = DelayedStepInput(
        task_id=wf_input.task_id,
        session_id=wf_input.session_id,
        user_id=wf_input.user_id,
        engine="auto",
        delay_seconds=30.0,
    )

    with (
        patch(
            "workflows.activities.task_activities._step_exists",
            new=AsyncMock(return_value=True),
        ),
        patch("workflows.activities.task_activities.asyncio.sleep", new=AsyncMock()) as sleep_mock,
    ):
        result = await delayed_step(ctx, step_input)

    assert result.skipped is True
    sleep_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_mark_task_failed_from_paused(activity_runtime: ActivityRuntime) -> None:
    wf_input = _wf_input()
    ctx = MagicMock(spec=WorkflowActivityContext)
    failure_input = TaskFailureInput(task_id=wf_input.task_id, error="boom")

    mock_repo = AsyncMock()
    mock_repo.get_task.return_value = _task_record(wf_input, status=TaskStatus.PAUSED.value)
    mock_repo.update_task_status = AsyncMock()

    with patch("workflows.activities.task_activities.TaskRepository", return_value=mock_repo):
        result = await mark_task_failed(ctx, failure_input)

    assert result["status"] == TaskStatus.FAILED.value
    assert mock_repo.update_task_status.await_count == 2


@pytest.mark.asyncio
async def test_finalize_task_writes_report(activity_runtime: ActivityRuntime) -> None:
    wf_input = _wf_input()
    ctx = MagicMock(spec=WorkflowActivityContext)

    mock_repo = AsyncMock()
    mock_repo.get_task.return_value = _task_record(wf_input, status=TaskStatus.RUNNING.value)
    mock_repo.update_task_status = AsyncMock()

    with patch("workflows.activities.task_activities.TaskRepository", return_value=mock_repo):
        result = await finalize_task(ctx, _finalize_input(wf_input))

    assert result.status == "succeeded"
    assert str(wf_input.task_id) in result.report


@pytest.mark.asyncio
async def test_finalize_task_uses_real_report_when_provided(
    activity_runtime: ActivityRuntime,
) -> None:
    wf_input = _wf_input()
    ctx = MagicMock(spec=WorkflowActivityContext)

    mock_repo = AsyncMock()
    mock_repo.get_task.return_value = _task_record(wf_input, status=TaskStatus.RUNNING.value)
    mock_repo.update_task_status = AsyncMock()

    with patch("workflows.activities.task_activities.TaskRepository", return_value=mock_repo):
        result = await finalize_task(ctx, _finalize_input(wf_input, report="# Real Report"))

    assert result.report == "# Real Report"


@pytest.mark.asyncio
async def test_run_langgraph_graph_executes_full_graph_and_publishes_node_events(
    activity_runtime: ActivityRuntime,
) -> None:
    wf_input = _wf_input()
    ctx = MagicMock(spec=WorkflowActivityContext)
    step_input = LangGraphStepInput(
        task_id=wf_input.task_id,
        session_id=wf_input.session_id,
        user_id=wf_input.user_id,
        user_query=wf_input.user_query,
        engine="langgraph",
        thread_id=str(wf_input.task_id),
    )

    def _structured_handler(_messages: list[ChatMessage], schema: type[BaseModel]) -> BaseModel:
        if schema is PlanOutput:
            return PlanOutput(assigned_roles=["writer"], subtasks={})
        if schema is WriterSummary:
            return WriterSummary(title="T", summary="S", markdown="# T\n\nS")
        msg = f"unexpected schema: {schema}"
        raise AssertionError(msg)

    activity_runtime.llm_client = FakeLLMClient(structured_handler=_structured_handler)

    mock_repo = AsyncMock()
    mock_repo.record_step.return_value = object()

    with (
        patch("workflows.activities.task_activities.TaskRepository", return_value=mock_repo),
        patch(
            "workflows.activities.task_activities._step_exists",
            new=AsyncMock(return_value=False),
        ),
    ):
        result = await run_langgraph_graph(ctx, step_input)

    assert result.report is not None
    assert "T" in result.report
    assert activity_runtime.event_publisher.publish.await_count >= 4
    assert mock_repo.record_step.await_count >= 4
