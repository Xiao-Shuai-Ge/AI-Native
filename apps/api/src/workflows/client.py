"""API-side Dapr Workflow scheduling client."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from dapr.ext.workflow import DaprWorkflowClient

from workflows.models import TaskWorkflowInput
from workflows.task_workflow import task_orchestration

logger = logging.getLogger(__name__)


class WorkflowScheduler:
    """Wraps the sync DaprWorkflowClient for use from async FastAPI handlers."""

    def __init__(
        self,
        *,
        grpc_host: str | None = None,
        grpc_port: int = 50001,
        max_workers: int = 4,
    ) -> None:
        self._client = DaprWorkflowClient(host=grpc_host, port=str(grpc_port))
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="wf-client")

    def _schedule_task_sync(self, wf_input: TaskWorkflowInput) -> str:
        payload = wf_input.model_dump(mode="json")
        return self._client.schedule_new_workflow(
            task_orchestration,
            input=payload,
            instance_id=wf_input.workflow_id,
        )

    async def schedule_task(self, wf_input: TaskWorkflowInput) -> str:
        loop = asyncio.get_running_loop()
        instance_id = await loop.run_in_executor(self._executor, self._schedule_task_sync, wf_input)
        logger.info(
            "scheduled workflow",
            extra={"task_id": str(wf_input.task_id), "workflow_id": wf_input.workflow_id},
        )
        return instance_id

    def _pause_task_sync(self, workflow_id: str) -> None:
        self._client.pause_workflow(workflow_id)

    async def pause_task(self, workflow_id: str) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            self._executor,
            self._pause_task_sync,
            workflow_id,
        )
        logger.info("paused workflow", extra={"workflow_id": workflow_id})

    def _resume_task_sync(self, workflow_id: str) -> None:
        self._client.resume_workflow(workflow_id)

    async def resume_task(self, workflow_id: str) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            self._executor,
            self._resume_task_sync,
            workflow_id,
        )
        logger.info("resumed workflow", extra={"workflow_id": workflow_id})

    def _get_runtime_status_sync(self, workflow_id: str) -> str | None:
        state = self._client.get_workflow_state(workflow_id, fetch_payloads=False)
        if state is None:
            return None
        return state.runtime_status.name

    async def get_runtime_status(self, workflow_id: str) -> str | None:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            self._get_runtime_status_sync,
            workflow_id,
        )

    def close(self) -> None:
        self._client.close()  # type: ignore[no-untyped-call]
        self._executor.shutdown(wait=False, cancel_futures=True)
