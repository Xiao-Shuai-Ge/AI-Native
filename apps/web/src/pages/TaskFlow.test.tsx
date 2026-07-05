import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createMockTaskDetail } from "../test/fixtures";
import { NewTaskPage } from "./NewTaskPage";
import { TaskDetailPage } from "./TaskDetailPage";

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  onerror: (() => void) | null = null;
  close = vi.fn();
  private handlers = new Map<string, (message: MessageEvent) => void>();

  constructor(url: string) {
    FakeEventSource.instances.push(this);
    void url;
  }

  addEventListener(type: string, handler: (message: MessageEvent) => void): void {
    this.handlers.set(type, handler);
  }

  dispatch(type: string, data?: string): void {
    const handler = this.handlers.get(type);
    if (handler) {
      handler({ data: data ?? "{}" } as MessageEvent);
    }
  }
}

const taskId = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const navigateMock = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock("../api/providers", () => ({
  getProviders: vi.fn().mockResolvedValue({
    provider: "deepseek",
    model: "deepseek-chat",
    capabilities: {},
  }),
}));

vi.mock("../api/tools", () => ({
  listTools: vi.fn().mockResolvedValue({
    tools: [{ name: "calculator", description: "Math", input_schema: {} }],
  }),
}));

vi.mock("../api/tasks", () => ({
  createTask: vi.fn(),
  getTask: vi.fn(),
  pauseTask: vi.fn(),
  resumeTask: vi.fn(),
  taskEventsUrl: (id: string) => `/api/tasks/${id}/events`,
}));

describe("TaskFlow", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    navigateMock.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("covers create, SSE refresh, remount and pause/resume", async () => {
    const { createTask, getTask, pauseTask, resumeTask } = await import("../api/tasks");

    vi.mocked(createTask).mockResolvedValue({
      task_id: taskId,
      session_id: "session-1",
      workflow_id: `wf-${taskId}`,
      thread_id: taskId,
      status: "queued",
      engine_requested: "auto",
      user_preferences: {},
      session_context: [],
    });

    let auditCount = 1;
    vi.mocked(getTask).mockImplementation(async () =>
      createMockTaskDetail({
        task_id: taskId,
        status: "running",
        audit_events: Array.from({ length: auditCount }, (_, index) => ({
          id: `evt-${index + 1}`,
          engine: "langgraph",
          step: "researcher",
          status: "running",
          payload: {},
          event_time: `2026-07-05T00:00:0${index}.000Z`,
        })),
        metrics: {
          tool_calls_total: auditCount,
          tool_calls_succeeded: auditCount,
          tool_calls_failed: 0,
          token_usage: {
            prompt_tokens: 10 * auditCount,
            completion_tokens: 5 * auditCount,
            total_tokens: 15 * auditCount,
            status: "known",
          },
          trace_id: "trace-flow-001",
        },
      }),
    );

    vi.mocked(pauseTask).mockResolvedValue({
      task_id: taskId,
      workflow_id: `wf-${taskId}`,
      status: "paused",
    });
    vi.mocked(resumeTask).mockResolvedValue({
      task_id: taskId,
      workflow_id: `wf-${taskId}`,
      status: "running",
    });

    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<NewTaskPage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText("研究主题"), {
      target: { value: "端到端测试" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建任务" }));

    await waitFor(() => {
      expect(createTask).toHaveBeenCalled();
      expect(navigateMock).toHaveBeenCalledWith(`/tasks/${taskId}`);
    });

    cleanup();
    render(
      <MemoryRouter initialEntries={[`/tasks/${taskId}`]}>
        <Routes>
          <Route path="/tasks/:taskId" element={<TaskDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("SSE 实时")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(FakeEventSource.instances).toHaveLength(1);
    });

    auditCount = 2;
    FakeEventSource.instances[0].dispatch(
      "task_event",
      JSON.stringify({
        task_id: taskId,
        engine: "langgraph",
        step: "analyst",
        status: "running",
        timestamp: "2026-07-05T00:00:03.000Z",
        detail: null,
        payload: {},
      }),
    );

    await waitFor(() => {
      expect(vi.mocked(getTask).mock.calls.length).toBeGreaterThan(1);
    });

    fireEvent.click(screen.getByRole("button", { name: "暂停" }));
    await waitFor(() => {
      expect(pauseTask).toHaveBeenCalledWith(taskId);
    });

    vi.mocked(getTask).mockImplementation(async () =>
      createMockTaskDetail({
        task_id: taskId,
        status: "paused",
        metrics: createMockTaskDetail().metrics,
      }),
    );
    cleanup();
    render(
      <MemoryRouter initialEntries={[`/tasks/${taskId}`]}>
        <Routes>
          <Route path="/tasks/:taskId" element={<TaskDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.queryByText("加载任务详情...")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "恢复" })).toBeEnabled();
    });

    fireEvent.click(screen.getByRole("button", { name: "恢复" }));
    await waitFor(() => {
      expect(resumeTask).toHaveBeenCalledWith(taskId);
    });
  });
});
