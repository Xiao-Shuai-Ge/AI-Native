"""CrewAI implementation of the `OrchestrationEngine` protocol.

Unlike `LangGraphEngine` (single Activity + Dapr checkpointer), the Dapr
Workflow wraps each CrewAI role in its own Activity
(`workflows.activities.task_activities.run_crewai_researcher/analyst/writer`)
so retries only re-run the failed role (AGENTS.md section 9). `CrewAIEngine`
itself exists for protocol parity, unit testing, and any direct (non-Workflow)
callers; it always runs researcher -> analyst -> writer in sequence.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import uuid4

from agents.roles import ANALYST_ROLE, RESEARCHER_ROLE, WRITER_ROLE, RoleConfig
from llm.protocol import LLMClient
from mcp_client.client import MCPClient
from orchestration.crewai_engine.roles_runner import run_analyst, run_researcher, run_writer
from orchestration.models import EngineChoice, TaskRequest, TaskResult, TaskStatus, ToolCallRecord

RoleEventCallback = Callable[[str, str], Awaitable[None]]


class CrewAIEngine:
    """Runs the fixed researcher/analyst/writer CrewAI role sequence."""

    def __init__(
        self,
        *,
        llm: LLMClient,
        role_registry: dict[str, RoleConfig] | None = None,
        on_role_complete: RoleEventCallback | None = None,
        mcp_client: MCPClient | None = None,
    ) -> None:
        self._llm = llm
        self._role_registry = role_registry or {}
        self._on_role_complete = on_role_complete
        self._mcp_client = mcp_client
        # Exposed for tests/callers that want the tool-call audit trail from
        # the most recent `run()`; not part of `TaskResult` (kept identical
        # across engines) so this stays an engine-specific convenience.
        self.tool_calls: list[ToolCallRecord] = []

    async def run(self, request: TaskRequest) -> TaskResult:
        task_id = request.task_id or uuid4()
        errors: list[str] = []
        report: str | None = None
        self.tool_calls = []
        try:
            researcher_role = self._role_registry.get("researcher", RESEARCHER_ROLE)
            notes_result, researcher_tool_calls = await run_researcher(
                request.user_query,
                task_id=task_id,
                llm=self._llm,
                role=researcher_role,
                mcp_client=self._mcp_client,
            )
            self.tool_calls.extend(researcher_tool_calls)
            await self._emit("researcher")

            analyst_role = self._role_registry.get("analyst", ANALYST_ROLE)
            analysis_result, analyst_tool_calls = await run_analyst(
                request.user_query,
                task_id=task_id,
                llm=self._llm,
                research_notes=list(notes_result.notes),
                role=analyst_role,
                mcp_client=self._mcp_client,
            )
            self.tool_calls.extend(analyst_tool_calls)
            await self._emit("analyst")

            writer_role = self._role_registry.get("writer", WRITER_ROLE)
            writer_result = await run_writer(
                request.user_query,
                task_id=task_id,
                llm=self._llm,
                research_notes=list(notes_result.notes),
                analysis=analysis_result.analysis,
                role=writer_role,
            )
            await self._emit("writer")
            report = writer_result.markdown
        except Exception as exc:  # noqa: BLE001 - surfaced as a TaskResult error
            errors.append(str(exc))

        return TaskResult(
            task_id=task_id,
            status=TaskStatus.FAILED if errors or not report else TaskStatus.SUCCEEDED,
            report=report,
            engine_selected=EngineChoice.CREWAI,
            errors=errors,
        )

    async def resume(self, task_id: str) -> TaskResult:
        # CrewAI has no built-in checkpointer: resumption for this engine is
        # handled at the Dapr Workflow/Activity level (each role is its own
        # idempotent Activity), not inside CrewAIEngine itself. Calling this
        # directly is not supported; it exists only to satisfy the shared
        # `OrchestrationEngine` protocol type.
        msg = (
            "CrewAIEngine.resume() is not supported: resumption is handled by "
            "retrying the per-role Dapr Activities, not by the engine itself"
        )
        raise NotImplementedError(msg)

    async def _emit(self, step_name: str) -> None:
        if self._on_role_complete is not None:
            await self._on_role_complete(step_name, "completed")
