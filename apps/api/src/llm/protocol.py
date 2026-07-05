"""LLM client types and protocol."""

from enum import StrEnum
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)


class ChatRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall(BaseModel):
    """A single tool invocation requested by the model (OpenAI-compatible shape)."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolDefinition(BaseModel):
    """Tool schema offered to the model, converted from MCP tool metadata."""

    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    role: ChatRole
    content: str
    tool_call_id: str | None = None
    """Set on TOOL-role messages: which prior tool call this result answers."""
    tool_calls: list[ToolCall] | None = None
    """Set on ASSISTANT-role messages that requested tool calls."""


class TokenUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class ChatResponse(BaseModel):
    content: str
    model: str | None = None
    usage: TokenUsage | None = None
    finish_reason: str | None = None
    tool_calls: list[ToolCall] | None = None


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
        tools: list[ToolDefinition] | None = None,
    ) -> ChatResponse: ...

    async def chat_structured(
        self,
        messages: list[ChatMessage],
        schema: type[T],
        *,
        timeout: float | None = None,
        task_id: str | None = None,
    ) -> T: ...
