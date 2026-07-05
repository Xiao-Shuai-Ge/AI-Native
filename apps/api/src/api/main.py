"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from api.config import get_settings
from api.deps import build_app_state, shutdown_app_state
from api.routes.dapr_subscribe import router as dapr_router
from api.routes.dev_writer import router as dev_writer_router
from api.routes.health import router as health_router
from api.routes.preferences import router as preferences_router
from api.routes.providers import router as providers_router
from api.routes.settings import router as settings_router
from api.routes.tasks import router as tasks_router
from api.routes.tools import router as tools_router
from observability import init_observability
from observability.metrics import render_metrics

_settings = get_settings()
init_observability(_settings, "api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.app_state = build_app_state(get_settings())
    yield
    await shutdown_app_state(app.state.app_state)


app = FastAPI(
    title="AI Native API",
    version="0.2.0",
    description="Multi-agent collaboration platform API",
    lifespan=lifespan,
)

FastAPIInstrumentor.instrument_app(app)

app.include_router(health_router)
app.include_router(dev_writer_router)
app.include_router(providers_router)
app.include_router(settings_router)
app.include_router(tasks_router)
app.include_router(preferences_router)
app.include_router(dapr_router)
app.include_router(tools_router)


@app.get("/metrics")
async def metrics() -> Response:
    content, content_type = render_metrics()
    return Response(content=content, media_type=content_type)
