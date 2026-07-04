"""Task orchestration Dapr Workflow definition."""

from __future__ import annotations

import logging
from collections.abc import Generator
from typing import Any

from dapr.ext.workflow import DaprWorkflowContext

from orchestration.models import EngineChoice
from workflows.activities.task_activities import (
    delayed_step,
    execute_step,
    finalize_task,
    initialize_task,
    mark_task_failed,
    run_langgraph_graph,
)
from workflows.constraints import (
    EXECUTE_STEP_RETRY,
    FINALIZE_RETRY,
    INITIALIZE_RETRY,
    LANGGRAPH_STEP_RETRY,
    MARK_FAILED_RETRY,
    delayed_step_retry,
)
from workflows.models import (
    STUB_STEPS,
    TASK_WORKFLOW_NAME,
    DelayedStepInput,
    FinalizeTaskInput,
    LangGraphStepInput,
    StepActivityInput,
    TaskFailureInput,
    TaskWorkflowInput,
)

logger = logging.getLogger(__name__)


def task_orchestration(
    ctx: DaprWorkflowContext,
    wf_input: TaskWorkflowInput,
) -> Generator[Any, Any, None]:
    """Deterministic workflow orchestration; all I/O happens in Activities."""
    try:
        yield ctx.call_activity(
            initialize_task,
            input=wf_input,
            retry_policy=INITIALIZE_RETRY,
        )

        report: str | None = None

        if wf_input.engine_requested == EngineChoice.LANGGRAPH.value:
            langgraph_input = LangGraphStepInput(
                task_id=wf_input.task_id,
                session_id=wf_input.session_id,
                user_id=wf_input.user_id,
                user_query=wf_input.user_query,
                engine=wf_input.engine_requested,
                thread_id=wf_input.thread_id,
            )
            langgraph_result = yield ctx.call_activity(
                run_langgraph_graph,
                input=langgraph_input,
                retry_policy=LANGGRAPH_STEP_RETRY,
            )
            report = langgraph_result.report
        else:
            # `auto`/`crewai` engines are not yet implemented; keep the stub
            # step sequence so Day 1-4 behavior and tests stay unaffected.
            for step_name in STUB_STEPS:
                step_input = StepActivityInput(
                    task_id=wf_input.task_id,
                    session_id=wf_input.session_id,
                    user_id=wf_input.user_id,
                    engine=wf_input.engine_requested,
                    step_name=step_name,
                )
                yield ctx.call_activity(
                    execute_step,
                    input=step_input,
                    retry_policy=EXECUTE_STEP_RETRY,
                )

        if wf_input.delay_seconds > 0:
            delay_input = DelayedStepInput(
                task_id=wf_input.task_id,
                session_id=wf_input.session_id,
                user_id=wf_input.user_id,
                engine=wf_input.engine_requested,
                delay_seconds=wf_input.delay_seconds,
            )
            yield ctx.call_activity(
                delayed_step,
                input=delay_input,
                retry_policy=delayed_step_retry(wf_input.delay_seconds),
            )

        finalize_input = FinalizeTaskInput(
            task_id=wf_input.task_id,
            session_id=wf_input.session_id,
            user_id=wf_input.user_id,
            engine=wf_input.engine_requested,
            report=report,
        )
        yield ctx.call_activity(
            finalize_task,
            input=finalize_input,
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
            input=failure_input,
            retry_policy=MARK_FAILED_RETRY,
        )
        raise


task_orchestration.__dict__["_dapr_alternate_name"] = TASK_WORKFLOW_NAME
