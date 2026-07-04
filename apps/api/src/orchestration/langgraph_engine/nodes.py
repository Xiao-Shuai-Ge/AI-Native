"""LangGraph node implementations.

Each node receives the current `GraphState` and returns only the fields it
changed (LangGraph merges partial updates using each field's reducer), so
nodes never pass an ever-growing full message history between each other.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from agents.analyst import AnalystAgent
from agents.planner import PlannerAgent
from agents.researcher import ResearcherAgent
from agents.roles import ROLE_REGISTRY
from agents.writer import WriterAgent
from llm.protocol import LLMClient
from orchestration.langgraph_engine.state import (
    STEP_ANALYST,
    STEP_PLAN,
    STEP_RESEARCHER,
    STEP_SELECT_ROLES,
    STEP_WRITER,
    GraphState,
)

_DEFAULT_ROLE_SUBSET = ("writer",)


async def plan_node(state: GraphState, *, llm: LLMClient) -> dict[str, Any]:
    planner = PlannerAgent()
    plan_output = await planner.plan(
        state["user_query"],
        task_id=UUID(state["task_id"]),
        llm=llm,
    )
    return {
        "plan": plan_output.subtasks,
        "assigned_roles": plan_output.assigned_roles,
        "current_step": STEP_PLAN,
    }


async def select_roles_node(state: GraphState) -> dict[str, Any]:
    """Pure state transform: normalize the planner's role selection.

    No LLM/network/DB call happens here; this only enforces the fixed role
    registry and guarantees `writer` always runs so a report is produced.
    """
    requested = [role for role in state.get("assigned_roles", []) if role in ROLE_REGISTRY]
    if not requested:
        requested = list(_DEFAULT_ROLE_SUBSET)
    if "writer" not in requested:
        requested = [*requested, "writer"]
    return {
        "assigned_roles": requested,
        "current_step": STEP_SELECT_ROLES,
    }


async def researcher_node(state: GraphState, *, llm: LLMClient) -> dict[str, Any]:
    researcher = ResearcherAgent()
    plan = state.get("plan") or {}
    result = await researcher.research(
        state["user_query"],
        task_id=UUID(state["task_id"]),
        llm=llm,
        subtask=plan.get("researcher"),
    )
    return {
        "research_notes": list(result.notes),
        "sources": list(result.sources),
        "current_step": STEP_RESEARCHER,
    }


async def analyst_node(state: GraphState, *, llm: LLMClient) -> dict[str, Any]:
    analyst = AnalystAgent()
    plan = state.get("plan") or {}
    result = await analyst.analyze(
        state["user_query"],
        task_id=UUID(state["task_id"]),
        llm=llm,
        research_notes=list(state.get("research_notes", [])),
        subtask=plan.get("analyst"),
    )
    return {
        "analysis": result.analysis,
        "current_step": STEP_ANALYST,
    }


async def writer_node(state: GraphState, *, llm: LLMClient) -> dict[str, Any]:
    writer = WriterAgent()
    result = await writer.summarize(
        state["user_query"],
        task_id=UUID(state["task_id"]),
        llm=llm,
        research_notes=list(state.get("research_notes", [])),
        analysis=state.get("analysis"),
    )
    return {
        "report": result.markdown,
        "current_step": STEP_WRITER,
    }
