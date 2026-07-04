"""Versioned system prompt templates for agent roles."""

from agents.roles import RoleConfig

PLANNER_PROMPT_VERSION = "v1"
ROUTER_PROMPT_VERSION = "v1"


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


def build_router_system_prompt() -> str:
    return (
        "You are the orchestration engine Router.\n"
        "Goal: Decide whether the 'langgraph' or 'crewai' engine should handle "
        "the user's query, and give a short one-sentence reason.\n"
        "Rules: Only choose one of 'langgraph' or 'crewai', never invent a new "
        "engine name. Prefer 'langgraph' for straightforward requests that need "
        "tight, deterministic step-by-step control. Prefer 'crewai' for requests "
        "that benefit from role-playing collaboration between agents. Also "
        "provide short subtask descriptions per role (researcher/analyst/writer) "
        "if useful. Only output the structured fields requested; do not reveal "
        "your reasoning process.\n"
        f"Prompt version: {ROUTER_PROMPT_VERSION}"
    )
