"""Task orchestration Dapr Workflow definition."""

from __future__ import annotations

import logging
from collections.abc import Generator
from typing import Any

from dapr.ext.workflow import DaprWorkflowContext

from pydantic import BaseModel

from orchestration.models import EngineChoice
from workflows.activities.task_activities import (
    delayed_step,
    finalize_task,
    initialize_task,
    mark_task_failed,
    run_crewai_analyst,
    run_crewai_researcher,
    run_crewai_writer,
    run_langgraph_graph,
    select_engine,
)
from workflows.constraints import (
    CREWAI_STEP_RETRY,
    FINALIZE_RETRY,
    INITIALIZE_RETRY,
    LANGGRAPH_STEP_RETRY,
    MARK_FAILED_RETRY,
    SELECT_ENGINE_RETRY,
    delayed_step_retry,
)
from workflows.models import (
    TASK_WORKFLOW_NAME,
    CrewAIAnalystInput,
    CrewAIAnalystResult,
    CrewAIResearcherInput,
    CrewAIResearcherResult,
    CrewAIWriterInput,
    CrewAIWriterResult,
    DelayedStepInput,
    FinalizeTaskInput,
    LangGraphStepInput,
    LangGraphStepResult,
    SelectEngineInput,
    SelectEngineResult,
    TaskFailureInput,
    TaskWorkflowInput,
)

logger = logging.getLogger(__name__)


def _activity_payload(model: BaseModel) -> dict[str, object]:
    """Dapr serializes activity inputs as JSON; pass plain dicts from the workflow."""
    return model.model_dump(mode="json")


def task_orchestration(
    ctx: DaprWorkflowContext,
    wf_input: TaskWorkflowInput | dict[str, object],
) -> Generator[Any, Any, None]:
    """Deterministic workflow orchestration; all I/O happens in Activities."""
    if not isinstance(wf_input, TaskWorkflowInput):
        wf_input = TaskWorkflowInput.model_validate(wf_input)
    try:
        yield ctx.call_activity(
            initialize_task,
            input=_activity_payload(wf_input),
            retry_policy=INITIALIZE_RETRY,
        )

        resolved_engine = wf_input.engine_requested
        subtasks: dict[str, str] = {}

        if resolved_engine == EngineChoice.AUTO.value:
            select_input = SelectEngineInput(
                task_id=wf_input.task_id,
                session_id=wf_input.session_id,
                user_id=wf_input.user_id,
                user_query=wf_input.user_query,
            )
            select_result = yield ctx.call_activity(
                select_engine,
                input=_activity_payload(select_input),
                retry_policy=SELECT_ENGINE_RETRY,
            )
            # Dapr deserializes activity outputs as plain dicts inside the workflow.
            selection = SelectEngineResult.model_validate(select_result)
            resolved_engine = selection.engine_selected
            subtasks = selection.subtasks

        report: str | None = None

        if resolved_engine == EngineChoice.LANGGRAPH.value:
            langgraph_input = LangGraphStepInput(
                task_id=wf_input.task_id,
                session_id=wf_input.session_id,
                user_id=wf_input.user_id,
                user_query=wf_input.user_query,
                engine=resolved_engine,
                thread_id=wf_input.thread_id,
            )
            langgraph_result = yield ctx.call_activity(
                run_langgraph_graph,
                input=_activity_payload(langgraph_input),
                retry_policy=LANGGRAPH_STEP_RETRY,
            )
            parsed = LangGraphStepResult.model_validate(langgraph_result)
            report = parsed.report
        else:
            researcher_input = CrewAIResearcherInput(
                task_id=wf_input.task_id,
                session_id=wf_input.session_id,
                user_id=wf_input.user_id,
                user_query=wf_input.user_query,
                engine=resolved_engine,
                subtask=subtasks.get("researcher"),
            )
            researcher_result = yield ctx.call_activity(
                run_crewai_researcher,
                input=_activity_payload(researcher_input),
                retry_policy=CREWAI_STEP_RETRY,
            )
            researcher_parsed = CrewAIResearcherResult.model_validate(researcher_result)

            analyst_input = CrewAIAnalystInput(
                task_id=wf_input.task_id,
                session_id=wf_input.session_id,
                user_id=wf_input.user_id,
                user_query=wf_input.user_query,
                engine=resolved_engine,
                research_notes=researcher_parsed.notes,
                subtask=subtasks.get("analyst"),
            )
            analyst_result = yield ctx.call_activity(
                run_crewai_analyst,
                input=_activity_payload(analyst_input),
                retry_policy=CREWAI_STEP_RETRY,
            )
            analyst_parsed = CrewAIAnalystResult.model_validate(analyst_result)

            writer_input = CrewAIWriterInput(
                task_id=wf_input.task_id,
                session_id=wf_input.session_id,
                user_id=wf_input.user_id,
                user_query=wf_input.user_query,
                engine=resolved_engine,
                research_notes=researcher_parsed.notes,
                analysis=analyst_parsed.analysis,
            )
            writer_result = yield ctx.call_activity(
                run_crewai_writer,
                input=_activity_payload(writer_input),
                retry_policy=CREWAI_STEP_RETRY,
            )
            writer_parsed = CrewAIWriterResult.model_validate(writer_result)
            report = writer_parsed.report

        if wf_input.delay_seconds > 0:
            delay_input = DelayedStepInput(
                task_id=wf_input.task_id,
                session_id=wf_input.session_id,
                user_id=wf_input.user_id,
                engine=resolved_engine,
                delay_seconds=wf_input.delay_seconds,
            )
            yield ctx.call_activity(
                delayed_step,
                input=_activity_payload(delay_input),
                retry_policy=delayed_step_retry(wf_input.delay_seconds),
            )

        finalize_input = FinalizeTaskInput(
            task_id=wf_input.task_id,
            session_id=wf_input.session_id,
            user_id=wf_input.user_id,
            engine=resolved_engine,
            report=report,
        )
        yield ctx.call_activity(
            finalize_task,
            input=_activity_payload(finalize_input),
            retry_policy=FINALIZE_RETRY,
        )
    except Exception as exc:
        logger.exception(
            "task workflow failed",
            extra={"task_id": str(wf_input.task_id), "workflow_id": wf_input.workflow_id},
        )
        failure_input = TaskFailureInput(task_id=wf_input.task_id, error=str(exc))
        yield ctx.call_activity(
            mark_task_failed,
            input=_activity_payload(failure_input),
            retry_policy=MARK_FAILED_RETRY,
        )
        raise


task_orchestration.__dict__["_dapr_alternate_name"] = TASK_WORKFLOW_NAME
