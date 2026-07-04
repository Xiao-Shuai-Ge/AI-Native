"""OpenAI-compatible chat completions client."""

from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from llm.errors import LLMParseError, LLMUnavailableError
from llm.protocol import (
    ChatMessage,
    ChatResponse,
    ChatRole,
    LLMCapabilities,
    LLMProviderInfo,
    TokenUsage,
)

logger = logging.getLogger(__name__)

StructuredT = TypeVar("StructuredT", bound=BaseModel)


def _chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _to_openai_messages(messages: list[ChatMessage]) -> list[dict[str, str]]:
    return [{"role": message.role.value, "content": message.content} for message in messages]


class OpenAICompatibleClient:
    """Shared adapter for DeepSeek, Ollama and OpenAI compatible endpoints."""

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        base_url: str,
        api_key: str | None,
        capabilities: LLMCapabilities,
        http_client: httpx.AsyncClient | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._base_url = base_url
        self._api_key = api_key
        self._capabilities = capabilities
        self._http_client = http_client
        self._owns_client = http_client is None
        self._extra_body = extra_body or {}
        self._provider_info = LLMProviderInfo(
            provider=provider,
            model=model,
            capabilities=capabilities,
        )

    @property
    def provider_info(self) -> LLMProviderInfo:
        return self._provider_info

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient()
        return self._http_client

    async def aclose(self) -> None:
        if self._owns_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        timeout: float,
    ) -> ChatResponse:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": _to_openai_messages(messages),
            **self._extra_body,
        }
        payload = await self._post_chat_completions(body, timeout=timeout)
        return self._parse_chat_response(payload)

    async def chat_structured(
        self,
        messages: list[ChatMessage],
        schema: type[StructuredT],
        *,
        timeout: float,
    ) -> StructuredT:
        schema_hint = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        structured_messages = list(messages)
        structured_messages.insert(
            0,
            ChatMessage(
                role=ChatRole.SYSTEM,
                content=(
                    "Respond with valid JSON only. Do not include markdown fences "
                    f"or commentary. The JSON must match this schema: {schema_hint}"
                ),
            ),
        )
        body: dict[str, Any] = {
            "model": self._model,
            "messages": _to_openai_messages(structured_messages),
            "response_format": {"type": "json_object"},
            **self._extra_body,
        }
        payload = await self._post_chat_completions(body, timeout=timeout)
        response = self._parse_chat_response(payload)
        return self._parse_structured_content(response.content, schema)

    async def _post_chat_completions(
        self,
        body: dict[str, Any],
        *,
        timeout: float,
    ) -> dict[str, Any]:
        client = await self._get_client()
        url = _chat_completions_url(self._base_url)
        try:
            response = await client.post(
                url,
                headers=self._headers(),
                json=body,
                timeout=timeout,
            )
        except httpx.TimeoutException as exc:
            raise LLMUnavailableError("LLM request timed out at transport layer") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailableError("LLM request failed at transport layer") from exc

        if response.status_code >= 400:
            raise LLMUnavailableError(
                f"LLM provider returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise LLMUnavailableError("LLM provider returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise LLMUnavailableError("LLM provider returned unexpected payload")
        return payload

    def _parse_chat_response(self, payload: dict[str, Any]) -> ChatResponse:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMUnavailableError("LLM provider returned no choices")

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise LLMUnavailableError("LLM provider returned invalid choice payload")

        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise LLMUnavailableError("LLM provider returned invalid message payload")

        content = message.get("content")
        if not isinstance(content, str):
            raise LLMUnavailableError("LLM provider returned empty content")

        usage_payload = payload.get("usage")
        usage: TokenUsage | None = None
        if isinstance(usage_payload, dict):
            usage = TokenUsage(
                prompt_tokens=usage_payload.get("prompt_tokens"),
                completion_tokens=usage_payload.get("completion_tokens"),
                total_tokens=usage_payload.get("total_tokens"),
            )

        model = payload.get("model")
        finish_reason = first_choice.get("finish_reason")
        return ChatResponse(
            content=content,
            model=model if isinstance(model, str) else self._model,
            usage=usage,
            finish_reason=finish_reason if isinstance(finish_reason, str) else None,
        )

    def _parse_structured_content(self, content: str, schema: type[StructuredT]) -> StructuredT:
        try:
            return schema.model_validate_json(content)
        except ValidationError as exc:
            logger.warning("structured output validation failed", extra={"error": str(exc)})
            raise LLMParseError("Structured output failed schema validation") from exc
        except ValueError as exc:
            logger.warning("structured output json decode failed", extra={"error": str(exc)})
            raise LLMParseError("Structured output is not valid JSON") from exc
