"""DaprStateStore unit tests."""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from persistence.dapr_client import DaprHttpClient
from persistence.dapr_state import DaprStateStore


@pytest.fixture
def mock_client() -> DaprHttpClient:
    client = DaprHttpClient(http_port=3500)
    client.get_state = AsyncMock(return_value=None)  # type: ignore[method-assign]
    client.save_state = AsyncMock()  # type: ignore[method-assign]
    return client


@pytest.mark.asyncio
async def test_merge_task_runtime_state_preserves_existing_fields(
    mock_client: DaprHttpClient,
) -> None:
    task_id = uuid4()
    mock_client.get_state = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "user_query": "Explain Dapr",
            "session_context": [{"role": "user", "content": "hi"}],
            "user_preferences": {"language": "zh-CN"},
        }
    )
    store = DaprStateStore(mock_client)

    await store.merge_task_runtime_state(
        task_id,
        {"status": "running", "current_step": "plan"},
    )

    mock_client.save_state.assert_awaited_once()
    saved = mock_client.save_state.await_args.args[1]
    assert saved["user_query"] == "Explain Dapr"
    assert saved["session_context"] == [{"role": "user", "content": "hi"}]
    assert saved["user_preferences"] == {"language": "zh-CN"}
    assert saved["status"] == "running"
    assert saved["current_step"] == "plan"


@pytest.mark.asyncio
async def test_merge_task_runtime_state_serializes_concurrent_updates(
    mock_client: DaprHttpClient,
) -> None:
    task_id = uuid4()
    stored: dict[str, object] = {}

    async def get_state_side_effect(_key: str) -> dict[str, object] | None:
        await asyncio.sleep(0)
        return dict(stored) if stored else None

    async def save_state_side_effect(_key: str, value: dict[str, object]) -> None:
        await asyncio.sleep(0)
        stored.clear()
        stored.update(value)

    mock_client.get_state = AsyncMock(side_effect=get_state_side_effect)  # type: ignore[method-assign]
    mock_client.save_state = AsyncMock(side_effect=save_state_side_effect)  # type: ignore[method-assign]
    store = DaprStateStore(mock_client)

    await asyncio.gather(
        store.merge_task_runtime_state(task_id, {"token_usage": {"prompt_tokens": 10}}),
        store.merge_task_runtime_state(task_id, {"current_step": "researcher"}),
    )

    assert stored["token_usage"] == {"prompt_tokens": 10}
    assert stored["current_step"] == "researcher"
