"""Dapr Workflow worker entrypoint."""

from __future__ import annotations

import logging
import signal
import sys
import threading

from dapr.ext.workflow import WorkflowRuntime

from api.config import get_settings
from observability import init_observability
from observability.metrics_server import start_metrics_server
from workflows.activities.task_activities import (
    delayed_step,
    execute_step,
    finalize_task,
    initialize_task,
    mark_task_failed,
    run_crewai_analyst,
    run_crewai_researcher,
    run_crewai_writer,
    run_langgraph_graph,
    select_engine,
)
from workflows.sync_runtime import init_activity_runtime, shutdown_activity_runtime_sync
from workflows.task_workflow import task_orchestration

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    settings = get_settings()
    init_observability(settings, "worker")
    start_metrics_server(settings.worker_metrics_port)


def build_workflow_runtime() -> WorkflowRuntime:
    settings = get_settings()
    runtime = WorkflowRuntime(port=str(settings.dapr_grpc_port))
    runtime.register_workflow(task_orchestration)
    runtime.register_activity(initialize_task)
    runtime.register_activity(execute_step)
    runtime.register_activity(delayed_step)
    runtime.register_activity(finalize_task)
    runtime.register_activity(mark_task_failed)
    runtime.register_activity(run_langgraph_graph)
    runtime.register_activity(select_engine)
    runtime.register_activity(run_crewai_researcher)
    runtime.register_activity(run_crewai_analyst)
    runtime.register_activity(run_crewai_writer)
    return runtime


def main() -> None:
    _configure_logging()
    settings = get_settings()
    init_activity_runtime(settings)
    runtime = build_workflow_runtime()

    stop_event = threading.Event()

    def _handle_signal(_signum: int, _frame: object) -> None:
        logger.info("shutdown signal received")
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info(
        "starting workflow worker",
        extra={"dapr_grpc_port": settings.dapr_grpc_port},
    )
    runtime.start()  # type: ignore[no-untyped-call]
    try:
        stop_event.wait()
    finally:
        logger.info("shutting down workflow worker")
        runtime.shutdown()  # type: ignore[no-untyped-call]
        shutdown_activity_runtime_sync()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("workflow worker failed")
        sys.exit(1)
