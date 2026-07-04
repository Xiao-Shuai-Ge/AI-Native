"""Dapr State helpers for task runtime snapshots."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from persistence.dapr_client import DaprHttpClient


def runtime_state_key(task_id: UUID) -> str:
    return f"task:{task_id}:runtime"


class DaprStateStore:
    def __init__(self, client: DaprHttpClient) -> None:
        self._client = client

    async def save_task_runtime_state(self, task_id: UUID, snapshot: dict[str, Any]) -> None:
        await self._client.save_state(runtime_state_key(task_id), snapshot)

    async def get_task_runtime_state(self, task_id: UUID) -> dict[str, Any] | None:
        return await self._client.get_state(runtime_state_key(task_id))

    async def delete_task_runtime_state(self, task_id: UUID) -> None:
        await self._client.delete_state(runtime_state_key(task_id))
