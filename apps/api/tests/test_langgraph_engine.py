"""LangGraph multi-node graph unit tests, driven entirely by FakeLLMClient."""

from __future__ import annotations

from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel

from agents.schemas import AnalystSummary, PlanOutput, ResearcherNotes, WriterSummary
from llm.fake import FakeLLMClient
from orchestration.langgraph_engine.engine import LangGraphEngine
from orchestration.langgraph_engine.graph import build_graph
from orchestration.langgraph_engine.state import STEP_PLAN, from_task_state
from orchestration.models import EngineChoice, TaskRequest, TaskState, TaskStatus


def _schema_dispatch_llm(*, assigned_roles: list[str]) -> FakeLLMClient:
    call_counts: dict[str, int] = {}

    def _handler(_messages: object, schema: type[BaseModel]) -> BaseModel:
        call_counts[schema.__name__] = call_counts.get(schema.__name__, 0) + 1
        if schema is PlanOutput:
            return PlanOutput(assigned_roles=assigned_roles, subtasks={})
        if schema is ResearcherNotes:
            return ResearcherNotes(
                notes=["fake research note"],
                sources=[{"title": "fake source", "url": "https://example.com"}],
            )
        if schema is AnalystSummary:
            return AnalystSummary(analysis="fake analysis")
        if schema is WriterSummary:
            return WriterSummary(
                title="Fake Title",
                summary="Fake summary",
                markdown="# Fake Title\n\nFake summary",
            )
        msg = f"unexpected schema requested: {schema}"
        raise AssertionError(msg)

    llm = FakeLLMClient(structured_handler=_handler)
    llm.call_counts = call_counts  # type: ignore[attr-defined]
    return llm


@pytest.mark.asyncio
async def test_full_graph_with_all_roles_produces_report() -> None:
    llm = _schema_dispatch_llm(assigned_roles=["researcher", "analyst", "writer"])
    events: list[str] = []

    async def on_node_complete(step_name: str, status: str, _state: TaskState) -> None:
        events.append(step_name)

    engine = LangGraphEngine(
        llm=llm,
        checkpointer=MemorySaver(),
        on_node_complete=on_node_complete,
    )
    result = await engine.run(
        TaskRequest(user_query="什么是 Dapr Workflow", engine=EngineChoice.LANGGRAPH)
    )

    assert result.status == TaskStatus.SUCCEEDED
    assert result.engine_selected == EngineChoice.LANGGRAPH
    assert result.report and "Fake Title" in result.report
    assert events == ["plan", "select_roles", "researcher", "analyst", "writer", "persist_result"]


@pytest.mark.asyncio
async def test_full_graph_writer_only_skips_researcher_and_analyst() -> None:
    llm = _schema_dispatch_llm(assigned_roles=["writer"])
    events: list[str] = []

    async def on_node_complete(step_name: str, status: str, _state: TaskState) -> None:
        events.append(step_name)

    engine = LangGraphEngine(
        llm=llm,
        checkpointer=MemorySaver(),
        on_node_complete=on_node_complete,
    )
    result = await engine.run(TaskRequest(user_query="topic", engine=EngineChoice.LANGGRAPH))

    assert result.status == TaskStatus.SUCCEEDED
    assert events == ["plan", "select_roles", "writer", "persist_result"]
    assert llm.call_counts.get("ResearcherNotes", 0) == 0  # type: ignore[attr-defined]
    assert llm.call_counts.get("AnalystSummary", 0) == 0  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_persist_result_callback_receives_final_state() -> None:
    llm = _schema_dispatch_llm(assigned_roles=["researcher", "analyst", "writer"])
    persisted: list[TaskState] = []

    async def persist_result(state: TaskState) -> None:
        persisted.append(state)

    engine = LangGraphEngine(llm=llm, checkpointer=MemorySaver(), persist_result=persist_result)
    await engine.run(TaskRequest(user_query="topic", engine=EngineChoice.LANGGRAPH))

    assert len(persisted) == 1
    assert persisted[0].report is not None
    assert persisted[0].analysis == "fake analysis"


@pytest.mark.asyncio
async def test_node_failure_propagates() -> None:
    def _raise_handler(_messages: object, _schema: type[BaseModel]) -> BaseModel:
        msg = "boom"
        raise RuntimeError(msg)

    llm = FakeLLMClient(structured_handler=_raise_handler)
    engine = LangGraphEngine(llm=llm, checkpointer=MemorySaver())

    with pytest.raises(RuntimeError, match="boom"):
        await engine.run(TaskRequest(user_query="topic", engine=EngineChoice.LANGGRAPH))


@pytest.mark.asyncio
async def test_graph_resumes_from_checkpoint_without_rerunning_plan() -> None:
    """Interrupting after `plan` and resuming must not re-invoke the plan node."""
    llm = _schema_dispatch_llm(assigned_roles=["writer"])
    checkpointer = MemorySaver()
    graph = build_graph(llm=llm, checkpointer=checkpointer).builder.compile(
        checkpointer=checkpointer, interrupt_after=[STEP_PLAN]
    )

    task_id = uuid4()
    initial_state = TaskState(
        task_id=task_id, engine_requested=EngineChoice.LANGGRAPH, user_query="topic"
    )
    config: RunnableConfig = {"configurable": {"thread_id": str(task_id)}}

    await graph.ainvoke(from_task_state(initial_state), config=config)
    assert llm.call_counts.get("PlanOutput", 0) == 1  # type: ignore[attr-defined]

    final_state = await graph.ainvoke(None, config=config)

    assert llm.call_counts.get("PlanOutput", 0) == 1  # type: ignore[attr-defined]
    assert final_state["report"] is not None


@pytest.mark.asyncio
async def test_node_completion_callback_failure_does_not_fail_graph() -> None:
    llm = _schema_dispatch_llm(assigned_roles=["writer"])

    async def flaky_callback(_step_name: str, _status: str, _state: TaskState) -> None:
        msg = "callback boom"
        raise RuntimeError(msg)

    engine = LangGraphEngine(
        llm=llm,
        checkpointer=MemorySaver(),
        on_node_complete=flaky_callback,
    )
    result = await engine.run(TaskRequest(user_query="topic", engine=EngineChoice.LANGGRAPH))

    assert result.status == TaskStatus.SUCCEEDED
    assert result.report is not None


@pytest.mark.asyncio
async def test_to_result_failed_when_errors_present() -> None:
    task_id = uuid4()
    engine = LangGraphEngine(llm=FakeLLMClient(), checkpointer=MemorySaver())
    final_state = from_task_state(
        TaskState(
            task_id=task_id,
            engine_requested=EngineChoice.LANGGRAPH,
            user_query="topic",
            errors=["planner failed"],
            report="# Report",
        )
    )

    result = engine._to_result(task_id, final_state)

    assert result.status == TaskStatus.FAILED
    assert result.errors == ["planner failed"]


@pytest.mark.asyncio
async def test_to_result_failed_when_report_missing() -> None:
    task_id = uuid4()
    engine = LangGraphEngine(llm=FakeLLMClient(), checkpointer=MemorySaver())
    final_state = from_task_state(
        TaskState(
            task_id=task_id,
            engine_requested=EngineChoice.LANGGRAPH,
            user_query="topic",
        )
    )

    result = engine._to_result(task_id, final_state)

    assert result.status == TaskStatus.FAILED
    assert result.report is None
