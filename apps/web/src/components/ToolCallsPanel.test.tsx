import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ToolCall } from "../api/types";
import { ToolCallsPanel } from "./ToolCallsPanel";

const successCall: ToolCall = {
  id: "call-1",
  tool_name: "calculator",
  arguments: { expression: "1+1" },
  result_summary: "2",
  error: null,
  started_at: "2026-07-05T00:00:00.000Z",
  finished_at: "2026-07-05T00:00:01.000Z",
};

const failedCall: ToolCall = {
  ...successCall,
  id: "call-2",
  tool_name: "web_search",
  result_summary: null,
  error: "timeout",
};

describe("ToolCallsPanel", () => {
  it("shows empty state", () => {
    render(<ToolCallsPanel calls={[]} />);
    expect(screen.getByText("暂无工具调用")).toBeInTheDocument();
  });

  it("renders successful call", () => {
    render(<ToolCallsPanel calls={[successCall]} />);
    expect(screen.getByText("calculator")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("renders failed call", () => {
    render(<ToolCallsPanel calls={[failedCall]} />);
    expect(screen.getByText("web_search")).toBeInTheDocument();
    expect(screen.getByText("timeout")).toBeInTheDocument();
  });
});
