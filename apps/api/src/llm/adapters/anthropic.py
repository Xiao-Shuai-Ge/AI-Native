"""Anthropic Claude LLM adapter."""

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

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicClient:
    """Adapter for Anthropic Messages API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._http_client = http_client
        self._owns_client = http_client is None
        self._provider_info = LLMProviderInfo(
            provider="anthropic",
            model=model,
            capabilities=LLMCapabilities(
                supports_streaming=False,
                supports_tools=False,
                supports_structured_output=True,
                max_context_tokens=200000,
            ),
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

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        timeout: float,
    ) -> ChatResponse:
        body = self._build_request_body(messages)
        payload = await self._post_messages(body, timeout=timeout)
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
        body = self._build_request_body(structured_messages)
        payload = await self._post_messages(body, timeout=timeout)
        response = self._parse_chat_response(payload)
        return self._parse_structured_content(response.content, schema)

    def _build_request_body(self, messages: list[ChatMessage]) -> dict[str, Any]:
        system_parts: list[str] = []
        anthropic_messages: list[dict[str, str]] = []
        for message in messages:
            if message.role == ChatRole.SYSTEM:
                system_parts.append(message.content)
                continue
            role = "assistant" if message.role == ChatRole.ASSISTANT else "user"
            anthropic_messages.append({"role": role, "content": message.content})

        body: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 4096,
            "messages": anthropic_messages,
        }
        if system_parts:
            body["system"] = "\n\n".join(system_parts)
        return body

    async def _post_messages(self, body: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        client = await self._get_client()
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        }
        try:
            response = await client.post(
                ANTHROPIC_API_URL,
                headers=headers,
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
        content_blocks = payload.get("content")
        if not isinstance(content_blocks, list):
            raise LLMUnavailableError("LLM provider returned invalid content blocks")

        text_parts: list[str] = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    text_parts.append(text)

        if not text_parts:
            raise LLMUnavailableError("LLM provider returned empty content")

        usage_payload = payload.get("usage")
        usage: TokenUsage | None = None
        if isinstance(usage_payload, dict):
            input_tokens = usage_payload.get("input_tokens")
            output_tokens = usage_payload.get("output_tokens")
            total_tokens = None
            if isinstance(input_tokens, int) and isinstance(output_tokens, int):
                total_tokens = input_tokens + output_tokens
            usage = TokenUsage(
                prompt_tokens=input_tokens if isinstance(input_tokens, int) else None,
                completion_tokens=output_tokens if isinstance(output_tokens, int) else None,
                total_tokens=total_tokens,
            )

        model = payload.get("model")
        stop_reason = payload.get("stop_reason")
        return ChatResponse(
            content="\n".join(text_parts),
            model=model if isinstance(model, str) else self._model,
            usage=usage,
            finish_reason=stop_reason if isinstance(stop_reason, str) else None,
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
