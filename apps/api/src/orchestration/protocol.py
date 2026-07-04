"""Orchestration engine protocol."""

from typing import Protocol

from orchestration.models import TaskRequest, TaskResult


class OrchestrationEngine(Protocol):
    async def run(self, request: TaskRequest) -> TaskResult: ...

    async def resume(self, task_id: str) -> TaskResult: ...
