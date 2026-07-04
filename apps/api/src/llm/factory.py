"""LLM client factory."""

from __future__ import annotations

from api.config import Settings
from llm.adapters.anthropic import AnthropicClient
from llm.adapters.deepseek import create_deepseek_client
from llm.adapters.ollama import create_ollama_client
from llm.adapters.openai_adapter import create_openai_client
from llm.errors import LLMConfigurationError
from llm.resilient import InnerClient, ResilientLLMClient


def create_llm_client(settings: Settings) -> ResilientLLMClient:
    """Create the configured LLM client with resilience wrapper."""
    provider = settings.llm_provider.strip().lower()
    if provider == "claude":
        provider = "anthropic"

    inner: InnerClient
    if provider == "deepseek":
        if not settings.deepseek_api_key:
            raise LLMConfigurationError("DEEPSEEK_API_KEY is required when LLM_PROVIDER=deepseek")
        inner = create_deepseek_client(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
        )
    elif provider == "ollama":
        inner = create_ollama_client(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
        )
    elif provider == "openai":
        if not settings.openai_api_key:
            raise LLMConfigurationError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        inner = create_openai_client(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
        )
    elif provider == "anthropic":
        if not settings.anthropic_api_key:
            raise LLMConfigurationError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        inner = AnthropicClient(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )
    else:
        raise LLMConfigurationError(
            f"Unsupported LLM_PROVIDER '{settings.llm_provider}'. "
            "Expected deepseek, ollama, openai, anthropic, or claude."
        )

    return ResilientLLMClient(
        inner,
        default_timeout=float(settings.llm_timeout_seconds),
        max_retries=settings.llm_max_retries,
    )
