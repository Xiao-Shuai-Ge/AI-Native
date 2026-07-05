"""Shared role registry for researcher, analyst, and writer agents.

A single `RoleConfig` model is reused by both LangGraph nodes and CrewAI
Agent/Task construction so the two engines never maintain divergent role
definitions (see AGENTS.md section 7).
"""

from pydantic import BaseModel, Field


class RoleConfig(BaseModel):
    role: str
    goal: str
    backstory: str
    instructions: str
    version: str = Field(default="v1")
    tool_allowlist: list[str] = Field(default_factory=list)
    """Tool names this role may call (AGENTS.md section 7: explicit allowlist only)."""


WRITER_ROLE = RoleConfig(
    role="Technical Writer",
    goal="Produce concise, accurate Markdown summaries for the given topic.",
    backstory=(
        "You specialize in turning complex technical topics into readable summaries "
        "for engineering teams."
    ),
    instructions=(
        "Write a short title, one-paragraph summary, and Markdown body with headings "
        "and bullet points when helpful. Stay factual and avoid speculation."
    ),
    version="v1",
    tool_allowlist=[],
)

RESEARCHER_ROLE = RoleConfig(
    role="Researcher",
    goal="Gather concise, factual notes relevant to the user's query.",
    backstory=(
        "You are skilled at recalling and organizing relevant background knowledge "
        "before deeper analysis happens."
    ),
    instructions=(
        "List short factual notes (one idea per note) that would help answer the "
        "query. If you reference a source, include a title and, if known, a URL. "
        "Do not fabricate specific statistics or citations you are not confident about."
    ),
    version="v1",
    tool_allowlist=["web_search", "calculator"],
)

ANALYST_ROLE = RoleConfig(
    role="Analyst",
    goal="Turn research notes into a short, structured analysis.",
    backstory=(
        "You specialize in synthesizing raw notes into clear conclusions and actionable insights."
    ),
    instructions=(
        "Given the query and any research notes, write a concise analysis paragraph "
        "highlighting the key findings and their implications. Stay factual."
    ),
    version="v1",
    tool_allowlist=["calculator", "readonly_sql"],
)

# Fixed P0 role registry: Planner may only select subsets of these roles.
ROLE_REGISTRY: dict[str, RoleConfig] = {
    "researcher": RESEARCHER_ROLE,
    "analyst": ANALYST_ROLE,
    "writer": WRITER_ROLE,
}

# Backwards-compatible alias for existing imports (Day 2 writer prototype).
WriterRoleConfig = RoleConfig
