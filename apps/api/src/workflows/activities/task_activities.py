"""Task lifecycle activities executed by the Dapr Workflow worker."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TypeVar
from uuid import UUID

from dapr.ext.workflow import WorkflowActivityContext
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from api.services.settings_service import SettingsService
from events.schemas import AgentTaskEvent
from llm.factory import create_llm_client
from orchestration.crewai_engine.roles_runner import run_analyst, run_researcher, run_writer
from orchestration.engine_router import EngineRouter
from orchestration.langgraph_engine.engine import LangGraphEngine
from orchestration.models import EngineChoice, TaskRequest, TaskState, TaskStatus
from persistence.checkpointer import DaprCheckpointSaver
from persistence.dapr_client import DaprHttpClient
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
    CrewAIAnalystInput,
    CrewAIAnalystResult,
    CrewAIResearcherInput,
    CrewAIResearcherResult,
    CrewAIWriterInput,
    CrewAIWriterResult,
    DelayedStepInput,
    DelayedStepResult,
    FinalizeTaskInput,
    FinalizeTaskResult,
    InitializeTaskResult,
    LangGraphStepInput,
    LangGraphStepResult,
    SelectEngineInput,
    SelectEngineResult,
    StepActivityInput,
    TaskFailureInput,
    TaskWorkflowInput,
)
from workflows.sync_runtime import ActivityRuntime, get_activity_runtime, run_async

logger = logging.getLogger(__name__)

TModel = TypeVar("TModel", bound=BaseModel)


def _coerce_input(model: type[TModel], value: TModel | dict[str, object]) -> TModel:
    if isinstance(value, model):
        return value
    return model.model_validate(value)


def _activity_result(model: BaseModel) -> dict[str, object]:
    return model.model_dump(mode="json")


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


def _require_dapr_client(runtime: ActivityRuntime) -> DaprHttpClient:
    if runtime.dapr_client is None:
        msg = "activity runtime is missing a dapr_client"
        raise RuntimeError(msg)
    return runtime.dapr_client


async def _step_exists(task_id: UUID, idempotency_key: str) -> bool:
    runtime = get_activity_runtime()
    async with runtime.session_factory() as session:
        result = await session.execute(
            select(TaskStepRecord).where(TaskStepRecord.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none() is not None


async def _load_recorded_step_output[TModel: BaseModel](
    idempotency_key: str,
    result_type: type[TModel],
) -> TModel | None:
    runtime = get_activity_runtime()
    async with runtime.session_factory() as session:
        existing = await session.execute(
            select(TaskStepRecord).where(TaskStepRecord.idempotency_key == idempotency_key)
        )
        record = existing.scalar_one_or_none()
        if record is not None and record.output_json is not None:
            return result_type.model_validate(record.output_json)
    return None


async def _commit_crewai_step[TModel: BaseModel](
    *,
    task_id: UUID,
    step_name: str,
    engine: str,
    idempotency_key: str,
    result: TModel,
    result_type: type[TModel],
    report: str | None = None,
) -> TModel:
    """Persist CrewAI role output and return the canonical stored result."""
    cached = await _load_recorded_step_output(idempotency_key, result_type)
    if cached is not None:
        logger.info(
            "crewai step already recorded, skipping side effects",
            extra={"task_id": str(task_id), "step_name": step_name},
        )
        return cached

    runtime = get_activity_runtime()
    async with runtime.session_factory() as session:
        repo = TaskRepository(session)
        record = await repo.record_step(
            task_id=task_id,
            step_name=step_name,
            status="completed",
            output_json=result.model_dump(),
            idempotency_key=idempotency_key,
        )
        if record is not None:
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
            else:
                await _publish_event(
                    task_id=task_id,
                    engine=engine,
                    step=step_name,
                    status="completed",
                    detail=f"{step_name} finished",
                )
                await _update_runtime_state(
                    task_id,
                    TaskStatus.RUNNING,
                    current_step=step_name,
                    report=report,
                )
                return result

    cached = await _load_recorded_step_output(idempotency_key, result_type)
    if cached is not None:
        logger.info(
            "crewai step persisted by peer, using stored output",
            extra={"task_id": str(task_id), "step_name": step_name},
        )
        return cached

    msg = f"failed to persist or load crewai step output: {step_name}"
    raise RuntimeError(msg)


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
        # Manual engine choices override auto-routing immediately; `auto` is
        # left unresolved here and settled by `select_engine` so a manual
        # choice can never be silently overwritten by the router.
        selected = None if engine == EngineChoice.AUTO else engine
        await repo.update_task_status(task_id, TaskStatus.RUNNING, engine_selected=selected)
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


def initialize_task(
    _ctx: WorkflowActivityContext,
    wf_input: TaskWorkflowInput | dict[str, object],
) -> dict[str, object]:
    parsed = _coerce_input(TaskWorkflowInput, wf_input)
    timeout = ACTIVITY_TIMEOUTS["initialize_task"].total_seconds()
    result = run_async(asyncio.wait_for(_initialize_task_impl(parsed), timeout=timeout))
    return _activity_result(result)


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


def execute_step(
    _ctx: WorkflowActivityContext,
    step_input: StepActivityInput | dict[str, object],
) -> dict[str, object]:
    parsed = _coerce_input(StepActivityInput, step_input)
    timeout = ACTIVITY_TIMEOUTS["execute_step"].total_seconds()
    result = run_async(asyncio.wait_for(_execute_step_impl(parsed), timeout=timeout))
    return _activity_result(result)


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
    settings_service = SettingsService(runtime.dapr_client, runtime.settings)
    runtime_settings = await settings_service.get_settings()
    role_registry = settings_service.role_registry_from_settings(runtime_settings)
    llm = create_llm_client(runtime.settings, runtime_llm=runtime_settings.llm)
    engine = LangGraphEngine(
        llm=llm,
        checkpointer=checkpointer,
        on_node_complete=on_node_complete,
        persist_result=persist_result,
        role_registry=role_registry,
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


def run_langgraph_graph(
    _ctx: WorkflowActivityContext,
    step_input: LangGraphStepInput | dict[str, object],
) -> dict[str, object]:
    parsed = _coerce_input(LangGraphStepInput, step_input)
    timeout = ACTIVITY_TIMEOUTS["run_langgraph_graph"].total_seconds()
    result = run_async(asyncio.wait_for(_run_langgraph_graph_impl(parsed), timeout=timeout))
    return _activity_result(result)


async def _select_engine_impl(step_input: SelectEngineInput) -> SelectEngineResult:
    runtime = get_activity_runtime()
    task_id = step_input.task_id

    settings_service = SettingsService(_require_dapr_client(runtime), runtime.settings)
    runtime_settings = await settings_service.get_settings()
    llm = create_llm_client(runtime.settings, runtime_llm=runtime_settings.llm)

    decision = await EngineRouter().select(
        step_input.user_query,
        llm=llm,
        task_id=str(task_id),
    )

    async with runtime.session_factory() as session:
        repo = TaskRepository(session)
        await repo.update_task_status(
            task_id,
            TaskStatus.RUNNING,
            engine_selected=decision.engine,
            engine_selection_reason=decision.reason,
        )
        await session.commit()

    await _publish_event(
        task_id=task_id,
        engine=decision.engine.value,
        step="select_engine",
        status="completed",
        detail=decision.reason,
    )
    return SelectEngineResult(
        engine_selected=decision.engine.value,
        reason=decision.reason,
        subtasks=decision.subtasks,
    )


def select_engine(
    _ctx: WorkflowActivityContext,
    step_input: SelectEngineInput | dict[str, object],
) -> dict[str, object]:
    parsed = _coerce_input(SelectEngineInput, step_input)
    timeout = ACTIVITY_TIMEOUTS["select_engine"].total_seconds()
    result = run_async(asyncio.wait_for(_select_engine_impl(parsed), timeout=timeout))
    return _activity_result(result)


async def _run_crewai_researcher_impl(
    step_input: CrewAIResearcherInput,
) -> CrewAIResearcherResult:
    runtime = get_activity_runtime()
    task_id = step_input.task_id
    step_name = "researcher"
    idempotency_key = step_idempotency_key(task_id, step_name, "crewai")

    cached = await _load_recorded_step_output(idempotency_key, CrewAIResearcherResult)
    if cached is not None:
        return cached

    settings_service = SettingsService(_require_dapr_client(runtime), runtime.settings)
    runtime_settings = await settings_service.get_settings()
    role_registry = settings_service.role_registry_from_settings(runtime_settings)
    llm = create_llm_client(runtime.settings, runtime_llm=runtime_settings.llm)

    notes_result = await run_researcher(
        step_input.user_query,
        task_id=task_id,
        llm=llm,
        subtask=step_input.subtask,
        role=role_registry.get("researcher"),
    )
    result = CrewAIResearcherResult(
        notes=list(notes_result.notes),
        sources=list(notes_result.sources),
    )
    return await _commit_crewai_step(
        task_id=task_id,
        step_name=step_name,
        engine=step_input.engine,
        idempotency_key=idempotency_key,
        result=result,
        result_type=CrewAIResearcherResult,
    )


def run_crewai_researcher(
    _ctx: WorkflowActivityContext,
    step_input: CrewAIResearcherInput | dict[str, object],
) -> dict[str, object]:
    parsed = _coerce_input(CrewAIResearcherInput, step_input)
    timeout = ACTIVITY_TIMEOUTS["run_crewai_researcher"].total_seconds()
    result = run_async(asyncio.wait_for(_run_crewai_researcher_impl(parsed), timeout=timeout))
    return _activity_result(result)


async def _run_crewai_analyst_impl(step_input: CrewAIAnalystInput) -> CrewAIAnalystResult:
    runtime = get_activity_runtime()
    task_id = step_input.task_id
    step_name = "analyst"
    idempotency_key = step_idempotency_key(task_id, step_name, "crewai")

    cached = await _load_recorded_step_output(idempotency_key, CrewAIAnalystResult)
    if cached is not None:
        return cached

    settings_service = SettingsService(_require_dapr_client(runtime), runtime.settings)
    runtime_settings = await settings_service.get_settings()
    role_registry = settings_service.role_registry_from_settings(runtime_settings)
    llm = create_llm_client(runtime.settings, runtime_llm=runtime_settings.llm)

    analysis_result = await run_analyst(
        step_input.user_query,
        task_id=task_id,
        llm=llm,
        research_notes=step_input.research_notes,
        subtask=step_input.subtask,
        role=role_registry.get("analyst"),
    )
    result = CrewAIAnalystResult(analysis=analysis_result.analysis)
    return await _commit_crewai_step(
        task_id=task_id,
        step_name=step_name,
        engine=step_input.engine,
        idempotency_key=idempotency_key,
        result=result,
        result_type=CrewAIAnalystResult,
    )


def run_crewai_analyst(
    _ctx: WorkflowActivityContext,
    step_input: CrewAIAnalystInput | dict[str, object],
) -> dict[str, object]:
    parsed = _coerce_input(CrewAIAnalystInput, step_input)
    timeout = ACTIVITY_TIMEOUTS["run_crewai_analyst"].total_seconds()
    result = run_async(asyncio.wait_for(_run_crewai_analyst_impl(parsed), timeout=timeout))
    return _activity_result(result)


async def _run_crewai_writer_impl(step_input: CrewAIWriterInput) -> CrewAIWriterResult:
    runtime = get_activity_runtime()
    task_id = step_input.task_id
    step_name = "writer"
    idempotency_key = step_idempotency_key(task_id, step_name, "crewai")

    cached = await _load_recorded_step_output(idempotency_key, CrewAIWriterResult)
    if cached is not None:
        return cached

    settings_service = SettingsService(_require_dapr_client(runtime), runtime.settings)
    runtime_settings = await settings_service.get_settings()
    role_registry = settings_service.role_registry_from_settings(runtime_settings)
    llm = create_llm_client(runtime.settings, runtime_llm=runtime_settings.llm)

    writer_result = await run_writer(
        step_input.user_query,
        task_id=task_id,
        llm=llm,
        research_notes=step_input.research_notes,
        analysis=step_input.analysis,
        subtask=step_input.subtask,
        role=role_registry.get("writer"),
    )
    result = CrewAIWriterResult(report=writer_result.markdown)
    return await _commit_crewai_step(
        task_id=task_id,
        step_name=step_name,
        engine=step_input.engine,
        idempotency_key=idempotency_key,
        result=result,
        result_type=CrewAIWriterResult,
        report=result.report,
    )


def run_crewai_writer(
    _ctx: WorkflowActivityContext,
    step_input: CrewAIWriterInput | dict[str, object],
) -> dict[str, object]:
    parsed = _coerce_input(CrewAIWriterInput, step_input)
    timeout = ACTIVITY_TIMEOUTS["run_crewai_writer"].total_seconds()
    result = run_async(asyncio.wait_for(_run_crewai_writer_impl(parsed), timeout=timeout))
    return _activity_result(result)


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


def delayed_step(
    _ctx: WorkflowActivityContext,
    step_input: DelayedStepInput | dict[str, object],
) -> dict[str, object]:
    parsed = _coerce_input(DelayedStepInput, step_input)
    timeout = delayed_step_timeout(parsed.delay_seconds).total_seconds()
    result = run_async(asyncio.wait_for(_delayed_step_impl(parsed), timeout=timeout))
    return _activity_result(result)


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


def finalize_task(
    _ctx: WorkflowActivityContext,
    finalize_input: FinalizeTaskInput | dict[str, object],
) -> dict[str, object]:
    parsed = _coerce_input(FinalizeTaskInput, finalize_input)
    timeout = ACTIVITY_TIMEOUTS["finalize_task"].total_seconds()
    result = run_async(asyncio.wait_for(_finalize_task_impl(parsed), timeout=timeout))
    return _activity_result(result)


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


def mark_task_failed(
    _ctx: WorkflowActivityContext,
    failure_input: TaskFailureInput | dict[str, object],
) -> dict[str, str]:
    parsed = _coerce_input(TaskFailureInput, failure_input)
    timeout = ACTIVITY_TIMEOUTS["mark_task_failed"].total_seconds()
    return run_async(asyncio.wait_for(_mark_task_failed_impl(parsed), timeout=timeout))
