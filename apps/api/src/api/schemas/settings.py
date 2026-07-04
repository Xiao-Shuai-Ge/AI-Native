"""Pydantic schemas for runtime settings APIs."""

from typing import Literal

from pydantic import BaseModel, Field

LLMProviderChoice = Literal["deepseek", "ollama", "openai", "anthropic", "claude"]

ALLOWED_LLM_PROVIDERS: frozenset[str] = frozenset(
    {"deepseek", "ollama", "openai", "anthropic", "claude"}
)


class AgentRoleSettings(BaseModel):
    role: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    backstory: str = Field(min_length=1)
    instructions: str = Field(min_length=1)
    version: str = Field(default="v1", min_length=1)


class LLMSettings(BaseModel):
    provider: LLMProviderChoice
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, le=128_000)


class RuntimeSettingsResponse(BaseModel):
    llm: LLMSettings
    agents: dict[str, AgentRoleSettings]


class UpdateRuntimeSettingsRequest(BaseModel):
    llm: LLMSettings | None = None
    agents: dict[str, AgentRoleSettings] | None = None
