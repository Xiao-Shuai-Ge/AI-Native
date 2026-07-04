"""DaprCheckpointSaver unit tests."""

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from persistence.checkpointer import DaprCheckpointSaver, checkpoint_key, writes_key
from persistence.dapr_client import DaprHttpClient


@pytest.fixture
def mock_client() -> DaprHttpClient:
    client = DaprHttpClient(http_port=3500)
    client.get_state = AsyncMock(return_value=None)  # type: ignore[method-assign]
    client.get_blob = AsyncMock(return_value=None)  # type: ignore[method-assign]
    client.get_blob_entry = AsyncMock(return_value=(None, None))  # type: ignore[method-assign]
    client.save_state = AsyncMock()  # type: ignore[method-assign]
    client.save_blob = AsyncMock()  # type: ignore[method-assign]
    client.save_blob_cas = AsyncMock(return_value=True)  # type: ignore[method-assign]
    return client


@pytest.mark.asyncio
async def test_aput_saves_checkpoint_and_index(mock_client: DaprHttpClient) -> None:
    saver = DaprCheckpointSaver(mock_client)
    thread_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id, "checkpoint_id": "1"}}
    checkpoint = {"v": 1, "id": "1", "ts": "2026-01-01T00:00:00+00:00", "channel_values": {}}
    metadata = {"source": "test", "step": 1, "parents": {}}

    result = await saver.aput(config, checkpoint, metadata, {})

    assert result["configurable"]["thread_id"] == thread_id
    mock_client.save_blob.assert_awaited_once()
    mock_client.save_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_aget_tuple_reads_latest_checkpoint(mock_client: DaprHttpClient) -> None:
    thread_id = str(uuid4())
    payload = {
        "checkpoint": {"v": 1, "id": "1", "ts": "2026-01-01T00:00:00+00:00", "channel_values": {}},
        "metadata": {"source": "test", "step": 1, "parents": {}},
        "parent_config": {"configurable": {"thread_id": thread_id, "checkpoint_id": "1"}},
    }
    stored_blobs = {checkpoint_key(thread_id, "1"): json.dumps(payload).encode("utf-8")}

    async def _get_blob(key: str) -> bytes | None:
        return stored_blobs.get(key)

    mock_client.get_state = AsyncMock(return_value={"latest": "1"})  # type: ignore[method-assign]
    mock_client.get_blob = AsyncMock(side_effect=_get_blob)  # type: ignore[method-assign]

    saver = DaprCheckpointSaver(mock_client)
    item = await saver.aget_tuple({"configurable": {"thread_id": thread_id}})

    assert item is not None
    assert item.checkpoint["id"] == "1"
    assert item.pending_writes == []


@pytest.mark.asyncio
async def test_aput_writes_then_aget_tuple_returns_pending_writes(
    mock_client: DaprHttpClient,
) -> None:
    thread_id = str(uuid4())
    checkpoint_id = "1"
    payload = {
        "checkpoint": {"v": 1, "id": "1", "ts": "2026-01-01T00:00:00+00:00", "channel_values": {}},
        "metadata": {"source": "test", "step": 1, "parents": {}},
        "parent_config": None,
    }
    stored_blobs: dict[str, bytes] = {
        checkpoint_key(thread_id, checkpoint_id): json.dumps(payload).encode("utf-8")
    }
    blob_etags: dict[str, str] = {}

    async def _get_blob_entry(key: str) -> tuple[bytes | None, str | None]:
        data = stored_blobs.get(key)
        if data is None:
            return None, None
        return data, blob_etags.get(key)

    async def _save_blob_cas(key: str, data: bytes, *, etag: str | None) -> bool:
        current_etag = blob_etags.get(key)
        if etag is not None and current_etag is not None and etag != current_etag:
            return False
        if etag is None and key in stored_blobs:
            return False
        stored_blobs[key] = data
        blob_etags[key] = f"etag-{len(blob_etags) + 1}"
        return True

    mock_client.get_state = AsyncMock(return_value={"latest": checkpoint_id})  # type: ignore[method-assign]
    mock_client.get_blob = AsyncMock(side_effect=lambda key: stored_blobs.get(key))  # type: ignore[method-assign]
    mock_client.get_blob_entry = AsyncMock(side_effect=_get_blob_entry)  # type: ignore[method-assign]
    mock_client.save_blob_cas = AsyncMock(side_effect=_save_blob_cas)  # type: ignore[method-assign]

    saver = DaprCheckpointSaver(mock_client)
    config = {"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}}
    await saver.aput_writes(config, [("plan", {"foo": "bar"})], task_id="task-1")

    item = await saver.aget_tuple({"configurable": {"thread_id": thread_id}})

    assert item is not None
    assert item.pending_writes == [("task-1", "plan", {"foo": "bar"})]


@pytest.mark.asyncio
async def test_aput_writes_retries_on_cas_conflict(mock_client: DaprHttpClient) -> None:
    thread_id = str(uuid4())
    checkpoint_id = "1"
    key = writes_key(thread_id, checkpoint_id)
    stored_blobs: dict[str, bytes] = {}
    blob_etags: dict[str, str] = {}
    cas_attempts = 0

    async def _get_blob_entry(blob_key: str) -> tuple[bytes | None, str | None]:
        data = stored_blobs.get(blob_key)
        if data is None:
            return None, None
        return data, blob_etags.get(blob_key)

    async def _save_blob_cas(blob_key: str, data: bytes, *, etag: str | None) -> bool:
        nonlocal cas_attempts
        cas_attempts += 1
        if cas_attempts == 1:
            stored_blobs[blob_key] = json.dumps([{"task_id": "other", "idx": 0}]).encode("utf-8")
            blob_etags[blob_key] = "stale-etag"
            return False
        stored_blobs[blob_key] = data
        blob_etags[blob_key] = f"etag-{cas_attempts}"
        return True

    mock_client.get_blob_entry = AsyncMock(side_effect=_get_blob_entry)  # type: ignore[method-assign]
    mock_client.save_blob_cas = AsyncMock(side_effect=_save_blob_cas)  # type: ignore[method-assign]

    saver = DaprCheckpointSaver(mock_client)
    config = {"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}}
    await saver.aput_writes(config, [("plan", {"foo": "bar"})], task_id="task-1")

    assert cas_attempts == 2
    merged = json.loads(stored_blobs[key].decode("utf-8"))
    assert any(entry.get("channel") == "plan" for entry in merged)
