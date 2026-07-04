"""Task lifecycle activities executed by the Dapr Workflow worker."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from dapr.ext.workflow import WorkflowActivityContext
from sqlalchemy import select

from events.schemas import AgentTaskEvent
from orchestration.langgraph_engine.engine import LangGraphEngine
from orchestration.models import EngineChoice, TaskRequest, TaskState, TaskStatus
from persistence.checkpointer import DaprCheckpointSaver
from persistence.idempotency import step_idempotency_key
from persistence.models import TaskStepRecord
from persistence.repository import TaskRepository
from workflows.constraints import (
    ACTIVITY_TIMEOUTS,
    delayed_step_timeout,
)
from workflows.models import (
    DELAYED_PROBE_STEP,
    ActivityStepResult,
    DelayedStepInput,
    DelayedStepResult,
    FinalizeTaskInput,
    FinalizeTaskResult,
    InitializeTaskResult,
    LangGraphStepInput,
    LangGraphStepResult,
    StepActivityInput,
    TaskFailureInput,
    TaskWorkflowInput,
)
from workflows.sync_runtime import get_activity_llm_client, get_activity_runtime

logger = logging.getLogger(__name__)


async def _publish_event(
    *,
    task_id: UUID,
    engine: str,
    step: str,
    status: str,
    detail: str,
) -> None:
    runtime = get_activity_runtime()
    event = AgentTaskEvent(
        task_id=task_id,
        engine=engine,
        step=step,
        status=status,
        timestamp=datetime.now(tz=UTC),
        detail=detail,
    )
    try:
        await runtime.event_publisher.publish(event)
    except Exception as exc:
        logger.warning(
            "failed to publish agent task event",
            extra={"task_id": str(task_id), "step": step, "error": str(exc)},
        )


async def _update_runtime_state(
    task_id: UUID,
    status: TaskStatus,
    *,
    current_step: str,
    report: str | None = None,
) -> None:
    runtime = get_activity_runtime()
    snapshot: dict[str, object] = {
        "task_id": str(task_id),
        "status": status.value,
        "current_step": current_step,
        "updated_at": datetime.now(tz=UTC).isoformat(),
    }
    if report is not None:
        snapshot["report"] = report
    try:
        await runtime.dapr_state.merge_task_runtime_state(task_id, snapshot)
    except Exception as exc:
        logger.warning(
            "failed to save dapr runtime state",
            extra={"task_id": str(task_id), "error": str(exc)},
        )


async def _step_exists(task_id: UUID, idempotency_key: str) -> bool:
    runtime = get_activity_runtime()
    async with runtime.session_factory() as session:
        result = await session.execute(
            select(TaskStepRecord).where(TaskStepRecord.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none() is not None


async def _initialize_task_impl(wf_input: TaskWorkflowInput) -> InitializeTaskResult:
    runtime = get_activity_runtime()
    task_id = wf_input.task_id
    engine = EngineChoice(wf_input.engine_requested)

    async with runtime.session_factory() as session:
        repo = TaskRepository(session)
        task = await repo.get_task(task_id)
        if task is None:
            msg = f"task not found: {task_id}"
            raise ValueError(msg)
        current = TaskStatus(task.status)
        if current != TaskStatus.QUEUED:
            logger.info(
                "initialize_task skipped, task already started",
                extra={"task_id": str(task_id), "status": current.value},
            )
            return InitializeTaskResult()
        await repo.update_task_status(task_id, TaskStatus.RUNNING, engine_selected=engine)
        await session.commit()

    await _publish_event(
        task_id=task_id,
        engine=engine.value,
        step="task",
        status=TaskStatus.RUNNING.value,
        detail="task started",
    )
    await _update_runtime_state(task_id, TaskStatus.RUNNING, current_step="plan")
    return InitializeTaskResult()


async def initialize_task(
    _ctx: WorkflowActivityContext,
    wf_input: TaskWorkflowInput,
) -> InitializeTaskResult:
    timeout = ACTIVITY_TIMEOUTS["initialize_task"].total_seconds()
    return await asyncio.wait_for(_initialize_task_impl(wf_input), timeout=timeout)


async def _execute_step_impl(step_input: StepActivityInput) -> ActivityStepResult:
    runtime = get_activity_runtime()
    task_id = step_input.task_id
    step_name = step_input.step_name
    idempotency_key = step_idempotency_key(task_id, step_name)

    if await _step_exists(task_id, idempotency_key):
        logger.info(
            "step already recorded, skipping side effects",
            extra={"task_id": str(task_id), "step_name": step_name},
        )
        return ActivityStepResult(step_name=step_name, created=False)

    await _publish_event(
        task_id=task_id,
        engine=step_input.engine,
        step=step_name,
        status=step_input.step_status,
        detail=f"{step_name} finished",
    )

    created = False
    async with runtime.session_factory() as session:
        repo = TaskRepository(session)
        record = await repo.record_step(
            task_id=task_id,
            step_name=step_name,
            status=step_input.step_status,
            output_json={"detail": f"{step_name} stub output"},
            idempotency_key=idempotency_key,
        )
        await session.commit()
        created = record is not None

    await _update_runtime_state(task_id, TaskStatus.RUNNING, current_step=step_name)
    return ActivityStepResult(step_name=step_name, created=created)


async def execute_step(
    _ctx: WorkflowActivityContext,
    step_input: StepActivityInput,
) -> ActivityStepResult:
    timeout = ACTIVITY_TIMEOUTS["execute_step"].total_seconds()
    return await asyncio.wait_for(_execute_step_impl(step_input), timeout=timeout)


async def _record_langgraph_node(task_id: UUID, step_name: str, status: str) -> None:
    runtime = get_activity_runtime()
    idempotency_key = step_idempotency_key(task_id, step_name, "langgraph")
    if await _step_exists(task_id, idempotency_key):
        return
    try:
        async with runtime.session_factory() as session:
            repo = TaskRepository(session)
            await repo.record_step(
                task_id=task_id,
                step_name=step_name,
                status=status,
                output_json={"detail": f"langgraph node {step_name} {status}"},
                idempotency_key=idempotency_key,
            )
            await session.commit()
    except Exception as exc:
        logger.warning(
            "failed to record langgraph node step",
            extra={"task_id": str(task_id), "step": step_name, "error": str(exc)},
        )


async def _run_langgraph_graph_impl(step_input: LangGraphStepInput) -> LangGraphStepResult:
    runtime = get_activity_runtime()
    task_id = step_input.task_id

    async def on_node_complete(step_name: str, status: str, _state: TaskState) -> None:
        await _publish_event(
            task_id=task_id,
            engine=step_input.engine,
            step=step_name,
            status=status,
            detail=f"langgraph node {step_name} {status}",
        )
        await _record_langgraph_node(task_id, step_name, status)
        await _update_runtime_state(task_id, TaskStatus.RUNNING, current_step=step_name)

    async def persist_result(state: TaskState) -> None:
        await _update_runtime_state(
            task_id,
            TaskStatus.RUNNING,
            current_step="persist_result",
            report=state.report,
        )

    if runtime.dapr_client is None:
        msg = "activity runtime is missing a dapr_client for LangGraph checkpointing"
        raise RuntimeError(msg)

    checkpointer = DaprCheckpointSaver(runtime.dapr_client)
    llm = runtime.llm_client or get_activity_llm_client()
    engine = LangGraphEngine(
        llm=llm,
        checkpointer=checkpointer,
        on_node_complete=on_node_complete,
        persist_result=persist_result,
    )

    existing_checkpoint = await checkpointer.aget_tuple(
        {"configurable": {"thread_id": step_input.thread_id}}
    )
    if existing_checkpoint is not None:
        result = await engine.resume(step_input.thread_id)
    else:
        request = TaskRequest(
            task_id=task_id,
            session_id=step_input.session_id,
            user_id=step_input.user_id,
            user_query=step_input.user_query,
            engine=EngineChoice(step_input.engine),
        )
        result = await engine.run(request)

    return LangGraphStepResult(report=result.report, errors=result.errors)


async def run_langgraph_graph(
    _ctx: WorkflowActivityContext,
    step_input: LangGraphStepInput,
) -> LangGraphStepResult:
    timeout = ACTIVITY_TIMEOUTS["run_langgraph_graph"].total_seconds()
    return await asyncio.wait_for(_run_langgraph_graph_impl(step_input), timeout=timeout)


async def _delayed_step_impl(step_input: DelayedStepInput) -> DelayedStepResult:
    task_id = step_input.task_id
    idempotency_key = step_idempotency_key(task_id, DELAYED_PROBE_STEP)

    if await _step_exists(task_id, idempotency_key):
        logger.info(
            "delayed_probe already recorded, skipping sleep",
            extra={"task_id": str(task_id)},
        )
        return DelayedStepResult(created=False, skipped=True)

    if step_input.delay_seconds > 0:
        await asyncio.sleep(step_input.delay_seconds)

    runtime = get_activity_runtime()
    await _publish_event(
        task_id=task_id,
        engine=step_input.engine,
        step=DELAYED_PROBE_STEP,
        status="completed",
        detail=f"delayed probe after {step_input.delay_seconds}s",
    )

    created = False
    async with runtime.session_factory() as session:
        repo = TaskRepository(session)
        record = await repo.record_step(
            task_id=task_id,
            step_name=DELAYED_PROBE_STEP,
            status="completed",
            output_json={"delay_seconds": step_input.delay_seconds},
            idempotency_key=idempotency_key,
        )
        await session.commit()
        created = record is not None

    await _update_runtime_state(task_id, TaskStatus.RUNNING, current_step=DELAYED_PROBE_STEP)
    return DelayedStepResult(created=created, skipped=False)


async def delayed_step(
    _ctx: WorkflowActivityContext,
    step_input: DelayedStepInput,
) -> DelayedStepResult:
    timeout = delayed_step_timeout(step_input.delay_seconds).total_seconds()
    return await asyncio.wait_for(_delayed_step_impl(step_input), timeout=timeout)


async def _finalize_task_impl(finalize_input: FinalizeTaskInput) -> FinalizeTaskResult:
    runtime = get_activity_runtime()
    task_id = finalize_input.task_id
    engine = finalize_input.engine
    report = finalize_input.report or f"Stub report for task {task_id}"

    async with runtime.session_factory() as session:
        repo = TaskRepository(session)
        task = await repo.get_task(task_id)
        if task is None:
            msg = f"task not found: {task_id}"
            raise ValueError(msg)
        current = TaskStatus(task.status)
        if current == TaskStatus.SUCCEEDED:
            existing_report = task.report or report
            logger.info(
                "finalize_task skipped, task already succeeded",
                extra={"task_id": str(task_id)},
            )
            return FinalizeTaskResult(report=existing_report)
        await repo.update_task_status(task_id, TaskStatus.SUCCEEDED, report=report)
        await session.commit()

    await _publish_event(
        task_id=task_id,
        engine=engine,
        step="task",
        status=TaskStatus.SUCCEEDED.value,
        detail="task succeeded",
    )
    await _update_runtime_state(
        task_id,
        TaskStatus.SUCCEEDED,
        current_step="done",
        report=report,
    )
    return FinalizeTaskResult(report=report)


async def finalize_task(
    _ctx: WorkflowActivityContext,
    finalize_input: FinalizeTaskInput,
) -> FinalizeTaskResult:
    timeout = ACTIVITY_TIMEOUTS["finalize_task"].total_seconds()
    return await asyncio.wait_for(_finalize_task_impl(finalize_input), timeout=timeout)


async def _mark_task_failed_impl(failure_input: TaskFailureInput) -> dict[str, str]:
    runtime = get_activity_runtime()
    task_id = failure_input.task_id

    async with runtime.session_factory() as session:
        repo = TaskRepository(session)
        task = await repo.get_task(task_id)
        if task is None:
            return {"status": "missing"}
        current = TaskStatus(task.status)
        if current in (TaskStatus.SUCCEEDED, TaskStatus.CANCELLED, TaskStatus.FAILED):
            return {"status": current.value}
        if current in (TaskStatus.QUEUED, TaskStatus.PAUSED):
            await repo.update_task_status(task_id, TaskStatus.RUNNING)
        await repo.update_task_status(task_id, TaskStatus.FAILED)
        await session.commit()

    await _publish_event(
        task_id=task_id,
        engine="unknown",
        step="task",
        status=TaskStatus.FAILED.value,
        detail=failure_input.error,
    )
    await _update_runtime_state(task_id, TaskStatus.FAILED, current_step="failed")
    return {"status": TaskStatus.FAILED.value}


async def mark_task_failed(
    _ctx: WorkflowActivityContext,
    failure_input: TaskFailureInput,
) -> dict[str, str]:
    timeout = ACTIVITY_TIMEOUTS["mark_task_failed"].total_seconds()
    return await asyncio.wait_for(_mark_task_failed_impl(failure_input), timeout=timeout)
