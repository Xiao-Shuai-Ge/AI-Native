"""LangGraph implementation of the `OrchestrationEngine` protocol."""

from __future__ import annotations

from uuid import UUID, uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver

from llm.protocol import LLMClient
from orchestration.langgraph_engine.graph import build_graph
from orchestration.langgraph_engine.ports import NodeEventCallback, ResultPersister
from orchestration.langgraph_engine.state import from_task_state, to_task_state
from orchestration.models import EngineChoice, TaskRequest, TaskResult, TaskState, TaskStatus


class LangGraphEngine:
    """Runs the fixed plan/select_roles/researcher/analyst/writer graph.

    LangGraph checkpoints are stored under `thread_id=str(task_id)` so that a
    retried Activity (e.g. after a worker crash) resumes from the last
    completed node instead of restarting the whole graph.
    """

    def __init__(
        self,
        *,
        llm: LLMClient,
        checkpointer: BaseCheckpointSaver[str],
        on_node_complete: NodeEventCallback | None = None,
        persist_result: ResultPersister | None = None,
    ) -> None:
        self._graph = build_graph(
            llm=llm,
            checkpointer=checkpointer,
            on_node_complete=on_node_complete,
            persist_result=persist_result,
        )

    async def run(self, request: TaskRequest) -> TaskResult:
        task_id = request.task_id or uuid4()
        initial_state = TaskState(
            task_id=task_id,
            session_id=request.session_id,
            engine_requested=request.engine,
            user_query=request.user_query,
        )
        config: RunnableConfig = {"configurable": {"thread_id": str(task_id)}}
        final_state = await self._graph.ainvoke(from_task_state(initial_state), config=config)
        return self._to_result(task_id, final_state)

    async def resume(self, task_id: str) -> TaskResult:
        config: RunnableConfig = {"configurable": {"thread_id": task_id}}
        final_state = await self._graph.ainvoke(None, config=config)
        if not final_state:
            msg = f"no LangGraph checkpoint found for task_id={task_id}"
            raise ValueError(msg)
        return self._to_result(UUID(task_id), final_state)

    def _to_result(self, task_id: UUID, final_state: object) -> TaskResult:
        task_state = to_task_state(final_state)  # type: ignore[arg-type]
        failed = bool(task_state.errors) or not task_state.report
        return TaskResult(
            task_id=task_id,
            status=TaskStatus.FAILED if failed else TaskStatus.SUCCEEDED,
            report=task_state.report,
            engine_selected=EngineChoice.LANGGRAPH,
            errors=task_state.errors,
        )
