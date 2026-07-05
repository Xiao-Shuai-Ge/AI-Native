import type { EngineChoice, TaskStatus } from "../api/types";

const STATUS_LABELS: Record<TaskStatus | "completed", string> = {
  queued: "排队中",
  running: "运行中",
  paused: "已暂停",
  succeeded: "已完成",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

const STEP_LABELS: Record<string, string> = {
  plan: "任务规划",
  select_roles: "角色选择",
  researcher: "资料研究",
  analyst: "内容分析",
  writer: "报告撰写",
  persist_result: "保存结果",
  task: "任务",
  scheduling_failed: "调度失败",
  done: "完成",
  initialize_task: "初始化",
};

const ENGINE_LABELS: Record<EngineChoice, string> = {
  auto: "自动选择",
  langgraph: "LangGraph",
  crewai: "CrewAI",
};

const AGENT_LABELS: Record<string, string> = {
  researcher: "研究员",
  analyst: "分析师",
  writer: "撰稿人",
};

const AGENT_FIELD_LABELS: Record<string, string> = {
  role: "角色",
  goal: "目标",
  backstory: "背景",
  instructions: "指令",
};

const TOOL_LABELS: Record<string, string> = {
  calculator: "计算器",
  web_search: "网络搜索",
  code_runner: "代码沙箱",
  readonly_sql: "只读 SQL",
};

export function formatStatus(status: string): string {
  return STATUS_LABELS[status as TaskStatus | "completed"] ?? status;
}

export function formatStep(step: string): string {
  return STEP_LABELS[step] ?? step;
}

export function formatEngine(engine: string): string {
  return ENGINE_LABELS[engine as EngineChoice] ?? engine;
}

export function formatAgentKey(key: string): string {
  return AGENT_LABELS[key] ?? key;
}

export function formatAgentField(field: string): string {
  return AGENT_FIELD_LABELS[field] ?? field;
}

export function formatToolName(name: string): string {
  return TOOL_LABELS[name] ?? name;
}
