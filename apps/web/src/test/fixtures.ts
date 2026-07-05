import type { TaskDetail, TaskMetrics } from "../api/types";

export const defaultMetrics: TaskMetrics = {
  tool_calls_total: 0,
  tool_calls_succeeded: 0,
  tool_calls_failed: 0,
  token_usage: {
    prompt_tokens: null,
    completion_tokens: null,
    total_tokens: null,
    status: "unknown",
  },
  trace_id: null,
};

export function createMockTaskDetail(overrides: Partial<TaskDetail> = {}): TaskDetail {
  return {
    task_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    session_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    user_id: "default",
    user_query: "测试任务",
    engine_requested: "auto",
    engine_selected: "langgraph",
    engine_selection_reason: "structured workflow",
    status: "running",
    workflow_id: "wf-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    thread_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    report: null,
    created_at: "2026-07-05T00:00:00.000Z",
    updated_at: "2026-07-05T00:00:01.000Z",
    steps: [],
    audit_events: [],
    tool_calls: [],
    metrics: defaultMetrics,
    messages: [],
    runtime_state: null,
    user_preferences: null,
    session_context: null,
    ...overrides,
  };
}
