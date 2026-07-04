"""CrewAI engine/role-runner tests driven with a fake, deterministic LLM.

These tests build *real* CrewAI `Agent`/`Task`/`Crew` objects (see
`orchestration/crewai_engine/`); only the LLM backend is faked so the tests
stay offline and deterministic (AGENTS.md section 7: "测试默认使用 fake/mock
LLM；真实模型测试必须显式启用").
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

import orchestration.crewai_engine as crewai_engine_package
from agents.schemas import AnalystSummary, ResearcherNotes, WriterSummary
from llm.fake import FakeLLMClient
from llm.protocol import ChatMessage, ChatResponse
from orchestration.crewai_engine.engine import CrewAIEngine
from orchestration.crewai_engine.roles_runner import run_analyst, run_researcher, run_writer
from orchestration.models import EngineChoice, TaskRequest, TaskStatus


def test_importing_crewai_engine_redirects_storage_and_disables_telemetry() -> None:
    """Regression test for CrewAI writing its kickoff-replay SQLite cache

    under `$HOME` (e.g. `~/Library/Application Support/<app>`), which crashes
    every role call in environments where that directory isn't writable
    (restricted sandboxes, read-only-HOME containers, CI). See
    `orchestration/crewai_engine/__init__.py`.
    """
    assert crewai_engine_package  # import already happened; env vars are set as a side effect
    assert os.environ.get("CREWAI_STORAGE_DIR") == str(
        Path(tempfile.gettempdir()) / "ainative-crewai-storage"
    )
    assert os.environ.get("CREWAI_DISABLE_TELEMETRY") == "true"


def _joined_content(messages: list[ChatMessage]) -> str:
    return " ".join(message.content for message in messages)


def _fake_llm() -> FakeLLMClient:
    def handler(messages: list[ChatMessage]) -> ChatResponse:
        content = _joined_content(messages)
        payload: dict[str, object]
        if "ResearcherNotes" in content:
            payload = {"notes": ["fact one", "fact two"], "sources": []}
        elif "AnalystSummary" in content:
            payload = {"analysis": "Key findings synthesized from the notes."}
        elif "WriterSummary" in content:
            payload = {
                "title": "Demo Report",
                "summary": "A short summary.",
                "markdown": "# Demo Report\n\nA short summary.",
            }
        else:
            msg = f"unexpected CrewAI task prompt (no known schema hint): {content[:200]}"
            raise AssertionError(msg)
        return ChatResponse(content=json.dumps(payload), model="fake-model")

    return FakeLLMClient(chat_handler=handler)


@pytest.mark.asyncio
async def test_run_researcher_builds_real_agent_task_and_parses_notes() -> None:
    result = await run_researcher(
        "What is Dapr Workflow?",
        task_id=uuid4(),
        llm=_fake_llm(),
    )
    assert isinstance(result, ResearcherNotes)
    assert result.notes == ["fact one", "fact two"]


@pytest.mark.asyncio
async def test_run_analyst_builds_real_agent_task_and_parses_analysis() -> None:
    result = await run_analyst(
        "What is Dapr Workflow?",
        task_id=uuid4(),
        llm=_fake_llm(),
        research_notes=["fact one"],
    )
    assert isinstance(result, AnalystSummary)
    assert result.analysis == "Key findings synthesized from the notes."


@pytest.mark.asyncio
async def test_run_writer_builds_real_agent_task_and_parses_report() -> None:
    result = await run_writer(
        "What is Dapr Workflow?",
        task_id=uuid4(),
        llm=_fake_llm(),
        research_notes=["fact one"],
        analysis="Key findings.",
    )
    assert isinstance(result, WriterSummary)
    assert result.markdown.startswith("# Demo Report")


@pytest.mark.asyncio
async def test_crewai_engine_runs_full_researcher_analyst_writer_sequence() -> None:
    engine = CrewAIEngine(llm=_fake_llm())
    request = TaskRequest(task_id=uuid4(), user_query="What is Dapr Workflow?")

    result = await engine.run(request)

    assert result.status == TaskStatus.SUCCEEDED
    assert result.engine_selected == EngineChoice.CREWAI
    assert result.report is not None
    assert "Demo Report" in result.report
    assert result.errors == []


@pytest.mark.asyncio
async def test_crewai_engine_reports_failure_when_a_role_raises() -> None:
    def broken_handler(_messages: list[ChatMessage]) -> ChatResponse:
        return ChatResponse(content="not valid json at all", model="fake-model")

    engine = CrewAIEngine(llm=FakeLLMClient(chat_handler=broken_handler))
    request = TaskRequest(task_id=uuid4(), user_query="anything")

    result = await engine.run(request)

    assert result.status == TaskStatus.FAILED
    assert result.report is None
    assert result.errors


@pytest.mark.asyncio
async def test_crewai_engine_resume_is_explicitly_unsupported() -> None:
    engine = CrewAIEngine(llm=_fake_llm())
    with pytest.raises(NotImplementedError):
        await engine.resume(str(uuid4()))
