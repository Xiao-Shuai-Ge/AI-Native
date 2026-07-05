"""Dapr State helpers for task runtime snapshots."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from persistence.dapr_client import DaprHttpClient


def runtime_state_key(task_id: UUID) -> str:
    return f"task:{task_id}:runtime"


class DaprStateStore:
    def __init__(self, client: DaprHttpClient) -> None:
        self._client = client
        self._merge_locks: dict[UUID, asyncio.Lock] = {}

    def _merge_lock(self, task_id: UUID) -> asyncio.Lock:
        lock = self._merge_locks.get(task_id)
        if lock is None:
            lock = asyncio.Lock()
            self._merge_locks[task_id] = lock
        return lock

    async def save_task_runtime_state(self, task_id: UUID, snapshot: dict[str, Any]) -> None:
        await self._client.save_state(runtime_state_key(task_id), snapshot)

    async def merge_task_runtime_state(self, task_id: UUID, patch: dict[str, Any]) -> None:
        async with self._merge_lock(task_id):
            existing = await self.get_task_runtime_state(task_id)
            merged = {**(existing or {}), **patch}
            await self.save_task_runtime_state(task_id, merged)

    async def get_task_runtime_state(self, task_id: UUID) -> dict[str, Any] | None:
        return await self._client.get_state(runtime_state_key(task_id))

    async def delete_task_runtime_state(self, task_id: UUID) -> None:
        await self._client.delete_state(runtime_state_key(task_id))
