"""Redis-backed short-term session conversation context."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis

from api.config import Settings

SESSION_KEY_PREFIX = "session"
DEFAULT_MAX_MESSAGES = 10


def session_key(user_id: str, session_id: UUID) -> str:
    return f"{SESSION_KEY_PREFIX}:{user_id}:{session_id}"


class SessionStore:
    def __init__(
        self,
        redis_client: aioredis.Redis,
        *,
        max_messages: int = DEFAULT_MAX_MESSAGES,
    ) -> None:
        self._redis = redis_client
        self._max_messages = max_messages

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        max_messages: int = DEFAULT_MAX_MESSAGES,
    ) -> SessionStore:
        client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        return cls(client, max_messages=max_messages)

    async def aclose(self) -> None:
        await self._redis.aclose()

    async def get_messages(self, user_id: str, session_id: UUID) -> list[dict[str, Any]]:
        raw = await self._redis.get(session_key(user_id, session_id))
        if not raw:
            return []
        data = json.loads(raw)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    async def append_message(
        self,
        user_id: str,
        session_id: UUID,
        *,
        role: str,
        content: str,
    ) -> list[dict[str, Any]]:
        messages = await self.get_messages(user_id, session_id)
        messages.append({"role": role, "content": content})
        trimmed = messages[-self._max_messages :]
        await self._redis.set(session_key(user_id, session_id), json.dumps(trimmed))
        return trimmed
