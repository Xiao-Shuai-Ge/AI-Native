"""Shared Activity retry and timeout constraints for dual-engine workflows."""

from __future__ import annotations

from datetime import timedelta

from dapr.ext.workflow import RetryPolicy

# Documented start-to-close timeouts (enforced inside Activity via asyncio.wait_for where needed).
ACTIVITY_TIMEOUTS: dict[str, timedelta] = {
    "initialize_task": timedelta(seconds=30),
    "execute_step": timedelta(seconds=120),
    "delayed_step_base": timedelta(seconds=60),
    "finalize_task": timedelta(seconds=30),
    "mark_task_failed": timedelta(seconds=30),
}


def _retry(max_attempts: int, *, first_seconds: float = 2.0) -> RetryPolicy:
    return RetryPolicy(
        first_retry_interval=timedelta(seconds=first_seconds),
        max_number_of_attempts=max_attempts,
        backoff_coefficient=2.0,
        max_retry_interval=timedelta(seconds=30),
    )


INITIALIZE_RETRY = _retry(3)
EXECUTE_STEP_RETRY = _retry(3)
FINALIZE_RETRY = _retry(2)
MARK_FAILED_RETRY = _retry(2)


def delayed_step_retry(delay_seconds: float) -> RetryPolicy:
    return _retry(3, first_seconds=min(max(delay_seconds / 4, 1.0), 10.0))


def delayed_step_timeout(delay_seconds: float) -> timedelta:
    return ACTIVITY_TIMEOUTS["delayed_step_base"] + timedelta(seconds=max(delay_seconds, 0.0))
