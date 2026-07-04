"""Writer agent prompt templates."""

from agents.roles import WriterRoleConfig


def build_writer_system_prompt(role: WriterRoleConfig) -> str:
    return (
        f"You are a {role.role}.\n"
        f"Goal: {role.goal}\n"
        f"Backstory: {role.backstory}\n"
        f"Instructions: {role.instructions}\n"
        f"Prompt version: {role.version}"
    )
