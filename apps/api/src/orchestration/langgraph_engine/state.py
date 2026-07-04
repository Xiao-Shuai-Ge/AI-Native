"""LangGraph state definition and conversions to/from the shared TaskState."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict
from uuid import UUID

from orchestration.models import EngineChoice, TaskState, ToolCallRecord

STEP_PLAN = "plan"
STEP_SELECT_ROLES = "select_roles"
STEP_RESEARCHER = "researcher"
STEP_ANALYST = "analyst"
STEP_WRITER = "writer"
STEP_PERSIST_RESULT = "persist_result"


def _replace_list[T](_current: list[T], update: list[T]) -> list[T]:
    """Last-write-wins reducer for single-execution node list fields."""

    return list(update)


class GraphState(TypedDict, total=False):
    """LangGraph working state for a single task run.

    Node-produced list fields use last-write-wins reducers so a retried node
    replaces its prior output instead of appending duplicates.
    """

    task_id: str
    session_id: str | None
    engine_requested: str
    engine_selected: str | None
    engine_selection_reason: str | None
    user_query: str
    plan: dict[str, Any] | None
    assigned_roles: list[str]
    sources: Annotated[list[dict[str, str]], _replace_list]
    research_notes: Annotated[list[str], _replace_list]
    analysis: str | None
    report: str | None
    current_step: str | None
    tool_calls: Annotated[list[dict[str, Any]], _replace_list]
    errors: Annotated[list[str], _replace_list]


def from_task_state(state: TaskState) -> GraphState:
    return GraphState(
        task_id=str(state.task_id),
        session_id=str(state.session_id) if state.session_id else None,
        engine_requested=state.engine_requested.value,
        engine_selected=state.engine_selected.value if state.engine_selected else None,
        engine_selection_reason=state.engine_selection_reason,
        user_query=state.user_query,
        plan=state.plan,
        assigned_roles=list(state.assigned_roles),
        sources=list(state.sources),
        research_notes=list(state.research_notes),
        analysis=state.analysis,
        report=state.report,
        current_step=state.current_step,
        tool_calls=[call.model_dump(mode="json") for call in state.tool_calls],
        errors=list(state.errors),
    )


def to_task_state(state: GraphState) -> TaskState:
    session_id = state.get("session_id")
    engine_selected = state.get("engine_selected")
    return TaskState(
        task_id=UUID(state["task_id"]),
        session_id=UUID(session_id) if session_id else None,
        engine_requested=EngineChoice(state["engine_requested"]),
        engine_selected=EngineChoice(engine_selected) if engine_selected else None,
        engine_selection_reason=state.get("engine_selection_reason"),
        user_query=state["user_query"],
        plan=state.get("plan"),
        assigned_roles=list(state.get("assigned_roles", [])),
        sources=list(state.get("sources", [])),
        research_notes=list(state.get("research_notes", [])),
        analysis=state.get("analysis"),
        report=state.get("report"),
        current_step=state.get("current_step"),
        tool_calls=[ToolCallRecord.model_validate(call) for call in state.get("tool_calls", [])],
        errors=list(state.get("errors", [])),
    )
