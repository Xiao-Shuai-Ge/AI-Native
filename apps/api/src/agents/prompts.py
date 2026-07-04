"""Versioned system prompt templates for agent roles."""

from agents.roles import RoleConfig

PLANNER_PROMPT_VERSION = "v1"


def _role_prompt(role: RoleConfig) -> str:
    return (
        f"You are a {role.role}.\n"
        f"Goal: {role.goal}\n"
        f"Backstory: {role.backstory}\n"
        f"Instructions: {role.instructions}\n"
        f"Prompt version: {role.version}"
    )


def build_writer_system_prompt(role: RoleConfig) -> str:
    return _role_prompt(role)


def build_researcher_system_prompt(role: RoleConfig) -> str:
    return _role_prompt(role)


def build_analyst_system_prompt(role: RoleConfig) -> str:
    return _role_prompt(role)


def build_planner_system_prompt() -> str:
    return (
        "You are the task Planner.\n"
        "Goal: Decide which of the registered roles are needed to answer the "
        "user's query and give each a short subtask description.\n"
        "Available roles (choose any non-empty subset): researcher, analyst, writer.\n"
        "Rules: Only choose roles from this fixed list, never invent new roles. "
        "Always include 'writer' so a final report can be produced. Only output "
        "the structured fields requested; do not reveal your reasoning process.\n"
        f"Prompt version: {PLANNER_PROMPT_VERSION}"
    )
