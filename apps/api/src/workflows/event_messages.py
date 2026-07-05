"""任务事件与步骤进度的中文展示文案。"""

STEP_LABELS: dict[str, str] = {
    "plan": "任务规划",
    "select_roles": "角色选择",
    "researcher": "资料研究",
    "analyst": "内容分析",
    "writer": "报告撰写",
    "persist_result": "保存结果",
    "task": "任务",
    "scheduling_failed": "调度失败",
    "done": "完成",
}

STATUS_LABELS: dict[str, str] = {
    "queued": "排队中",
    "running": "运行中",
    "paused": "已暂停",
    "succeeded": "已完成",
    "failed": "失败",
    "cancelled": "已取消",
    "completed": "已完成",
    "unknown": "未知",
}


def step_label(step_name: str) -> str:
    return STEP_LABELS.get(step_name, step_name)


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def step_finished_detail(step_name: str) -> str:
    return f"{step_label(step_name)} 已完成"


def task_started_detail() -> str:
    return "任务已开始"


def task_succeeded_detail() -> str:
    return "任务已完成"


def langgraph_node_detail(step_name: str, status: str) -> str:
    return f"LangGraph 节点「{step_label(step_name)}」{status_label(status)}"
