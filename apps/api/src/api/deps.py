"""Application state and dependency wiring."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from api.config import Settings
from events.broadcaster import TaskEventBroadcaster
from events.handler import AgentTaskEventHandler
from events.schemas import AgentTaskEventPublisher
from observability.task_tokens import clear_token_accumulator, register_dapr_token_accumulator
from persistence.dapr_client import DaprHttpClient
from persistence.dapr_state import DaprStateStore
from persistence.database import create_engine, create_session_factory
from persistence.session_store import SessionStore
from workflows.client import WorkflowScheduler


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
    event_broadcaster: TaskEventBroadcaster
    workflow_scheduler: WorkflowScheduler


def build_app_state(settings: Settings) -> AppState:
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    dapr_client = DaprHttpClient(http_port=settings.dapr_http_port)
    dapr_state = DaprStateStore(dapr_client)
    register_dapr_token_accumulator(dapr_state)
    event_broadcaster = TaskEventBroadcaster()
    return AppState(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        dapr_client=dapr_client,
        dapr_state=dapr_state,
        session_store=SessionStore.from_settings(settings),
        event_publisher=AgentTaskEventPublisher(dapr_client),
        event_handler=AgentTaskEventHandler(
            session_factory,
            broadcaster=event_broadcaster,
        ),
        event_broadcaster=event_broadcaster,
        workflow_scheduler=WorkflowScheduler(
            grpc_host=settings.workflow_dapr_grpc_host,
            grpc_port=settings.workflow_dapr_grpc_port or settings.dapr_grpc_port,
        ),
    )


async def shutdown_app_state(state: AppState) -> None:
    clear_token_accumulator()
    state.workflow_scheduler.close()
    await state.dapr_client.aclose()
    await state.session_store.aclose()
    await state.engine.dispose()
