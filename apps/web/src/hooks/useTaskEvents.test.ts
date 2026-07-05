import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createMockTaskDetail } from "../test/fixtures";
import { useTaskEvents } from "./useTaskEvents";

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  url: string;
  onerror: (() => void) | null = null;
  close = vi.fn();
  private handlers = new Map<string, (message: MessageEvent) => void>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
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

vi.mock("../api/tasks", () => ({
  getTask: vi.fn(),
  taskEventsUrl: (taskId: string) => `/api/tasks/${taskId}/events`,
}));

describe("useTaskEvents", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it("uses SSE for running tasks", async () => {
    const { getTask } = await import("../api/tasks");
    vi.mocked(getTask).mockResolvedValue(createMockTaskDetail({ status: "running" }));

    const { result } = renderHook(() => useTaskEvents("task-1"));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.connectionMode).toBe("sse");
    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it("stays idle for terminal tasks", async () => {
    const { getTask } = await import("../api/tasks");
    vi.mocked(getTask).mockResolvedValue(createMockTaskDetail({ status: "succeeded" }));

    const { result } = renderHook(() => useTaskEvents("task-1"));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.connectionMode).toBe("idle");
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it("falls back to polling after max reconnects", async () => {
    const { getTask } = await import("../api/tasks");
    vi.mocked(getTask).mockResolvedValue(createMockTaskDetail({ status: "running" }));

    const { result } = renderHook(() => useTaskEvents("task-1"));

    await waitFor(() => {
      expect(FakeEventSource.instances.length).toBeGreaterThan(0);
    });

    for (let attempt = 0; attempt < 4; attempt += 1) {
      await act(async () => {
        FakeEventSource.instances.at(-1)?.onerror?.();
        await new Promise((resolve) => {
          setTimeout(resolve, 50);
        });
      });
      await act(async () => {
        await new Promise((resolve) => {
          setTimeout(resolve, 1050);
        });
      });
    }

    await waitFor(
      () => {
        expect(result.current.connectionMode).toBe("polling");
      },
      { timeout: 8000 },
    );
  }, 15000);

  it("resets reconnect count after task_event", async () => {
    const { getTask } = await import("../api/tasks");
    vi.mocked(getTask).mockResolvedValue(createMockTaskDetail({ status: "running" }));

    const { result } = renderHook(() => useTaskEvents("task-1"));

    await waitFor(() => {
      expect(FakeEventSource.instances).toHaveLength(1);
    });

    const source = FakeEventSource.instances[0];
    act(() => {
      source.dispatch(
        "task_event",
        JSON.stringify({
          task_id: "task-1",
          engine: "langgraph",
          step: "researcher",
          status: "running",
          timestamp: "2026-07-05T00:00:02.000Z",
          detail: null,
          payload: {},
        }),
      );
    });

    await act(async () => {
      source.onerror?.();
      await new Promise((resolve) => {
        setTimeout(resolve, 1100);
      });
    });

    expect(result.current.connectionMode).toBe("sse");
    expect(FakeEventSource.instances.length).toBe(2);
  }, 10000);

  it("stops reconnecting when task becomes terminal", async () => {
    const { getTask } = await import("../api/tasks");
    vi.mocked(getTask)
      .mockResolvedValueOnce(createMockTaskDetail({ status: "running" }))
      .mockResolvedValue(createMockTaskDetail({ status: "succeeded" }));

    const { result } = renderHook(() => useTaskEvents("task-1"));

    await waitFor(() => {
      expect(FakeEventSource.instances).toHaveLength(1);
    });

    await act(async () => {
      FakeEventSource.instances[0].onerror?.();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(result.current.connectionMode).toBe("idle");
    });
  });
});
