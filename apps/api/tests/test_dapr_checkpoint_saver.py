"""DaprCheckpointSaver unit tests."""

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from persistence.checkpointer import DaprCheckpointSaver
from persistence.dapr_client import DaprHttpClient


@pytest.fixture
def mock_client() -> DaprHttpClient:
    client = DaprHttpClient(http_port=3500)
    client.get_state = AsyncMock(return_value=None)  # type: ignore[method-assign]
    client.get_blob = AsyncMock(return_value=None)  # type: ignore[method-assign]
    client.save_state = AsyncMock()  # type: ignore[method-assign]
    client.save_blob = AsyncMock()  # type: ignore[method-assign]
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
    mock_client.get_state = AsyncMock(return_value={"latest": "1"})  # type: ignore[method-assign]
    mock_client.get_blob = AsyncMock(  # type: ignore[method-assign]
        return_value=json.dumps(payload).encode("utf-8")
    )

    saver = DaprCheckpointSaver(mock_client)
    item = await saver.aget_tuple({"configurable": {"thread_id": thread_id}})

    assert item is not None
    assert item.checkpoint["id"] == "1"
