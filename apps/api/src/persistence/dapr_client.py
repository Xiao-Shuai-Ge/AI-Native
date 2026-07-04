"""Async HTTP client for Dapr sidecar APIs."""

from __future__ import annotations

import json
from typing import Any

import httpx


class DaprHttpClient:
    def __init__(
        self,
        *,
        http_port: int = 3500,
        state_store: str = "statestore",
        pubsub_name: str = "pubsub",
        base_url: str | None = None,
    ) -> None:
        self._state_store = state_store
        self._pubsub_name = pubsub_name
        self._base_url = base_url or f"http://127.0.0.1:{http_port}"
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=10.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def healthz(self) -> bool:
        response = await self._client.get("/v1.0/healthz")
        return response.status_code == 204

    async def save_state(self, key: str, value: dict[str, Any]) -> None:
        payload = [{"key": key, "value": value}]
        response = await self._client.post(
            f"/v1.0/state/{self._state_store}",
            json=payload,
        )
        response.raise_for_status()

    async def get_state(self, key: str) -> dict[str, Any] | None:
        response = await self._client.get(f"/v1.0/state/{self._state_store}/{key}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        if not response.content:
            return None
        data = response.json()
        if isinstance(data, dict):
            return data
        return None

    async def delete_state(self, key: str) -> None:
        response = await self._client.delete(f"/v1.0/state/{self._state_store}/{key}")
        if response.status_code not in (200, 204, 404):
            response.raise_for_status()

    async def publish_event(self, topic: str, data: dict[str, Any]) -> None:
        response = await self._client.post(
            f"/v1.0/publish/{self._pubsub_name}/{topic}",
            content=json.dumps(data),
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()

    async def save_blob(self, key: str, data: bytes) -> None:
        payload = [{"key": key, "value": data.decode("utf-8")}]
        response = await self._client.post(
            f"/v1.0/state/{self._state_store}",
            json=payload,
        )
        response.raise_for_status()

    async def get_blob(self, key: str) -> bytes | None:
        response = await self._client.get(f"/v1.0/state/{self._state_store}/{key}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        if not response.content:
            return None
        text = response.text
        return text.encode("utf-8")
