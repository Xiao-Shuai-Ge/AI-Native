"""Pydantic models for Dapr Workflow inputs and outputs."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

TASK_WORKFLOW_NAME = "task_orchestration"
DELAYED_PROBE_STEP = "delayed_probe"
STUB_STEPS: tuple[str, ...] = ("plan", "writer")


class TaskWorkflowInput(BaseModel):
    task_id: UUID
    session_id: UUID
    user_id: str
    user_query: str
    engine_requested: str
    workflow_id: str
    thread_id: str
    delay_seconds: float = 0.0
    user_preferences: dict[str, object] = Field(default_factory=dict)
    session_context: list[dict[str, object]] = Field(default_factory=list)


class StepActivityInput(BaseModel):
    task_id: UUID
    session_id: UUID
    user_id: str
    engine: str
    step_name: str
    step_status: str = "completed"


class DelayedStepInput(BaseModel):
    task_id: UUID
    session_id: UUID
    user_id: str
    engine: str
    delay_seconds: float


class TaskFailureInput(BaseModel):
    task_id: UUID
    error: str


class ActivityStepResult(BaseModel):
    step_name: str
    created: bool


class DelayedStepResult(BaseModel):
    created: bool
    skipped: bool = False


class InitializeTaskResult(BaseModel):
    status: str = "running"


class LangGraphStepInput(BaseModel):
    task_id: UUID
    session_id: UUID
    user_id: str
    user_query: str
    engine: str
    thread_id: str


class LangGraphStepResult(BaseModel):
    report: str | None = None
    errors: list[str] = Field(default_factory=list)


class SelectEngineInput(BaseModel):
    task_id: UUID
    session_id: UUID
    user_id: str
    user_query: str


class SelectEngineResult(BaseModel):
    engine_selected: str
    reason: str
    subtasks: dict[str, str] = Field(default_factory=dict)


class CrewAIResearcherInput(BaseModel):
    task_id: UUID
    session_id: UUID
    user_id: str
    user_query: str
    engine: str
    subtask: str | None = None


class CrewAIResearcherResult(BaseModel):
    notes: list[str] = Field(default_factory=list)
    sources: list[dict[str, str]] = Field(default_factory=list)


class CrewAIAnalystInput(BaseModel):
    task_id: UUID
    session_id: UUID
    user_id: str
    user_query: str
    engine: str
    research_notes: list[str] = Field(default_factory=list)
    subtask: str | None = None


class CrewAIAnalystResult(BaseModel):
    analysis: str


class CrewAIWriterInput(BaseModel):
    task_id: UUID
    session_id: UUID
    user_id: str
    user_query: str
    engine: str
    research_notes: list[str] = Field(default_factory=list)
    analysis: str | None = None


class CrewAIWriterResult(BaseModel):
    report: str


class FinalizeTaskInput(BaseModel):
    task_id: UUID
    session_id: UUID
    user_id: str
    engine: str
    report: str | None = None


class FinalizeTaskResult(BaseModel):
    status: str = "succeeded"
    report: str
