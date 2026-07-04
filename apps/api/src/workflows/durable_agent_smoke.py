"""Minimal DurableAgent factory for Day 4 smoke testing."""

from __future__ import annotations

from typing import Any

from dapr.ext.workflow import WorkflowRuntime
from dapr_agents import DurableAgent
from dapr_agents.agents.configs import AgentMemoryConfig, AgentStateConfig
from dapr_agents.llm import DaprChatClient
from dapr_agents.memory import ConversationDaprStateMemory
from dapr_agents.storage.daprstores.stateservice import StateStoreService

SMOKE_AGENT_NAME = "durable-agent-smoke"


def build_smoke_durable_agent(
    workflow_runtime: WorkflowRuntime | None = None,
    *,
    llm_component: str = "conversation-deepseek",
    state_store: str = "statestore",
) -> DurableAgent:
    """Build a minimal DurableAgent wired to Dapr Conversation and State."""
    llm: Any = DaprChatClient(component_name=llm_component)  # type: ignore[abstract]
    memory = AgentMemoryConfig(
        store=ConversationDaprStateMemory(
            store_name=state_store,
            agent_name=SMOKE_AGENT_NAME,
        )
    )
    state = AgentStateConfig(
        store=StateStoreService(store_name=state_store),
    )
    kwargs: dict[str, Any] = {
        "name": SMOKE_AGENT_NAME,
        "role": "SmokeAssistant",
        "instructions": ["Respond briefly to smoke-test prompts."],
        "llm": llm,
        "memory": memory,
        "state": state,
    }
    if workflow_runtime is not None:
        kwargs["runtime"] = workflow_runtime
    return DurableAgent(**kwargs)
