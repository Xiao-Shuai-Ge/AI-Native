"""Builds the fixed LangGraph StateGraph for task orchestration.

Fixed main graph (see 开发执行计划.md 4.2):

    START -> plan -> select_roles
                        -> [researcher?] -> [analyst?] -> writer -> persist_result -> END

`select_roles` drives two conditional edges so that researcher/analyst are
skipped when the planner did not assign them, while `writer` and
`persist_result` always run so every task produces a report.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agents.roles import ROLE_REGISTRY, RoleConfig
from llm.protocol import LLMClient
from mcp_client.client import MCPClient
from orchestration.langgraph_engine.nodes import (
    analyst_node,
    plan_node,
    researcher_node,
    select_roles_node,
    writer_node,
)
from orchestration.langgraph_engine.ports import NodeEventCallback, ResultPersister
from orchestration.langgraph_engine.state import (
    STEP_ANALYST,
    STEP_PERSIST_RESULT,
    STEP_PLAN,
    STEP_RESEARCHER,
    STEP_SELECT_ROLES,
    STEP_WRITER,
    GraphState,
    to_task_state,
)
from observability.tracing import start_span

logger = logging.getLogger(__name__)

NodeFn = Callable[[GraphState], Awaitable[dict[str, Any]]]


def _with_span(step_name: str, node_fn: NodeFn) -> NodeFn:
    @functools.wraps(node_fn)
    async def _wrapped(state: GraphState) -> dict[str, Any]:
        with start_span(
            f"langgraph.node.{step_name}",
            attributes={"task_id": state.get("task_id"), "step": step_name},
        ):
            return await node_fn(state)

    return _wrapped


def _with_event(
    step_name: str,
    node_fn: NodeFn,
    on_node_complete: NodeEventCallback | None,
) -> NodeFn:
    if on_node_complete is None:
        return node_fn

    @functools.wraps(node_fn)
    async def _wrapped(state: GraphState) -> dict[str, Any]:
        update = await node_fn(state)
        merged = cast("GraphState", {**state, **update})
        try:
            await on_node_complete(step_name, "completed", to_task_state(merged))
        except Exception as exc:
            logger.warning(
                "node completion callback failed; node state is still committed",
                extra={"step": step_name, "task_id": state.get("task_id"), "error": str(exc)},
            )
        return update

    return _wrapped


def _route_after_select_roles(state: GraphState) -> str:
    roles = state.get("assigned_roles", [])
    if "researcher" in roles:
        return STEP_RESEARCHER
    if "analyst" in roles:
        return STEP_ANALYST
    return STEP_WRITER


def _route_after_researcher(state: GraphState) -> str:
    if "analyst" in state.get("assigned_roles", []):
        return STEP_ANALYST
    return STEP_WRITER


def build_graph(
    *,
    llm: LLMClient,
    checkpointer: BaseCheckpointSaver[Any],
    on_node_complete: NodeEventCallback | None = None,
    persist_result: ResultPersister | None = None,
    role_registry: dict[str, RoleConfig] | None = None,
    mcp_client: MCPClient | None = None,
) -> CompiledStateGraph[GraphState, None, GraphState, GraphState]:
    registry = role_registry or ROLE_REGISTRY
    graph: StateGraph[GraphState] = StateGraph(GraphState)

    # `add_node`'s overloaded signature does not model plain async callables
    # cleanly; the runtime accepts any `Callable[[GraphState], Awaitable[dict]]`.
    graph.add_node(  # type: ignore[call-overload]
        STEP_PLAN,
        _with_event(
            STEP_PLAN,
            _with_span(STEP_PLAN, functools.partial(plan_node, llm=llm)),
            on_node_complete,
        ),
    )
    graph.add_node(  # type: ignore[call-overload]
        STEP_SELECT_ROLES,
        _with_event(
            STEP_SELECT_ROLES,
            _with_span(
                STEP_SELECT_ROLES,
                functools.partial(select_roles_node, role_registry=registry),
            ),
            on_node_complete,
        ),
    )
    graph.add_node(  # type: ignore[call-overload]
        STEP_RESEARCHER,
        _with_event(
            STEP_RESEARCHER,
            _with_span(
                STEP_RESEARCHER,
                functools.partial(
                    researcher_node, llm=llm, role_registry=registry, mcp_client=mcp_client
                ),
            ),
            on_node_complete,
        ),
    )
    graph.add_node(  # type: ignore[call-overload]
        STEP_ANALYST,
        _with_event(
            STEP_ANALYST,
            _with_span(
                STEP_ANALYST,
                functools.partial(
                    analyst_node, llm=llm, role_registry=registry, mcp_client=mcp_client
                ),
            ),
            on_node_complete,
        ),
    )
    graph.add_node(  # type: ignore[call-overload]
        STEP_WRITER,
        _with_event(
            STEP_WRITER,
            _with_span(
                STEP_WRITER,
                functools.partial(writer_node, llm=llm, role_registry=registry),
            ),
            on_node_complete,
        ),
    )

    async def persist_result_node(state: GraphState) -> dict[str, Any]:
        if persist_result is not None:
            try:
                await persist_result(to_task_state(state))
            except Exception as exc:
                logger.warning(
                    "persist_result callback failed; graph output is still committed",
                    extra={"task_id": state.get("task_id"), "error": str(exc)},
                )
        return {}

    graph.add_node(  # type: ignore[call-overload]
        STEP_PERSIST_RESULT,
        _with_event(
            STEP_PERSIST_RESULT,
            _with_span(STEP_PERSIST_RESULT, persist_result_node),
            on_node_complete,
        ),
    )

    graph.add_edge(START, STEP_PLAN)
    graph.add_edge(STEP_PLAN, STEP_SELECT_ROLES)
    graph.add_conditional_edges(
        STEP_SELECT_ROLES,
        _route_after_select_roles,
        {STEP_RESEARCHER: STEP_RESEARCHER, STEP_ANALYST: STEP_ANALYST, STEP_WRITER: STEP_WRITER},
    )
    graph.add_conditional_edges(
        STEP_RESEARCHER,
        _route_after_researcher,
        {STEP_ANALYST: STEP_ANALYST, STEP_WRITER: STEP_WRITER},
    )
    graph.add_edge(STEP_ANALYST, STEP_WRITER)
    graph.add_edge(STEP_WRITER, STEP_PERSIST_RESULT)
    graph.add_edge(STEP_PERSIST_RESULT, END)

    return graph.compile(checkpointer=checkpointer)
