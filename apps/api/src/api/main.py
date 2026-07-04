"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response

from api.config import get_settings
from api.deps import build_app_state, shutdown_app_state
from api.routes.dapr_subscribe import router as dapr_router
from api.routes.dev_writer import router as dev_writer_router
from api.routes.health import router as health_router
from api.routes.preferences import router as preferences_router
from api.routes.providers import router as providers_router
from api.routes.tasks import router as tasks_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.app_state = build_app_state(settings)
    yield
    await shutdown_app_state(app.state.app_state)


app = FastAPI(
    title="AI Native API",
    version="0.2.0",
    description="Multi-agent collaboration platform API",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(dev_writer_router)
app.include_router(providers_router)
app.include_router(tasks_router)
app.include_router(preferences_router)
app.include_router(dapr_router)


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics stub for Day 1."""
    return Response(
        content="# HELP api_up API process is running.\n# TYPE api_up gauge\napi_up 1\n",
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
