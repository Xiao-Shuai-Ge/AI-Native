"""Runs one CrewAI role (researcher/analyst/writer) as a minimal single-task Crew.

Each function below builds its own single-Agent, single-Task `Crew` and runs
it to completion. Keeping each role independent (rather than one Crew running
all three Tasks) is what lets `workflows/activities/task_activities.py` wrap
each role in its own Dapr Activity, so a retry only re-runs the failed role
instead of the whole Crew (AGENTS.md section 9).
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from crewai import Crew, Process
from crewai.crews.crew_output import CrewOutput

from agents.roles import ANALYST_ROLE, RESEARCHER_ROLE, WRITER_ROLE, RoleConfig
from agents.schemas import AnalystSummary, ResearcherNotes, WriterSummary
from llm.errors import LLMParseError
from llm.protocol import LLMClient
from orchestration.crewai_engine.builders import build_agent, build_task
from orchestration.crewai_engine.llm_bridge import CrewAILLMBridge
from orchestration.crewai_engine.parsing import parse_structured_output


async def _run_single_task_crew(
    *,
    role: RoleConfig,
    description_body: str,
    schema: type,
    llm: LLMClient,
    task_id: UUID,
) -> str:
    loop = asyncio.get_running_loop()
    bridge = CrewAILLMBridge(
        llm_client=llm,
        task_id=str(task_id),
        async_loop=loop,
    )
    agent = build_agent(role, bridge)
    task = build_task(role=role, agent=agent, description_body=description_body, schema=schema)
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
    output = await crew.kickoff_async()
    if not isinstance(output, CrewOutput):
        msg = f"CrewAI returned a streaming output for role {role.role}, which is not supported"
        raise LLMParseError(msg)
    return output.raw


async def run_researcher(
    user_query: str,
    *,
    task_id: UUID,
    llm: LLMClient,
    subtask: str | None = None,
    role: RoleConfig | None = None,
) -> ResearcherNotes:
    role_config = role or RESEARCHER_ROLE
    description = f"User query: {user_query}"
    if subtask:
        description += f"\nSubtask: {subtask}"
    raw = await _run_single_task_crew(
        role=role_config,
        description_body=description,
        schema=ResearcherNotes,
        llm=llm,
        task_id=task_id,
    )
    return parse_structured_output(raw, ResearcherNotes)


async def run_analyst(
    user_query: str,
    *,
    task_id: UUID,
    llm: LLMClient,
    research_notes: list[str],
    subtask: str | None = None,
    role: RoleConfig | None = None,
) -> AnalystSummary:
    role_config = role or ANALYST_ROLE
    notes_block = "\n".join(f"- {note}" for note in research_notes) or "(no research notes)"
    description = f"User query: {user_query}\nResearch notes:\n{notes_block}"
    if subtask:
        description += f"\nSubtask: {subtask}"
    raw = await _run_single_task_crew(
        role=role_config,
        description_body=description,
        schema=AnalystSummary,
        llm=llm,
        task_id=task_id,
    )
    return parse_structured_output(raw, AnalystSummary)


async def run_writer(
    user_query: str,
    *,
    task_id: UUID,
    llm: LLMClient,
    research_notes: list[str],
    analysis: str | None,
    subtask: str | None = None,
    role: RoleConfig | None = None,
) -> WriterSummary:
    role_config = role or WRITER_ROLE
    notes_block = "\n".join(f"- {note}" for note in research_notes) or "(no research notes)"
    description = (
        f"User query: {user_query}\nResearch notes:\n{notes_block}\n"
        f"Analysis:\n{analysis or '(no analysis)'}"
    )
    if subtask:
        description += f"\nSubtask: {subtask}"
    raw = await _run_single_task_crew(
        role=role_config,
        description_body=description,
        schema=WriterSummary,
        llm=llm,
        task_id=task_id,
    )
    return parse_structured_output(raw, WriterSummary)
