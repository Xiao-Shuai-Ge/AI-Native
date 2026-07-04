"""Dapr Pub/Sub subscription routes."""

from typing import Any

from fastapi import APIRouter, Request, Response

router = APIRouter(prefix="/dapr", tags=["dapr"])


@router.get("/subscribe")
async def dapr_subscribe() -> list[dict[str, str]]:
    return [
        {
            "pubsubname": "pubsub",
            "topic": "agent.task.events",
            "route": "/dapr/agent-task-events",
        }
    ]


@router.post("/agent-task-events")
async def handle_agent_task_event(request: Request) -> Response:
    envelope: dict[str, Any] = await request.json()
    state = request.app.state.app_state
    created = await state.event_handler.handle_dapr_envelope(envelope)
    if created:
        return Response(status_code=200)
    return Response(status_code=200)
