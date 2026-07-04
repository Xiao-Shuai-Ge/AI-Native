"""User preference routes."""

from fastapi import APIRouter, Request

from api.schemas.preferences import UpdateUserPreferencesRequest, UserPreferencesResponse
from persistence.repository import TaskRepository

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/{user_id}/preferences", response_model=UserPreferencesResponse)
async def get_user_preferences(user_id: str, request: Request) -> UserPreferencesResponse:
    state = request.app.state.app_state
    async with state.session_factory() as session:
        repo = TaskRepository(session)
        preferences = await repo.get_user_preferences(user_id)
    return UserPreferencesResponse(user_id=user_id, preferences=preferences)


@router.put("/{user_id}/preferences", response_model=UserPreferencesResponse)
async def update_user_preferences(
    user_id: str,
    body: UpdateUserPreferencesRequest,
    request: Request,
) -> UserPreferencesResponse:
    state = request.app.state.app_state
    async with state.session_factory() as session:
        repo = TaskRepository(session)
        record = await repo.upsert_user_preferences(user_id, body.preferences)
        await session.commit()
    return UserPreferencesResponse(user_id=record.user_id, preferences=dict(record.preferences))
