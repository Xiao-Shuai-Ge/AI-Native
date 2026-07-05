"""Resilient LLM client wrapper with timeout, retry and logging."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx
from pydantic import BaseModel

from llm.adapters.anthropic import AnthropicClient
from llm.errors import LLMTimeoutError, LLMUnavailableError
from llm.openai_compatible import OpenAICompatibleClient
from llm.protocol import ChatMessage, ChatResponse, LLMProviderInfo, ToolDefinition

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
R = TypeVar("R")

InnerClient = OpenAICompatibleClient | AnthropicClient


class ResilientLLMClient:
    """Wrap an LLM client with timeout enforcement, limited retry and logging."""

    def __init__(
        self,
        inner: InnerClient,
        *,
        default_timeout: float,
        max_retries: int,
    ) -> None:
        self._inner = inner
        self._default_timeout = default_timeout
        self._max_retries = max_retries

    @property
    def provider_info(self) -> LLMProviderInfo:
        return self._inner.provider_info

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        timeout: float | None = None,
        task_id: str | None = None,
        tools: list[ToolDefinition] | None = None,
    ) -> ChatResponse:
        effective_timeout = timeout if timeout is not None else self._default_timeout
        return await self._execute_with_resilience(
            operation="chat",
            task_id=task_id,
            timeout=effective_timeout,
            call=lambda: self._inner.chat(messages, timeout=effective_timeout, tools=tools),
        )

    async def chat_structured(
        self,
        messages: list[ChatMessage],
        schema: type[T],
        *,
        timeout: float | None = None,
        task_id: str | None = None,
    ) -> T:
        effective_timeout = timeout if timeout is not None else self._default_timeout
        return await self._execute_with_resilience(
            operation="chat_structured",
            task_id=task_id,
            timeout=effective_timeout,
            call=lambda: self._inner.chat_structured(
                messages,
                schema,
                timeout=effective_timeout,
            ),
        )

    async def _execute_with_resilience(
        self,
        *,
        operation: str,
        task_id: str | None,
        timeout: float,
        call: Callable[[], Awaitable[R]],
    ) -> R:
        provider = self.provider_info.provider
        model = self.provider_info.model
        attempts = self._max_retries + 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            started = time.perf_counter()
            try:
                result = await asyncio.wait_for(call(), timeout=timeout)
            except TimeoutError as exc:
                last_error = LLMTimeoutError(f"LLM {operation} exceeded timeout of {timeout}s")
                duration_ms = int((time.perf_counter() - started) * 1000)
                self._log_call(
                    task_id=task_id,
                    provider=provider,
                    model=model,
                    duration_ms=duration_ms,
                    status="error",
                    error=str(last_error),
                    attempt=attempt + 1,
                )
                if attempt < attempts - 1 and self._is_retryable(last_error):
                    continue
                raise last_error from exc
            except Exception as exc:
                last_error = exc
                duration_ms = int((time.perf_counter() - started) * 1000)
                self._log_call(
                    task_id=task_id,
                    provider=provider,
                    model=model,
                    duration_ms=duration_ms,
                    status="error",
                    error=str(exc),
                    attempt=attempt + 1,
                )
                if attempt < attempts - 1 and self._is_retryable(exc):
                    continue
                raise

            duration_ms = int((time.perf_counter() - started) * 1000)
            self._log_call(
                task_id=task_id,
                provider=provider,
                model=model,
                duration_ms=duration_ms,
                status="success",
                error=None,
                attempt=attempt + 1,
            )
            return result

        assert last_error is not None
        raise last_error

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        if isinstance(exc, LLMTimeoutError):
            return True
        if isinstance(exc, LLMUnavailableError):
            message = str(exc)
            for code in ("429", "502", "503"):
                if f"HTTP {code}" in message:
                    return True
            if "transport layer" in message:
                return True
        return isinstance(exc, httpx.HTTPError)

    @staticmethod
    def _log_call(
        *,
        task_id: str | None,
        provider: str,
        model: str,
        duration_ms: int,
        status: str,
        error: str | None,
        attempt: int,
    ) -> None:
        logger.info(
            "llm.chat",
            extra={
                "task_id": task_id,
                "provider": provider,
                "model": model,
                "duration_ms": duration_ms,
                "status": status,
                "error": error,
                "attempt": attempt,
            },
        )
