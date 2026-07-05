"""Builds real CrewAI `Agent`/`Task` objects from the shared role registry.

Each role's `RoleConfig.instructions` and `expected_output` schema are baked
into the Task description as an explicit JSON-response instruction, mirroring
`llm.openai_compatible.OpenAICompatibleClient.chat_structured`'s prompt-based
structured output technique (see `parsing.py`). Tool-calling (when the role
has a `tool_allowlist`) is handled entirely inside `CrewAILLMBridge.call()`
via the shared `agents.tool_loop`, not CrewAI's native `Agent(tools=...)`
mechanism, so `Agent` here intentionally never receives a `tools=` argument.
"""

from __future__ import annotations

import json

from crewai import Agent, Task
from pydantic import BaseModel

from agents.roles import RoleConfig
from orchestration.crewai_engine.llm_bridge import CrewAILLMBridge


def build_agent(role: RoleConfig, llm_bridge: CrewAILLMBridge) -> Agent:
    return Agent(
        role=role.role,
        goal=role.goal,
        backstory=role.backstory,
        llm=llm_bridge,
        allow_delegation=False,
        verbose=False,
    )


def build_task(
    *,
    role: RoleConfig,
    agent: Agent,
    description_body: str,
    schema: type[BaseModel],
) -> Task:
    schema_hint = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    description = (
        f"{role.instructions}\n\n{description_body}\n\n"
        "请仅返回合法 JSON，不要包含 markdown 代码块或额外说明。"
        f"JSON 必须符合以下 schema：{schema_hint}"
    )
    return Task(
        description=description,
        expected_output=f"符合 {schema.__name__} schema 的 JSON 对象",
        agent=agent,
    )
