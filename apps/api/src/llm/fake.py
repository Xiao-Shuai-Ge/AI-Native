"""Fake LLM client for tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel

from llm.errors import LLMError
from llm.protocol import ChatMessage, ChatResponse, LLMCapabilities, LLMProviderInfo

T = TypeVar("T", bound=BaseModel)


class FakeLLMClient:
    """Deterministic LLM client used by unit tests."""

    def __init__(
        self,
        *,
        provider: str = "fake",
        model: str = "fake-model",
        chat_handler: Callable[[list[ChatMessage]], Awaitable[ChatResponse] | ChatResponse]
        | None = None,
        structured_handler: Callable[
            [list[ChatMessage], type[BaseModel]],
            Awaitable[BaseModel] | BaseModel,
        ]
        | None = None,
        error: LLMError | None = None,
    ) -> None:
        self._provider_info = LLMProviderInfo(
            provider=provider,
            model=model,
            capabilities=LLMCapabilities(
                supports_streaming=False,
                supports_tools=False,
                supports_structured_output=True,
                max_context_tokens=8192,
            ),
        )
        self._chat_handler = chat_handler
        self._structured_handler = structured_handler
        self._error = error
        self.chat_calls: list[list[ChatMessage]] = []
        self.structured_calls: list[tuple[list[ChatMessage], type[BaseModel]]] = []

    @property
    def provider_info(self) -> LLMProviderInfo:
        return self._provider_info

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        timeout: float | None = None,
        task_id: str | None = None,
    ) -> ChatResponse:
        self.chat_calls.append(messages)
        if self._error is not None:
            raise self._error
        if self._chat_handler is None:
            return ChatResponse(content="fake response", model=self._provider_info.model)
        result = self._chat_handler(messages)
        if isinstance(result, ChatResponse):
            return result
        return await result

    async def chat_structured(
        self,
        messages: list[ChatMessage],
        schema: type[T],
        *,
        timeout: float | None = None,
        task_id: str | None = None,
    ) -> T:
        self.structured_calls.append((messages, schema))
        if self._error is not None:
            raise self._error
        if self._structured_handler is None:
            return schema.model_validate(
                {
                    "title": "Fake Title",
                    "summary": "Fake summary.",
                    "markdown": "# Fake Title\n\nFake summary.",
                }
            )
        result = self._structured_handler(messages, schema)
        if isinstance(result, BaseModel):
            return result  # type: ignore[return-value]
        return await result  # type: ignore[return-value]
