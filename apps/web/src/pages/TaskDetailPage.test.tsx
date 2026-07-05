import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createMockTaskDetail } from "../test/fixtures";
import { TaskDetailPage } from "./TaskDetailPage";

const refreshMock = vi.fn();
let currentStatus: "running" | "paused" = "running";

const mockTask = createMockTaskDetail({
  metrics: {
    tool_calls_total: 2,
    tool_calls_succeeded: 1,
    tool_calls_failed: 1,
    token_usage: {
      prompt_tokens: 120,
      completion_tokens: 80,
      total_tokens: 200,
      status: "known",
    },
    trace_id: "abc123def4567890abc123def4567890",
  },
  tool_calls: [
    {
      id: "call-1",
      tool_name: "calculator",
      arguments: { expression: "1+1" },
      result_summary: "2",
      error: null,
      started_at: "2026-07-05T00:00:00.000Z",
      finished_at: "2026-07-05T00:00:01.000Z",
    },
  ],
  audit_events: [
    {
      id: "evt-1",
      engine: "langgraph",
      step: "researcher",
      status: "running",
      payload: {},
      event_time: "2026-07-05T00:00:00.000Z",
    },
  ],
});

vi.mock("../hooks/useTaskEvents", () => ({
  useTaskEvents: vi.fn(),
}));

vi.mock("../api/tools", () => ({
  listTools: vi.fn().mockResolvedValue({
    tools: [{ name: "calculator", description: "Math tool", input_schema: {} }],
  }),
}));

vi.mock("../api/tasks", () => ({
  pauseTask: vi.fn().mockResolvedValue({ status: "paused" }),
  resumeTask: vi.fn().mockResolvedValue({ status: "running" }),
}));

function renderDetailPage(status: "running" | "paused" = "running") {
  currentStatus = status;
  return render(
    <MemoryRouter initialEntries={["/tasks/task-1"]}>
      <Routes>
        <Route path="/tasks/:taskId" element={<TaskDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("TaskDetailPage", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    currentStatus = "running";
    const { useTaskEvents } = await import("../hooks/useTaskEvents");
    refreshMock.mockResolvedValue(undefined);
    vi.mocked(useTaskEvents).mockImplementation(() => ({
      task: { ...mockTask, status: currentStatus },
      auditEvents: mockTask.audit_events,
      loading: false,
      error: null,
      connectionMode: "sse",
      refresh: refreshMock,
    }));
  });

  afterEach(() => {
    cleanup();
  });

  it("renders metrics, tools and observability sections", async () => {
    renderDetailPage();

    expect(screen.getByText("任务指标")).toBeInTheDocument();
    expect(screen.getByText("可用 MCP 工具")).toBeInTheDocument();
    expect(screen.getByText("120")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getAllByText("calculator").length).toBeGreaterThan(0);
    });

    expect(screen.getByRole("link", { name: /Jaeger/i })).toHaveAttribute(
      "href",
      expect.stringContaining("abc123def4567890"),
    );
  });

  it("calls pause and refresh", async () => {
    const { pauseTask } = await import("../api/tasks");
    renderDetailPage("running");

    fireEvent.click(screen.getByRole("button", { name: "暂停" }));

    await waitFor(() => {
      expect(pauseTask).toHaveBeenCalledWith("task-1");
      expect(refreshMock).toHaveBeenCalled();
    });
  });

  it("calls resume when paused", async () => {
    const { resumeTask } = await import("../api/tasks");
    renderDetailPage("paused");

    fireEvent.click(screen.getByRole("button", { name: "恢复" }));

    await waitFor(() => {
      expect(resumeTask).toHaveBeenCalledWith("task-1");
      expect(refreshMock).toHaveBeenCalled();
    });
  });
});
