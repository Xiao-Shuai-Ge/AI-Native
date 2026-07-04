"""FastAPI application entrypoint."""

from fastapi import FastAPI, Response

from api.routes.dev_writer import router as dev_writer_router
from api.routes.health import router as health_router
from api.routes.providers import router as providers_router

app = FastAPI(
    title="AI Native API",
    version="0.1.0",
    description="Multi-agent collaboration platform API",
)

app.include_router(health_router)
app.include_router(dev_writer_router)
app.include_router(providers_router)


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics stub for Day 1."""
    return Response(
        content="# HELP api_up API process is running.\n# TYPE api_up gauge\napi_up 1\n",
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
