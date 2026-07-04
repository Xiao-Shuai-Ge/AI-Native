"""Task orchestration Dapr Workflow definition."""

from __future__ import annotations

import logging
from collections.abc import Generator
from typing import Any

from dapr.ext.workflow import DaprWorkflowContext

from workflows.activities.task_activities import (
    delayed_step,
    execute_step,
    finalize_task,
    initialize_task,
    mark_task_failed,
)
from workflows.constraints import (
    EXECUTE_STEP_RETRY,
    FINALIZE_RETRY,
    INITIALIZE_RETRY,
    MARK_FAILED_RETRY,
    delayed_step_retry,
)
from workflows.models import (
    STUB_STEPS,
    TASK_WORKFLOW_NAME,
    DelayedStepInput,
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

        yield ctx.call_activity(
            finalize_task,
            input=wf_input,
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
