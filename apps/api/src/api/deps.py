"""Application state and dependency wiring."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from api.config import Settings
from events.handler import AgentTaskEventHandler
from events.schemas import AgentTaskEventPublisher
from persistence.dapr_client import DaprHttpClient
from persistence.dapr_state import DaprStateStore
from persistence.database import create_engine, create_session_factory
from persistence.session_store import SessionStore


@dataclass
class AppState:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    dapr_client: DaprHttpClient
    dapr_state: DaprStateStore
    session_store: SessionStore
    event_publisher: AgentTaskEventPublisher
    event_handler: AgentTaskEventHandler


def build_app_state(settings: Settings) -> AppState:
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    dapr_client = DaprHttpClient(http_port=settings.dapr_http_port)
    return AppState(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        dapr_client=dapr_client,
        dapr_state=DaprStateStore(dapr_client),
        session_store=SessionStore.from_settings(settings),
        event_publisher=AgentTaskEventPublisher(dapr_client),
        event_handler=AgentTaskEventHandler(session_factory),
    )


async def shutdown_app_state(state: AppState) -> None:
    await state.dapr_client.aclose()
    await state.session_store.aclose()
    await state.engine.dispose()
