"""LangGraph checkpoint saver backed by Dapr State API."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
)

from persistence.dapr_client import DaprHttpClient

logger = logging.getLogger(__name__)

_MAX_WRITE_RETRIES = 3


def checkpoint_key(thread_id: str, checkpoint_id: str) -> str:
    return f"lg:checkpoint:{thread_id}:{checkpoint_id}"


def checkpoint_index_key(thread_id: str) -> str:
    return f"lg:checkpoint-index:{thread_id}"


def writes_key(thread_id: str, checkpoint_id: str) -> str:
    return f"lg:writes:{thread_id}:{checkpoint_id}"


class DaprCheckpointSaver(BaseCheckpointSaver[str]):
    def __init__(self, client: DaprHttpClient) -> None:
        super().__init__()
        self._client = client

    async def aget_tuple(self, config: dict[str, Any]) -> CheckpointTuple | None:
        thread_id = self._thread_id(config)
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id")
        if checkpoint_id:
            raw = await self._client.get_blob(checkpoint_key(thread_id, checkpoint_id))
            if raw is None:
                return None
            payload = json.loads(raw.decode("utf-8"))
            pending_writes = await self._load_writes(thread_id, checkpoint_id)
            return CheckpointTuple(
                config=config,
                checkpoint=payload["checkpoint"],
                metadata=payload.get("metadata", {}),
                parent_config=payload.get("parent_config"),
                pending_writes=pending_writes,
            )

        index_raw = await self._client.get_state(checkpoint_index_key(thread_id))
        if not index_raw:
            return None
        latest_id = index_raw.get("latest")
        if not isinstance(latest_id, str):
            return None
        latest_config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": latest_id,
            }
        }
        return await self.aget_tuple(latest_config)

    async def _load_writes(self, thread_id: str, checkpoint_id: str) -> list[tuple[str, str, Any]]:
        raw, _etag = await self._client.get_blob_entry(writes_key(thread_id, checkpoint_id))
        if raw is None:
            return []
        entries = json.loads(raw.decode("utf-8"))
        return [(entry["task_id"], entry["channel"], entry["value"]) for entry in entries]

    def _merge_pending_writes(
        self,
        existing: list[dict[str, Any]],
        writes: Sequence[tuple[str, Any]],
        *,
        task_id: str,
        task_path: str,
    ) -> list[dict[str, Any]]:
        merged = list(existing)
        existing_index = {(entry["task_id"], entry["idx"]): i for i, entry in enumerate(merged)}

        for idx, (channel, value) in enumerate(writes):
            write_idx = WRITES_IDX_MAP.get(channel, idx)
            dedup_key = (task_id, write_idx)
            entry = {
                "task_id": task_id,
                "idx": write_idx,
                "channel": channel,
                "value": value,
                "task_path": task_path,
            }
            if write_idx >= 0 and dedup_key in existing_index:
                continue
            merged.append(entry)
            existing_index[dedup_key] = len(merged) - 1

        return merged

    async def aput(
        self,
        config: dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, str | int | float],
    ) -> dict[str, Any]:
        thread_id = self._thread_id(config)
        checkpoint_id = get_checkpoint_id(config) or checkpoint["id"]
        payload = {
            "checkpoint": checkpoint,
            "metadata": metadata,
            "parent_config": config,
        }
        await self._client.save_blob(
            checkpoint_key(thread_id, str(checkpoint_id)),
            json.dumps(payload, default=str).encode("utf-8"),
        )
        await self._client.save_state(
            checkpoint_index_key(thread_id),
            {"latest": str(checkpoint_id)},
        )
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": str(checkpoint_id),
            }
        }

    async def aput_writes(
        self,
        config: dict[str, Any],
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = self._thread_id(config)
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id")
        if not checkpoint_id:
            msg = "checkpoint_id is required to store pending writes"
            raise ValueError(msg)

        key = writes_key(thread_id, checkpoint_id)
        for attempt in range(_MAX_WRITE_RETRIES):
            raw, etag = await self._client.get_blob_entry(key)
            existing: list[dict[str, Any]] = json.loads(raw.decode("utf-8")) if raw else []
            merged = self._merge_pending_writes(
                existing,
                writes,
                task_id=task_id,
                task_path=task_path,
            )
            saved = await self._client.save_blob_cas(
                key,
                json.dumps(merged, default=str).encode("utf-8"),
                etag=etag,
            )
            if saved:
                return
            logger.warning(
                "pending writes CAS conflict, retrying",
                extra={
                    "thread_id": thread_id,
                    "checkpoint_id": checkpoint_id,
                    "attempt": attempt + 1,
                },
            )

        msg = (
            f"failed to store pending writes for thread_id={thread_id} "
            f"checkpoint_id={checkpoint_id} after {_MAX_WRITE_RETRIES} attempts"
        )
        raise RuntimeError(msg)

    async def alist(
        self,
        config: dict[str, Any] | None,
        *,
        filter: dict[str, Any] | None = None,
        before: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        if config is None:
            return
        thread_id = self._thread_id(config)
        index_raw = await self._client.get_state(checkpoint_index_key(thread_id))
        if not index_raw:
            return
        latest_id = index_raw.get("latest")
        if not isinstance(latest_id, str):
            return
        item = await self.aget_tuple(
            {"configurable": {"thread_id": thread_id, "checkpoint_id": latest_id}}
        )
        if item is not None:
            yield item

    def get_tuple(self, config: dict[str, Any]) -> CheckpointTuple | None:
        raise NotImplementedError("use async methods")

    def put(
        self,
        config: dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, str | int | float],
    ) -> dict[str, Any]:
        raise NotImplementedError("use async methods")

    def list(
        self,
        config: dict[str, Any] | None,
        *,
        filter: dict[str, Any] | None = None,
        before: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        raise NotImplementedError("use async methods")

    def _thread_id(self, config: dict[str, Any]) -> str:
        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id")
        if not isinstance(thread_id, str) or not thread_id:
            msg = "thread_id is required in checkpoint config"
            raise ValueError(msg)
        return thread_id

    def get_next_version(self, current: str | None, channel: Sequence[str]) -> str:
        if current is None:
            return "1"
        try:
            return str(int(current) + 1)
        except ValueError:
            return "1"
