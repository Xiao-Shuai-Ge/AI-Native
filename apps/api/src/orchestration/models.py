"""Shared orchestration domain models."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class EngineChoice(StrEnum):
    AUTO = "auto"
    LANGGRAPH = "langgraph"
    CREWAI = "crewai"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ToolCallRecord(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result_summary: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    step_name: str | None = None


class TaskRequest(BaseModel):
    task_id: UUID | None = None
    session_id: UUID | None = None
    user_id: str | None = None
    user_query: str
    engine: EngineChoice = EngineChoice.AUTO
    delay_seconds: float | None = None


class TaskResult(BaseModel):
    task_id: UUID
    status: TaskStatus
    report: str | None = None
    engine_selected: EngineChoice | None = None
    engine_selection_reason: str | None = None
    errors: list[str] = Field(default_factory=list)


class TaskState(BaseModel):
    task_id: UUID
    session_id: UUID | None = None
    engine_requested: EngineChoice
    engine_selected: EngineChoice | None = None
    engine_selection_reason: str | None = None
    user_query: str
    plan: dict[str, Any] | None = None
    assigned_roles: list[str] = Field(default_factory=list)
    sources: list[dict[str, str]] = Field(default_factory=list)
    research_notes: list[str] = Field(default_factory=list)
    analysis: str | None = None
    report: str | None = None
    current_step: str | None = None
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
