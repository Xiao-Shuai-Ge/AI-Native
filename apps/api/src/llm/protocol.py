"""LLM client types and protocol."""

from enum import StrEnum
from typing import Protocol, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)


class ChatRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(BaseModel):
    role: ChatRole
    content: str


class TokenUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class ChatResponse(BaseModel):
    content: str
    model: str | None = None
    usage: TokenUsage | None = None
    finish_reason: str | None = None


class LLMCapabilities(BaseModel):
    supports_streaming: bool = False
    supports_tools: bool = False
    supports_structured_output: bool = False
    max_context_tokens: int | None = None


class LLMProviderInfo(BaseModel):
    provider: str
    model: str
    capabilities: LLMCapabilities = Field(default_factory=LLMCapabilities)


class LLMClient(Protocol):
    @property
    def provider_info(self) -> LLMProviderInfo: ...

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        timeout: float | None = None,
        task_id: str | None = None,
    ) -> ChatResponse: ...

    async def chat_structured(
        self,
        messages: list[ChatMessage],
        schema: type[T],
        *,
        timeout: float | None = None,
        task_id: str | None = None,
    ) -> T: ...
