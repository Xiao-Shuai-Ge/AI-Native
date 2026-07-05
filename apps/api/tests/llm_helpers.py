"""Shared LLM test helpers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from llm.protocol import ChatMessage, ChatRole


def openai_chat_payload(content: str, *, model: str = "test-model") -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 24,
            "total_tokens": 36,
        },
    }


def anthropic_chat_payload(content: str, *, model: str = "claude-test") -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": content}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 20},
    }


def user_message(text: str) -> list[ChatMessage]:
    return [ChatMessage(role=ChatRole.USER, content=text)]


def fake_litellm_response(
    content: str = "",
    *,
    model: str = "test-model",
    tool_calls: list[dict[str, Any]] | None = None,
    finish_reason: str = "stop",
    prompt_tokens: int = 12,
    completion_tokens: int = 24,
) -> SimpleNamespace:
    """Builds a minimal object shaped like `litellm.types.utils.ModelResponse`.

    Only the attributes read by `llm.litellm_support.parse_litellm_response`
    are populated (`choices[0].message.content/.tool_calls`,
    `choices[0].finish_reason`, `usage.*`, `model`).
    """
    message_tool_calls = None
    if tool_calls:
        message_tool_calls = [
            SimpleNamespace(
                id=call["id"],
                function=SimpleNamespace(name=call["name"], arguments=call["arguments"]),
            )
            for call in tool_calls
        ]
    message = SimpleNamespace(content=content, tool_calls=message_tool_calls)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    return SimpleNamespace(choices=[choice], usage=usage, model=model)
