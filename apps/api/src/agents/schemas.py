"""Structured output schemas for agent roles."""

from pydantic import BaseModel, Field, field_validator

ALLOWED_ROLES = frozenset({"researcher", "analyst", "writer"})


class WriterSummary(BaseModel):
    """Structured writer output for topic summaries."""

    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    markdown: str = Field(min_length=1)


class PlanOutput(BaseModel):
    """Structured planner output selecting a subset of registered roles."""

    assigned_roles: list[str] = Field(min_length=1)
    subtasks: dict[str, str] = Field(default_factory=dict)

    @field_validator("assigned_roles")
    @classmethod
    def _validate_roles(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - ALLOWED_ROLES)
        if unknown:
            msg = f"unknown roles requested by planner: {unknown}"
            raise ValueError(msg)
        return value


class ResearcherNotes(BaseModel):
    """Structured researcher output."""

    notes: list[str] = Field(default_factory=list)
    sources: list[dict[str, str]] = Field(default_factory=list)


class AnalystSummary(BaseModel):
    """Structured analyst output."""

    analysis: str = Field(min_length=1)
