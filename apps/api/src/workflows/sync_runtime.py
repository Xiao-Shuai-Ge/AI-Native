"""Bridge async persistence/Dapr clients into Dapr Workflow Activity workers."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from api.config import Settings, get_settings
from events.schemas import AgentTaskEventPublisher
from persistence.dapr_client import DaprHttpClient
from persistence.dapr_state import DaprStateStore
from persistence.database import create_engine, create_session_factory

logger = logging.getLogger(__name__)


@dataclass
class ActivityRuntime:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    dapr_state: DaprStateStore
    event_publisher: AgentTaskEventPublisher
    loop: asyncio.AbstractEventLoop


_runtime: ActivityRuntime | None = None


def init_activity_runtime(settings: Settings | None = None) -> ActivityRuntime:
    global _runtime
    if _runtime is not None:
        return _runtime

    resolved = settings or get_settings()
    engine = create_engine(resolved)
    session_factory = create_session_factory(engine)
    dapr_client = DaprHttpClient(http_port=resolved.dapr_http_port)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    _runtime = ActivityRuntime(
        settings=resolved,
        engine=engine,
        session_factory=session_factory,
        dapr_state=DaprStateStore(dapr_client),
        event_publisher=AgentTaskEventPublisher(dapr_client),
        loop=loop,
    )
    logger.info("activity runtime initialized")
    return _runtime


def get_activity_runtime() -> ActivityRuntime:
    if _runtime is None:
        msg = "activity runtime not initialized; call init_activity_runtime() first"
        raise RuntimeError(msg)
    return _runtime


def run_async(coro: object) -> object:
    """Run an async coroutine on the worker's dedicated event loop."""
    runtime = get_activity_runtime()
    if not asyncio.iscoroutine(coro):
        msg = "run_async expects a coroutine"
        raise TypeError(msg)
    return runtime.loop.run_until_complete(coro)


async def shutdown_activity_runtime() -> None:
    global _runtime
    if _runtime is None:
        return
    await _runtime.engine.dispose()
    _runtime.loop.close()
    _runtime = None
    logger.info("activity runtime shut down")


def shutdown_activity_runtime_sync() -> None:
    if _runtime is None:
        return
    run_async(shutdown_activity_runtime())
