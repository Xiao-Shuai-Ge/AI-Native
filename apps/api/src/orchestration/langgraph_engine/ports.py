"""Injection points that keep the LangGraph engine decoupled from I/O layers.

The engine and its nodes never import `events`/`persistence` directly; callers
(Dapr Workflow Activities) wire concrete implementations through these
callbacks, keeping the orchestration layer testable and boundary-compliant.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from orchestration.models import TaskState

# Invoked after each node completes with (step_name, status, state).
NodeEventCallback = Callable[[str, str, TaskState], Awaitable[None]]

# Invoked once the graph reaches `persist_result` with the final state.
ResultPersister = Callable[[TaskState], Awaitable[None]]
