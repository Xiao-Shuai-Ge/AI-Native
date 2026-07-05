"""Shared litellm request/response conversion and error mapping.

`llm/openai_compatible.py` and `llm/adapters/anthropic.py` both delegate their
actual HTTP calls to `litellm.acompletion` so all four providers (DeepSeek,
Ollama, OpenAI, Anthropic) get real, litellm-normalized `tool_calls` parsing
instead of hand-rolled per-provider JSON parsing. This module holds the
conversion helpers shared by both adapters so the `LLMClient` contract
(`chat`/`chat_structured`/`provider_info`) stays provider-agnostic per
AGENTS.md section 2 ("所有供应商必须走同一个 LLMClient 接口").
"""

from __future__ import annotations

import json
import logging
from typing import Any

import litellm
from litellm.exceptions import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
    Timeout,
)

from llm.errors import LLMConfigurationError, LLMUnavailableError
from llm.protocol import ChatMessage, ChatResponse, TokenUsage, ToolCall, ToolDefinition

logger = logging.getLogger(__name__)


def to_litellm_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for message in messages:
        entry: dict[str, Any] = {"role": message.role.value, "content": message.content}
        if message.tool_call_id:
            entry["tool_call_id"] = message.tool_call_id
        if message.tool_calls:
            entry["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
                for call in message.tool_calls
            ]
        converted.append(entry)
    return converted


def to_litellm_tools(tools: list[ToolDefinition] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters or {"type": "object", "properties": {}},
            },
        }
        for tool in tools
    ]


async def call_litellm(
    *,
    model: str,
    messages: list[ChatMessage],
    timeout: float,
    api_key: str | None = None,
    base_url: str | None = None,
    tools: list[ToolDefinition] | None = None,
    extra_body: dict[str, Any] | None = None,
) -> Any:
    """Calls `litellm.acompletion`, mapping litellm exceptions to `llm.errors`."""
    litellm_tools = to_litellm_tools(tools)
    try:
        return await litellm.acompletion(
            model=model,
            messages=to_litellm_messages(messages),
            timeout=timeout,
            api_key=api_key,
            base_url=base_url,
            tools=litellm_tools,
            tool_choice="auto" if litellm_tools else None,
            **(extra_body or {}),
        )
    except Timeout as exc:
        raise LLMUnavailableError("LLM request timed out at transport layer") from exc
    except AuthenticationError as exc:
        raise LLMConfigurationError(f"LLM provider rejected credentials: {exc}") from exc
    except RateLimitError as exc:
        raise LLMUnavailableError(f"LLM provider returned HTTP 429: {exc}") from exc
    except APIConnectionError as exc:
        raise LLMUnavailableError(f"LLM request failed at transport layer: {exc}") from exc
    except BadRequestError as exc:
        raise LLMUnavailableError(f"LLM provider returned HTTP 400: {exc}") from exc
    except APIError as exc:
        status = getattr(exc, "status_code", "unknown")
        raise LLMUnavailableError(f"LLM provider returned HTTP {status}: {exc}") from exc


def parse_litellm_response(response: Any, *, fallback_model: str) -> ChatResponse:
    choices = getattr(response, "choices", None)
    if not choices:
        raise LLMUnavailableError("LLM provider returned no choices")

    message = choices[0].message
    content = message.content or ""

    tool_calls: list[ToolCall] | None = None
    raw_tool_calls = getattr(message, "tool_calls", None)
    if raw_tool_calls:
        tool_calls = []
        for raw_call in raw_tool_calls:
            arguments_raw = getattr(raw_call.function, "arguments", "") or "{}"
            try:
                arguments = json.loads(arguments_raw)
            except (TypeError, ValueError):
                logger.warning(
                    "tool call arguments were not valid JSON", extra={"raw": arguments_raw}
                )
                arguments = {}
            tool_calls.append(
                ToolCall(id=raw_call.id, name=raw_call.function.name, arguments=arguments)
            )

    if not content and not tool_calls:
        raise LLMUnavailableError("LLM provider returned empty content")

    usage_payload = getattr(response, "usage", None)
    usage: TokenUsage | None = None
    if usage_payload is not None:
        usage = TokenUsage(
            prompt_tokens=getattr(usage_payload, "prompt_tokens", None),
            completion_tokens=getattr(usage_payload, "completion_tokens", None),
            total_tokens=getattr(usage_payload, "total_tokens", None),
        )

    model = getattr(response, "model", None)
    finish_reason = getattr(choices[0], "finish_reason", None)
    return ChatResponse(
        content=content,
        model=model if isinstance(model, str) else fallback_model,
        usage=usage,
        finish_reason=finish_reason if isinstance(finish_reason, str) else None,
        tool_calls=tool_calls,
    )
