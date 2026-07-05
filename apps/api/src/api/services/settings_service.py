"""Runtime settings backed by Dapr State with code defaults as fallback."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from agents.roles import ROLE_REGISTRY, RoleConfig
from api.config import Settings
from api.schemas.settings import (
    ALLOWED_LLM_PROVIDERS,
    AgentRoleSettings,
    LLMProviderChoice,
    LLMSettings,
    RuntimeSettingsResponse,
)
from persistence.dapr_client import DaprHttpClient

logger = logging.getLogger(__name__)

RUNTIME_SETTINGS_KEY = "settings:runtime"
ALLOWED_AGENT_KEYS = frozenset(ROLE_REGISTRY)


class SettingsService:
    def __init__(self, dapr: DaprHttpClient, settings: Settings) -> None:
        self._dapr = dapr
        self._settings = settings

    def _default_llm(self) -> LLMSettings:
        raw = str(self._settings.llm_provider).strip().lower()
        provider: LLMProviderChoice = (
            raw if raw in ALLOWED_LLM_PROVIDERS else "deepseek"  # type: ignore[assignment]
        )
        return LLMSettings(
            provider=provider,
            temperature=0.7,
            max_tokens=4096,
        )

    def _default_agents(self) -> dict[str, AgentRoleSettings]:
        return {
            key: AgentRoleSettings(
                role=role.role,
                goal=role.goal,
                backstory=role.backstory,
                instructions=role.instructions,
                version=role.version,
            )
            for key, role in ROLE_REGISTRY.items()
        }

    async def get_settings(self) -> RuntimeSettingsResponse:
        stored = await self._dapr.get_state(RUNTIME_SETTINGS_KEY) or {}
        llm_data = stored.get("llm") if isinstance(stored.get("llm"), dict) else {}
        agents_data = stored.get("agents") if isinstance(stored.get("agents"), dict) else {}

        llm_payload: dict[str, Any] = {**self._default_llm().model_dump(), **llm_data}
        try:
            llm = LLMSettings.model_validate(llm_payload)
        except ValidationError:
            llm = self._default_llm()
        agents = self._default_agents()
        for key, value in agents_data.items():
            if key in ALLOWED_AGENT_KEYS and isinstance(value, dict):
                try:
                    agents[key] = AgentRoleSettings.model_validate(value)
                except ValidationError:
                    logger.warning(
                        "invalid agent settings in runtime state; using default",
                        extra={"agent_key": key},
                    )
        return RuntimeSettingsResponse(llm=llm, agents=agents)

    def role_registry_from_settings(
        self,
        runtime: RuntimeSettingsResponse,
    ) -> dict[str, RoleConfig]:
        # `tool_allowlist` is fixed per role (AGENTS.md section 7: explicit
        # allowlist only) and is never one of the fields the settings page
        # lets users edit (role/goal/backstory/instructions/model params), so
        # it always comes from the code-defined `ROLE_REGISTRY`, not from
        # user-controlled runtime settings.
        return {
            key: RoleConfig(
                role=runtime.agents[key].role,
                goal=runtime.agents[key].goal,
                backstory=runtime.agents[key].backstory,
                instructions=runtime.agents[key].instructions,
                version=runtime.agents[key].version,
                tool_allowlist=list(ROLE_REGISTRY[key].tool_allowlist),
            )
            for key in ALLOWED_AGENT_KEYS
        }

    async def update_settings(
        self,
        *,
        llm: LLMSettings | None = None,
        agents: dict[str, AgentRoleSettings] | None = None,
    ) -> RuntimeSettingsResponse:
        current = await self.get_settings()
        merged_llm = current.llm if llm is None else llm
        merged_agents = dict(current.agents)
        if agents is not None:
            for key, value in agents.items():
                if key not in ALLOWED_AGENT_KEYS:
                    msg = f"unknown agent role: {key}"
                    raise ValueError(msg)
                merged_agents[key] = value

        payload: dict[str, Any] = {
            "llm": merged_llm.model_dump(),
            "agents": {key: value.model_dump() for key, value in merged_agents.items()},
        }
        await self._dapr.save_state(RUNTIME_SETTINGS_KEY, payload)
        return RuntimeSettingsResponse(llm=merged_llm, agents=merged_agents)

    async def get_role_config(self, role_key: str) -> RoleConfig:
        runtime = await self.get_settings()
        agent = runtime.agents.get(role_key)
        if agent is None:
            return ROLE_REGISTRY[role_key]
        return RoleConfig(
            role=agent.role,
            goal=agent.goal,
            backstory=agent.backstory,
            instructions=agent.instructions,
            version=agent.version,
        )

    async def get_role_registry(self) -> dict[str, RoleConfig]:
        return self.role_registry_from_settings(await self.get_settings())
