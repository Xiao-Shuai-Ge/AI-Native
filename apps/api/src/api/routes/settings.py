"""Runtime settings routes."""

from fastapi import APIRouter, HTTPException, Request

from api.schemas.settings import RuntimeSettingsResponse, UpdateRuntimeSettingsRequest
from api.services.settings_service import SettingsService

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _settings_service(request: Request) -> SettingsService:
    state = request.app.state.app_state
    return SettingsService(state.dapr_client, state.settings)


@router.get("", response_model=RuntimeSettingsResponse)
async def get_settings(request: Request) -> RuntimeSettingsResponse:
    service = _settings_service(request)
    return await service.get_settings()


@router.put("", response_model=RuntimeSettingsResponse)
async def update_settings(
    body: UpdateRuntimeSettingsRequest,
    request: Request,
) -> RuntimeSettingsResponse:
    service = _settings_service(request)
    try:
        return await service.update_settings(llm=body.llm, agents=body.agents)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
