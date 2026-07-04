import { describe, expect, it, vi, beforeEach } from "vitest";

import { createTask } from "./tasks";

describe("tasks api client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("createTask posts user query and engine", async () => {
    const mockResponse = {
      task_id: "11111111-1111-1111-1111-111111111111",
      session_id: "22222222-2222-2222-2222-222222222222",
      workflow_id: "wf-test",
      thread_id: "thread-test",
      status: "queued",
      engine_requested: "langgraph",
      user_preferences: {},
      session_context: [],
    };

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 201,
        json: async () => mockResponse,
      }),
    );

    const result = await createTask({
      user_query: "test query",
      engine: "langgraph",
    });

    expect(fetch).toHaveBeenCalledWith(
      "/api/tasks",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ user_query: "test query", engine: "langgraph" }),
      }),
    );
    expect(result.task_id).toBe(mockResponse.task_id);
  });
});
