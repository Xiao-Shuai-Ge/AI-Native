"""Shared LLM test helpers."""

from __future__ import annotations

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
