"""Pydantic schemas for task APIs."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from orchestration.models import EngineChoice, TaskStatus


class CreateTaskRequest(BaseModel):
    task_id: UUID | None = None
    session_id: UUID | None = None
    user_id: str | None = None
    user_query: str = Field(min_length=1)
    engine: EngineChoice = EngineChoice.AUTO
    delay_seconds: float | None = Field(default=None, ge=0.0, le=600.0)


class TaskStepResponse(BaseModel):
    id: UUID
    step_name: str
    status: str
    output_json: dict[str, object] | None = None
    created_at: datetime


class TaskMessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: datetime


class AuditEventResponse(BaseModel):
    id: UUID
    engine: str
    step: str
    status: str
    payload: dict[str, object]
    event_time: datetime


class ToolCallResponse(BaseModel):
    id: UUID
    tool_name: str
    arguments: dict[str, object]
    result_summary: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class TokenUsageSummary(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    status: Literal["known", "partial", "unknown"] = "unknown"


class TaskMetricsResponse(BaseModel):
    tool_calls_total: int
    tool_calls_succeeded: int
    tool_calls_failed: int
    token_usage: TokenUsageSummary
    trace_id: str | None = None


class TaskSummaryResponse(BaseModel):
    task_id: UUID
    session_id: UUID | None
    user_id: str
    user_query: str
    engine_requested: str
    engine_selected: str | None = None
    status: str
    workflow_id: str
    thread_id: str
    report: str | None = None
    created_at: datetime
    updated_at: datetime


class TaskDetailResponse(TaskSummaryResponse):
    engine_selection_reason: str | None = None
    steps: list[TaskStepResponse] = Field(default_factory=list)
    messages: list[TaskMessageResponse] = Field(default_factory=list)
    audit_events: list[AuditEventResponse] = Field(default_factory=list)
    tool_calls: list[ToolCallResponse] = Field(default_factory=list)
    metrics: TaskMetricsResponse
    runtime_state: dict[str, object] | None = None
    user_preferences: dict[str, object] | None = None
    session_context: list[dict[str, object]] | None = None


class CreateTaskResponse(BaseModel):
    task_id: UUID
    session_id: UUID
    workflow_id: str
    thread_id: str
    status: TaskStatus
    engine_requested: EngineChoice
    user_preferences: dict[str, object] = Field(default_factory=dict)
    session_context: list[dict[str, object]] = Field(default_factory=list)


class TaskControlResponse(BaseModel):
    task_id: UUID
    workflow_id: str
    status: TaskStatus
