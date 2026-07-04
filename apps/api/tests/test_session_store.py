"""Session store unit tests."""

from uuid import uuid4

import pytest
import redis.asyncio as aioredis

from persistence.session_store import SessionStore


@pytest.fixture
async def session_store() -> SessionStore:
    client = aioredis.from_url("redis://localhost:6379/15", encoding="utf-8", decode_responses=True)
    store = SessionStore(client, max_messages=3)
    yield store
    await client.flushdb()
    await store.aclose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_session_store_keeps_recent_messages(session_store: SessionStore) -> None:
    user_id = "test-user"
    session_id = uuid4()

    await session_store.append_message(user_id, session_id, role="user", content="first")
    await session_store.append_message(user_id, session_id, role="assistant", content="second")
    await session_store.append_message(user_id, session_id, role="user", content="third")
    await session_store.append_message(user_id, session_id, role="assistant", content="fourth")

    messages = await session_store.get_messages(user_id, session_id)
    assert len(messages) == 3
    assert messages[0]["content"] == "second"
    assert messages[-1]["content"] == "fourth"
