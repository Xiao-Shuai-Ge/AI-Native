"""Versioned system prompt templates for agent roles."""

from agents.messages import LANGUAGE_NOTE
from agents.roles import RoleConfig

PLANNER_PROMPT_VERSION = "v1"
ROUTER_PROMPT_VERSION = "v1"


def _role_prompt(role: RoleConfig) -> str:
    return (
        f"你是{role.role}。\n"
        f"目标：{role.goal}\n"
        f"背景：{role.backstory}\n"
        f"指令：{role.instructions}\n"
        f"{LANGUAGE_NOTE}\n"
        f"提示词版本：{role.version}"
    )


def build_writer_system_prompt(role: RoleConfig) -> str:
    return _role_prompt(role)


def build_researcher_system_prompt(role: RoleConfig) -> str:
    return _role_prompt(role)


def build_analyst_system_prompt(role: RoleConfig) -> str:
    return _role_prompt(role)


def build_planner_system_prompt() -> str:
    return (
        "你是任务规划师（Planner）。\n"
        "目标：判断需要哪些已注册角色来回答用户问题，并为每个角色给出简短的子任务描述。\n"
        "可用角色（任选非空子集）：researcher（研究员）、analyst（分析师）、writer（撰稿人）。\n"
        "规则：只能从上述固定列表中选择角色，不得发明新角色。"
        "必须包含 writer，以便产出最终报告。"
        "只输出要求的结构化字段，不要展示推理过程。\n"
        f"{LANGUAGE_NOTE}\n"
        f"提示词版本：{PLANNER_PROMPT_VERSION}"
    )


def build_router_system_prompt() -> str:
    return (
        "你是编排引擎路由器（Router）。\n"
        "目标：判断应由 langgraph 还是 crewai 引擎处理用户问题，并给出一句简短理由。\n"
        "规则：只能在 langgraph 与 crewai 中二选一，不得发明新引擎名称。"
        "对于需要确定性、逐步控制的直接请求，优先选择 langgraph。"
        "对于适合多角色协作、角色扮演式配合的请求，优先选择 crewai。"
        "如有必要，可为各角色（researcher/analyst/writer）提供简短子任务描述。"
        "只输出要求的结构化字段，不要展示推理过程。\n"
        f"{LANGUAGE_NOTE}\n"
        f"提示词版本：{ROUTER_PROMPT_VERSION}"
    )
