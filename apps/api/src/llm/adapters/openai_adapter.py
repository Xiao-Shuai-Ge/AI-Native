"""OpenAI LLM adapter."""

from __future__ import annotations

from llm.openai_compatible import OpenAICompatibleClient
from llm.protocol import LLMCapabilities


def create_openai_client(
    *,
    api_key: str,
    base_url: str,
    model: str,
    extra_body: dict[str, object] | None = None,
) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(
        provider="openai",
        model=model,
        base_url=base_url,
        api_key=api_key,
        capabilities=LLMCapabilities(
            supports_streaming=False,
            supports_tools=True,
            supports_structured_output=True,
            max_context_tokens=128000,
        ),
        extra_body=extra_body,
    )
