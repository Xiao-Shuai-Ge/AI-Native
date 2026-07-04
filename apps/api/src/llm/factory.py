"""LLM client factory."""

from __future__ import annotations

from typing import Any

from api.config import Settings
from api.schemas.settings import LLMSettings
from llm.adapters.anthropic import AnthropicClient
from llm.adapters.deepseek import create_deepseek_client
from llm.adapters.ollama import create_ollama_client
from llm.adapters.openai_adapter import create_openai_client
from llm.errors import LLMConfigurationError
from llm.resilient import InnerClient, ResilientLLMClient


def _generation_params(runtime_llm: LLMSettings | None) -> tuple[dict[str, Any], int, float]:
    if runtime_llm is None:
        return {}, 4096, 0.7
    return (
        {"temperature": runtime_llm.temperature, "max_tokens": runtime_llm.max_tokens},
        runtime_llm.max_tokens,
        runtime_llm.temperature,
    )


def create_llm_client(
    settings: Settings,
    *,
    runtime_llm: LLMSettings | None = None,
) -> ResilientLLMClient:
    """Create the configured LLM client with resilience wrapper."""
    provider_source = runtime_llm.provider if runtime_llm is not None else settings.llm_provider
    provider = provider_source.strip().lower()
    if provider == "claude":
        provider = "anthropic"

    extra_body, max_tokens, temperature = _generation_params(runtime_llm)

    inner: InnerClient
    if provider == "deepseek":
        if not settings.deepseek_api_key:
            raise LLMConfigurationError("DEEPSEEK_API_KEY is required when LLM_PROVIDER=deepseek")
        inner = create_deepseek_client(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            extra_body=extra_body or None,
        )
    elif provider == "ollama":
        inner = create_ollama_client(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            extra_body=extra_body or None,
        )
    elif provider == "openai":
        if not settings.openai_api_key:
            raise LLMConfigurationError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        inner = create_openai_client(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            extra_body=extra_body or None,
        )
    elif provider == "anthropic":
        if not settings.anthropic_api_key:
            raise LLMConfigurationError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        inner = AnthropicClient(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    else:
        raise LLMConfigurationError(
            f"Unsupported LLM provider '{provider_source}'. "
            "Expected deepseek, ollama, openai, anthropic, or claude."
        )

    return ResilientLLMClient(
        inner,
        default_timeout=float(settings.llm_timeout_seconds),
        max_retries=settings.llm_max_retries,
    )
