"""LLM provider information routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from api.config import Settings, get_settings
from llm.errors import LLMConfigurationError
from llm.factory import create_llm_client
from llm.protocol import LLMProviderInfo

router = APIRouter(prefix="/api", tags=["providers"])


@router.get("/providers", response_model=LLMProviderInfo)
async def get_providers(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LLMProviderInfo:
    try:
        llm = create_llm_client(settings)
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return llm.provider_info
