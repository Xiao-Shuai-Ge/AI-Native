"""Task status machine tests."""

import pytest

from orchestration.models import TaskStatus
from persistence.state_machine import assert_transition, can_transition


@pytest.mark.parametrize(
    ("current", "target", "expected"),
    [
        (TaskStatus.QUEUED, TaskStatus.RUNNING, True),
        (TaskStatus.RUNNING, TaskStatus.SUCCEEDED, True),
        (TaskStatus.RUNNING, TaskStatus.FAILED, True),
        (TaskStatus.PAUSED, TaskStatus.RUNNING, True),
        (TaskStatus.FAILED, TaskStatus.RUNNING, True),
        (TaskStatus.QUEUED, TaskStatus.SUCCEEDED, False),
        (TaskStatus.SUCCEEDED, TaskStatus.RUNNING, False),
        (TaskStatus.CANCELLED, TaskStatus.RUNNING, False),
    ],
)
def test_can_transition(current: TaskStatus, target: TaskStatus, expected: bool) -> None:
    assert can_transition(current, target) is expected


def test_assert_transition_raises_for_invalid_move() -> None:
    with pytest.raises(ValueError, match="invalid task status transition"):
        assert_transition(TaskStatus.QUEUED, TaskStatus.SUCCEEDED)


def test_same_status_is_allowed() -> None:
    assert can_transition(TaskStatus.RUNNING, TaskStatus.RUNNING) is True
