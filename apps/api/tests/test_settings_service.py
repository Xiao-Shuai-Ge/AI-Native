"""Settings service unit tests."""

from unittest.mock import AsyncMock, patch

import pytest

from api.config import Settings
from api.services.settings_service import SettingsService
from persistence.dapr_client import DaprHttpClient


@pytest.mark.asyncio
async def test_get_settings_falls_back_when_llm_state_is_invalid() -> None:
    service = SettingsService(
        DaprHttpClient(http_port=3500),
        Settings.model_validate({"llm_provider": "deepseek"}),
    )
    with patch.object(
        DaprHttpClient,
        "get_state",
        new=AsyncMock(return_value={"llm": {"temperature": 99.0}}),
    ):
        settings = await service.get_settings()

    assert settings.llm.provider == "deepseek"
    assert settings.llm.temperature == 0.7


@pytest.mark.asyncio
async def test_get_settings_falls_back_when_agent_state_is_invalid() -> None:
    service = SettingsService(
        DaprHttpClient(http_port=3500),
        Settings.model_validate({"llm_provider": "deepseek"}),
    )
    with patch.object(
        DaprHttpClient,
        "get_state",
        new=AsyncMock(
            return_value={
                "agents": {
                    "writer": {
                        "role": "",
                        "goal": "bad",
                        "backstory": "bad",
                        "instructions": "bad",
                    }
                }
            }
        ),
    ):
        settings = await service.get_settings()

    assert settings.agents["writer"].role == "技术撰稿人"


@pytest.mark.asyncio
async def test_get_role_registry_returns_runtime_overrides() -> None:
    stored = {
        "llm": {"provider": "deepseek", "temperature": 0.7, "max_tokens": 4096},
        "agents": {
            "writer": {
                "role": "Custom Writer",
                "goal": "Custom goal",
                "backstory": "Custom backstory",
                "instructions": "Custom instructions",
                "version": "v9",
            }
        },
    }
    service = SettingsService(
        DaprHttpClient(http_port=3500),
        Settings.model_validate({"llm_provider": "deepseek"}),
    )
    with patch.object(DaprHttpClient, "get_state", new=AsyncMock(return_value=stored)):
        registry = await service.get_role_registry()

    assert registry["writer"].role == "Custom Writer"
    assert registry["writer"].version == "v9"
    assert registry["researcher"].role == "研究员"
