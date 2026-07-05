"""Shared adapter for DeepSeek, Ollama and OpenAI compatible endpoints.

Delegates the actual HTTP call to `litellm.acompletion` (see
`llm/litellm_support.py`) so tool-calling is parsed the same, litellm-
normalized way across every provider instead of hand-rolled per-provider
JSON parsing. The `model` string is prefixed with `openai/` so litellm
targets the given `base_url` as a generic OpenAI-compatible endpoint,
matching this adapter's previous direct-httpx behavior byte-for-byte.
"""

from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from llm.errors import LLMParseError
from llm.litellm_support import call_litellm, parse_litellm_response
from llm.protocol import (
    ChatMessage,
    ChatResponse,
    ChatRole,
    LLMCapabilities,
    LLMProviderInfo,
    ToolDefinition,
)

logger = logging.getLogger(__name__)

StructuredT = TypeVar("StructuredT", bound=BaseModel)


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
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._base_url = base_url
        self._api_key = api_key
        self._capabilities = capabilities
        self._extra_body = extra_body or {}
        self._provider_info = LLMProviderInfo(
            provider=provider,
            model=model,
            capabilities=capabilities,
        )

    @property
    def provider_info(self) -> LLMProviderInfo:
        return self._provider_info

    async def aclose(self) -> None:
        """No-op: litellm manages its own connection pooling internally."""

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        timeout: float,
        tools: list[ToolDefinition] | None = None,
    ) -> ChatResponse:
        response = await call_litellm(
            model=f"openai/{self._model}",
            messages=messages,
            timeout=timeout,
            api_key=self._api_key or "not-needed",
            base_url=self._base_url,
            tools=tools,
            extra_body=self._extra_body or None,
        )
        return parse_litellm_response(response, fallback_model=self._model)

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
        response = await call_litellm(
            model=f"openai/{self._model}",
            messages=structured_messages,
            timeout=timeout,
            api_key=self._api_key or "not-needed",
            base_url=self._base_url,
            extra_body={**self._extra_body, "response_format": {"type": "json_object"}},
        )
        parsed = parse_litellm_response(response, fallback_model=self._model)
        return self._parse_structured_content(parsed.content, schema)

    def _parse_structured_content(self, content: str, schema: type[StructuredT]) -> StructuredT:
        try:
            return schema.model_validate_json(content)
        except ValidationError as exc:
            logger.warning("structured output validation failed", extra={"error": str(exc)})
            raise LLMParseError("Structured output failed schema validation") from exc
        except ValueError as exc:
            logger.warning("structured output json decode failed", extra={"error": str(exc)})
            raise LLMParseError("Structured output is not valid JSON") from exc
