"""Workflow orchestration branching tests.

`task_orchestration` is a plain generator function (Dapr replays it
deterministically), so it can be driven directly with `next()`/`send()`/
`throw()` without a real Dapr Workflow runtime, injecting the same plain-dict
activity outputs Dapr would deserialize during replay.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from workflows.activities.task_activities import (
    finalize_task,
    initialize_task,
    mark_task_failed,
    run_crewai_analyst,
    run_crewai_researcher,
    run_crewai_writer,
    run_langgraph_graph,
    select_engine,
)
from workflows.models import (
    CrewAIAnalystInput,
    CrewAIResearcherInput,
    CrewAIWriterInput,
    FinalizeTaskInput,
    LangGraphStepResult,
    TaskWorkflowInput,
)
from workflows.task_workflow import task_orchestration


def _wf_input(engine_requested: str) -> TaskWorkflowInput:
    task_id = uuid4()
    session_id = uuid4()
    return TaskWorkflowInput(
        task_id=task_id,
        session_id=session_id,
        user_id="user-1",
        user_query="workflow branching test",
        engine_requested=engine_requested,
        workflow_id=f"wf-{task_id}",
        thread_id=str(task_id),
        delay_seconds=0.0,
    )


def _activity_names(ctx: MagicMock) -> list[str]:
    return [call.args[0].__name__ for call in ctx.call_activity.call_args_list]


def _drive(gen: Any, responses: list[Any]) -> None:
    next(gen)
    for response in responses:
        gen.send(response)


def test_langgraph_step_result_model_validate_accepts_activity_dict() -> None:
    payload = {"report": "# Demo Report", "errors": []}
    parsed = LangGraphStepResult.model_validate(payload)
    assert parsed.report == "# Demo Report"
    assert parsed.errors == []


def test_manual_langgraph_engine_calls_only_langgraph_activity() -> None:
    ctx = MagicMock()
    wf_input = _wf_input("langgraph")
    gen = task_orchestration(ctx, wf_input)

    with pytest.raises(StopIteration):
        _drive(
            gen,
            [
                {},  # initialize_task
                {"report": "# LangGraph Report", "errors": []},  # run_langgraph_graph
                {},  # finalize_task
            ],
        )

    assert _activity_names(ctx) == [
        initialize_task.__name__,
        run_langgraph_graph.__name__,
        finalize_task.__name__,
    ]
    finalize_input = FinalizeTaskInput.model_validate(
        ctx.call_activity.call_args_list[-1].kwargs["input"]
    )
    assert finalize_input.report == "# LangGraph Report"
    assert finalize_input.engine == "langgraph"


def test_manual_crewai_engine_calls_three_independent_role_activities() -> None:
    ctx = MagicMock()
    wf_input = _wf_input("crewai")
    gen = task_orchestration(ctx, wf_input)

    with pytest.raises(StopIteration):
        _drive(
            gen,
            [
                {},  # initialize_task
                {"notes": ["note 1"], "sources": []},  # run_crewai_researcher
                {"analysis": "analysis text"},  # run_crewai_analyst
                {"report": "# CrewAI Report"},  # run_crewai_writer
                {},  # finalize_task
            ],
        )

    assert _activity_names(ctx) == [
        initialize_task.__name__,
        run_crewai_researcher.__name__,
        run_crewai_analyst.__name__,
        run_crewai_writer.__name__,
        finalize_task.__name__,
    ]
    analyst_input = CrewAIAnalystInput.model_validate(
        ctx.call_activity.call_args_list[2].kwargs["input"]
    )
    assert analyst_input.research_notes == ["note 1"]
    writer_input = CrewAIWriterInput.model_validate(
        ctx.call_activity.call_args_list[3].kwargs["input"]
    )
    assert writer_input.analysis == "analysis text"
    finalize_input = FinalizeTaskInput.model_validate(
        ctx.call_activity.call_args_list[-1].kwargs["input"]
    )
    assert finalize_input.report == "# CrewAI Report"
    assert finalize_input.engine == "crewai"


def test_crewai_workflow_accepts_dapr_deserialized_dict_input() -> None:
    """Dapr replays workflow input as plain dicts; coerce before attribute access."""
    ctx = MagicMock()
    wf_input = _wf_input("crewai")
    gen = task_orchestration(ctx, wf_input.model_dump(mode="json"))

    with pytest.raises(StopIteration):
        _drive(
            gen,
            [
                {},
                {"notes": ["note 1"], "sources": []},
                {"analysis": "analysis text"},
                {"report": "# CrewAI Report"},
                {},
            ],
        )

    assert _activity_names(ctx) == [
        initialize_task.__name__,
        run_crewai_researcher.__name__,
        run_crewai_analyst.__name__,
        run_crewai_writer.__name__,
        finalize_task.__name__,
    ]


def test_auto_engine_routes_to_crewai_and_forwards_router_subtasks() -> None:
    ctx = MagicMock()
    wf_input = _wf_input("auto")
    gen = task_orchestration(ctx, wf_input)

    with pytest.raises(StopIteration):
        _drive(
            gen,
            [
                {},  # initialize_task
                {
                    "engine_selected": "crewai",
                    "reason": "role-play collaboration needed",
                    "subtasks": {"researcher": "look into X"},
                },  # select_engine
                {"notes": [], "sources": []},  # run_crewai_researcher
                {"analysis": "n/a"},  # run_crewai_analyst
                {"report": "# Auto->CrewAI Report"},  # run_crewai_writer
                {},  # finalize_task
            ],
        )

    assert _activity_names(ctx) == [
        initialize_task.__name__,
        select_engine.__name__,
        run_crewai_researcher.__name__,
        run_crewai_analyst.__name__,
        run_crewai_writer.__name__,
        finalize_task.__name__,
    ]
    researcher_input = CrewAIResearcherInput.model_validate(
        ctx.call_activity.call_args_list[2].kwargs["input"]
    )
    assert researcher_input.subtask == "look into X"
    assert researcher_input.engine == "crewai"


def test_auto_engine_routes_to_langgraph() -> None:
    ctx = MagicMock()
    wf_input = _wf_input("auto")
    gen = task_orchestration(ctx, wf_input)

    with pytest.raises(StopIteration):
        _drive(
            gen,
            [
                {},  # initialize_task
                {
                    "engine_selected": "langgraph",
                    "reason": "deterministic control preferred",
                    "subtasks": {},
                },  # select_engine
                {"report": "# Auto->LangGraph Report", "errors": []},  # run_langgraph_graph
                {},  # finalize_task
            ],
        )

    assert _activity_names(ctx) == [
        initialize_task.__name__,
        select_engine.__name__,
        run_langgraph_graph.__name__,
        finalize_task.__name__,
    ]


def test_activity_failure_marks_task_failed_and_reraises() -> None:
    ctx = MagicMock()
    wf_input = _wf_input("langgraph")
    gen = task_orchestration(ctx, wf_input)

    next(gen)  # initialize_task yielded
    gen.send({})  # initialize_task result -> run_langgraph_graph yielded
    # Simulate run_langgraph_graph failing; the except branch yields mark_task_failed.
    gen.throw(RuntimeError("boom"))

    with pytest.raises(RuntimeError, match="boom"):
        gen.send({})

    assert _activity_names(ctx) == [
        initialize_task.__name__,
        run_langgraph_graph.__name__,
        mark_task_failed.__name__,
    ]
