"""Per-task token usage accumulation for task-detail metrics."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Literal

from llm.protocol import TokenUsage
from persistence.dapr_state import DaprStateStore

logger = logging.getLogger(__name__)

TokenUsageStatus = Literal["known", "partial", "unknown"]

TokenAccumulator = Callable[[str, TokenUsage, str], Awaitable[None]]

_accumulator: TokenAccumulator | None = None


def register_token_accumulator(callback: TokenAccumulator) -> None:
    global _accumulator
    _accumulator = callback


def clear_token_accumulator() -> None:
    global _accumulator
    _accumulator = None


def register_dapr_token_accumulator(dapr_state: DaprStateStore) -> None:
    """Register a callback that persists per-task token usage into Dapr runtime state."""

    async def accumulator(task_id: str, usage: TokenUsage, provider: str) -> None:
        from uuid import UUID

        task_uuid = UUID(task_id)
        existing = await dapr_state.get_task_runtime_state(task_uuid)
        token_existing = existing.get("token_usage") if existing else None
        token_existing_dict = token_existing if isinstance(token_existing, dict) else None
        merged = merge_token_usage(token_existing_dict, usage)
        await dapr_state.merge_task_runtime_state(task_uuid, {"token_usage": merged})
        logger.debug(
            "accumulated task token usage",
            extra={"task_id": task_id, "provider": provider, "status": merged.get("status")},
        )

    register_token_accumulator(accumulator)


def _sum_optional(left: int | None, right: int | None) -> int | None:
    if left is None and right is None:
        return None
    return (left or 0) + (right or 0)


def _derive_status(
    *,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
) -> TokenUsageStatus:
    values = (prompt_tokens, completion_tokens, total_tokens)
    if all(value is None for value in values):
        return "unknown"
    if all(value is not None for value in values):
        return "known"
    return "partial"


def merge_token_usage(
    existing: dict[str, object] | None,
    incoming: TokenUsage,
) -> dict[str, object]:
    """Merge two token usage snapshots by summing known numeric fields."""
    base = existing or {}
    prompt_tokens = _sum_optional(
        _coerce_int(base.get("prompt_tokens")),
        incoming.prompt_tokens,
    )
    completion_tokens = _sum_optional(
        _coerce_int(base.get("completion_tokens")),
        incoming.completion_tokens,
    )
    total_tokens = _sum_optional(
        _coerce_int(base.get("total_tokens")),
        incoming.total_tokens,
    )
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "status": _derive_status(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        ),
    }


def token_usage_from_runtime(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        return {"status": "unknown"}
    prompt_tokens = _coerce_int(raw.get("prompt_tokens"))
    completion_tokens = _coerce_int(raw.get("completion_tokens"))
    total_tokens = _coerce_int(raw.get("total_tokens"))
    status = raw.get("status")
    if status not in ("known", "partial", "unknown"):
        status = _derive_status(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "status": status,
    }


def accumulate_task_tokens(task_id: str, usage: TokenUsage | None, provider: str) -> None:
    """Schedule per-task token accumulation when a worker callback is registered."""
    if usage is None or _accumulator is None:
        return
    if not any(
        value is not None
        for value in (usage.prompt_tokens, usage.completion_tokens, usage.total_tokens)
    ):
        return

    async def _run() -> None:
        try:
            await _accumulator(task_id, usage, provider)
        except Exception as exc:
            logger.warning(
                "failed to accumulate task token usage",
                extra={"task_id": task_id, "provider": provider, "error": str(exc)},
            )

    try:
        import asyncio

        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        logger.debug(
            "no running event loop for token accumulation",
            extra={"task_id": task_id, "provider": provider},
        )


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None
