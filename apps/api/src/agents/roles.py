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
    role="技术撰稿人",
    goal="为给定主题撰写简洁、准确的 Markdown 摘要。",
    backstory="你擅长将复杂技术话题转化为工程团队易读的摘要。",
    instructions=("撰写简短标题、一段摘要，以及带标题与要点的 Markdown 正文。保持客观，避免推测。"),
    version="v1",
    tool_allowlist=[],
)

RESEARCHER_ROLE = RoleConfig(
    role="研究员",
    goal="收集与用户问题相关的简洁、事实性笔记。",
    backstory="你擅长在深入分析之前回忆并组织相关背景知识。",
    instructions=(
        "列出有助于回答问题的简短事实笔记（每条一个要点）。"
        "若引用来源，请附上标题及已知 URL。"
        "不要编造没有把握的统计数据或引用。"
    ),
    version="v1",
    tool_allowlist=["web_search", "calculator"],
)

ANALYST_ROLE = RoleConfig(
    role="分析师",
    goal="将研究笔记转化为简短、结构化的分析。",
    backstory="你擅长将原始笔记综合为清晰结论与可行洞察。",
    instructions=("根据问题及研究笔记，写出简洁分析段落，突出关键发现及其含义。保持客观。"),
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
