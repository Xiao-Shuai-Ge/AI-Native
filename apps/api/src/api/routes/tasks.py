"""Task CRUD routes."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from api.schemas.tasks import (
    CreateTaskRequest,
    CreateTaskResponse,
    TaskControlResponse,
    TaskDetailResponse,
    TaskSummaryResponse,
)
from api.services.task_service import TaskService, WorkflowScheduleError
from orchestration.models import TaskRequest

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _task_service(request: Request) -> TaskService:
    state = request.app.state.app_state
    return TaskService(
        state.session_factory,
        state.dapr_state,
        state.session_store,
        state.event_publisher,
        state.workflow_scheduler,
        default_delay_seconds=state.settings.task_delay_seconds,
    )


@router.post("", response_model=CreateTaskResponse, status_code=201)
async def create_task(body: CreateTaskRequest, request: Request) -> CreateTaskResponse:
    service = _task_service(request)
    try:
        result = await service.create_task(
            TaskRequest(
                task_id=body.task_id,
                session_id=body.session_id,
                user_id=body.user_id,
                user_query=body.user_query,
                engine=body.engine,
                delay_seconds=body.delay_seconds,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WorkflowScheduleError as exc:
        raise HTTPException(
            status_code=503,
            detail={"task_id": str(exc.task_id), "message": str(exc)},
        ) from exc
    return CreateTaskResponse.model_validate(result)


@router.get("", response_model=list[TaskSummaryResponse])
async def list_tasks(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[TaskSummaryResponse]:
    service = _task_service(request)
    tasks = await service.list_tasks(limit=limit, offset=offset)
    return [
        TaskSummaryResponse(
            task_id=item["task_id"],  # type: ignore[arg-type]
            session_id=item.get("session_id"),  # type: ignore[arg-type]
            user_id=str(item["user_id"]),
            user_query=str(item["user_query"]),
            engine_requested=str(item["engine_requested"]),
            engine_selected=item.get("engine_selected"),  # type: ignore[arg-type]
            status=str(item["status"]),
            workflow_id=str(item["workflow_id"]),
            thread_id=str(item["thread_id"]),
            report=item.get("report"),  # type: ignore[arg-type]
            created_at=item["created_at"],  # type: ignore[arg-type]
            updated_at=item["updated_at"],  # type: ignore[arg-type]
        )
        for item in tasks
    ]


@router.get("/{task_id}", response_model=TaskDetailResponse)
async def get_task(task_id: UUID, request: Request) -> TaskDetailResponse:
    service = _task_service(request)
    task = await service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    runtime = task.pop("runtime_state", None)
    preferences = None
    session_context = None
    if isinstance(runtime, dict):
        pref = runtime.get("user_preferences")
        if isinstance(pref, dict):
            preferences = pref
        ctx = runtime.get("session_context")
        if isinstance(ctx, list):
            session_context = [item for item in ctx if isinstance(item, dict)]
    payload = {
        **task,
        "runtime_state": runtime if isinstance(runtime, dict) else None,
        "user_preferences": preferences,
        "session_context": session_context,
    }
    return TaskDetailResponse.model_validate(payload)


@router.post("/{task_id}/pause", response_model=TaskControlResponse)
async def pause_task(task_id: UUID, request: Request) -> TaskControlResponse:
    service = _task_service(request)
    try:
        result = await service.pause_task(task_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return TaskControlResponse.model_validate(result)


@router.post("/{task_id}/resume", response_model=TaskControlResponse)
async def resume_task(task_id: UUID, request: Request) -> TaskControlResponse:
    service = _task_service(request)
    try:
        result = await service.resume_task(task_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return TaskControlResponse.model_validate(result)
