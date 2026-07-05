"""Anthropic Claude LLM adapter.

Delegates to `litellm.acompletion` (litellm auto-detects `claude-*` model
names as the Anthropic provider) so Anthropic gets the same litellm-
normalized `tool_calls` parsing as the other three providers instead of a
hand-rolled Anthropic Messages API tools translation.
"""

from __future__ import annotations

import json
import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from llm.errors import LLMParseError
from llm.litellm_support import call_litellm, parse_litellm_response
from llm.protocol import (
    ChatMessage,
    ChatResponse,
    ChatRole,
    LLMCapabilities,
    LLMProviderInfo,
    TokenUsage,
    ToolDefinition,
)

logger = logging.getLogger(__name__)

StructuredT = TypeVar("StructuredT", bound=BaseModel)


class AnthropicClient:
    """Adapter for the Anthropic Messages API, via litellm."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._provider_info = LLMProviderInfo(
            provider="anthropic",
            model=model,
            capabilities=LLMCapabilities(
                supports_streaming=False,
                supports_tools=True,
                supports_structured_output=True,
                max_context_tokens=200000,
            ),
        )
        self._last_usage: TokenUsage | None = None

    @property
    def provider_info(self) -> LLMProviderInfo:
        return self._provider_info

    @property
    def last_usage(self) -> TokenUsage | None:
        return self._last_usage

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
            model=self._model,
            messages=messages,
            timeout=timeout,
            api_key=self._api_key,
            tools=tools,
            extra_body={"max_tokens": self._max_tokens, "temperature": self._temperature},
        )
        parsed = parse_litellm_response(response, fallback_model=self._model)
        self._last_usage = parsed.usage
        return parsed

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
            model=self._model,
            messages=structured_messages,
            timeout=timeout,
            api_key=self._api_key,
            extra_body={"max_tokens": self._max_tokens, "temperature": self._temperature},
        )
        parsed = parse_litellm_response(response, fallback_model=self._model)
        self._last_usage = parsed.usage
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
