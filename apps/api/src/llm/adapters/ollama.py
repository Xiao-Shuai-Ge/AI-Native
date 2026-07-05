"""Ollama LLM adapter using OpenAI-compatible endpoint."""

from __future__ import annotations

from llm.openai_compatible import OpenAICompatibleClient
from llm.protocol import LLMCapabilities


def create_ollama_client(
    *,
    base_url: str,
    model: str,
    extra_body: dict[str, object] | None = None,
) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(
        provider="ollama",
        model=model,
        base_url=base_url,
        api_key=None,
        capabilities=LLMCapabilities(
            supports_streaming=False,
            supports_tools=True,
            supports_structured_output=True,
            max_context_tokens=32768,
        ),
        extra_body=extra_body,
    )
