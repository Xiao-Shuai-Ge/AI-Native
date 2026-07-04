"""Task status transition rules."""

from orchestration.models import TaskStatus

ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.QUEUED: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {
        TaskStatus.PAUSED,
        TaskStatus.SUCCEEDED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.PAUSED: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.FAILED: {TaskStatus.RUNNING},
    TaskStatus.SUCCEEDED: set(),
    TaskStatus.CANCELLED: set(),
}


def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    if current == target:
        return True
    return target in ALLOWED_TRANSITIONS.get(current, set())


def assert_transition(current: TaskStatus, target: TaskStatus) -> None:
    if not can_transition(current, target):
        msg = f"invalid task status transition: {current.value} -> {target.value}"
        raise ValueError(msg)
