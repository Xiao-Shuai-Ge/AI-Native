export type EngineChoice = "auto" | "langgraph" | "crewai";

export type TaskStatus =
  | "queued"
  | "running"
  | "paused"
  | "succeeded"
  | "failed"
  | "cancelled";

export type AuditEvent = {
  id: string;
  engine: string;
  step: string;
  status: string;
  payload: Record<string, unknown>;
  event_time: string;
};

export type TaskStep = {
  id: string;
  step_name: string;
  status: string;
  output_json: Record<string, unknown> | null;
  created_at: string;
};

export type TaskSummary = {
  task_id: string;
  session_id: string | null;
  user_id: string;
  user_query: string;
  engine_requested: string;
  engine_selected: string | null;
  status: TaskStatus;
  workflow_id: string;
  thread_id: string;
  report: string | null;
  created_at: string;
  updated_at: string;
};

export type TaskDetail = TaskSummary & {
  engine_selection_reason: string | null;
  steps: TaskStep[];
  audit_events: AuditEvent[];
  messages: Array<{ id: string; role: string; content: string; created_at: string }>;
  runtime_state: Record<string, unknown> | null;
  user_preferences: Record<string, unknown> | null;
  session_context: Array<Record<string, unknown>> | null;
};

export type CreateTaskResponse = {
  task_id: string;
  session_id: string;
  workflow_id: string;
  thread_id: string;
  status: TaskStatus;
  engine_requested: EngineChoice;
  user_preferences: Record<string, unknown>;
  session_context: Array<Record<string, unknown>>;
};

export type TaskControlResponse = {
  task_id: string;
  workflow_id: string;
  status: TaskStatus;
};

export type AgentRoleSettings = {
  role: string;
  goal: string;
  backstory: string;
  instructions: string;
  version: string;
};

export type LLMSettings = {
  provider: string;
  temperature: number;
  max_tokens: number;
};

export type RuntimeSettings = {
  llm: LLMSettings;
  agents: Record<string, AgentRoleSettings>;
};

export type LLMProviderInfo = {
  provider: string;
  model: string;
  capabilities: {
    supports_streaming: boolean;
    supports_tools: boolean;
    supports_structured_output: boolean;
    max_context_tokens: number | null;
  };
};

export type TaskEventSnapshot = {
  task_id: string;
  status: TaskStatus;
  audit_events: AuditEvent[];
};

export type TaskSseEvent = {
  task_id: string;
  engine: string;
  step: string;
  status: string;
  timestamp: string;
  detail: string | null;
  payload: Record<string, unknown>;
};
