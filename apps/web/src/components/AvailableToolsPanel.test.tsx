import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AvailableToolsPanel } from "./AvailableToolsPanel";

vi.mock("../api/tools", () => ({
  listTools: vi.fn(),
}));

describe("AvailableToolsPanel", () => {
  it("shows error when tools API fails", async () => {
    const { listTools } = await import("../api/tools");
    vi.mocked(listTools).mockRejectedValue(new Error("mcp-server unavailable"));

    render(<AvailableToolsPanel />);

    await waitFor(() => {
      expect(screen.getByText(/工具列表不可用/)).toBeInTheDocument();
    });
  });

  it("renders discovered tools", async () => {
    const { listTools } = await import("../api/tools");
    vi.mocked(listTools).mockResolvedValue({
      tools: [{ name: "calculator", description: "Safe math", input_schema: {} }],
    });

    render(<AvailableToolsPanel />);

    await waitFor(() => {
      expect(screen.getByText("计算器")).toBeInTheDocument();
      expect(screen.getByText("Safe math")).toBeInTheDocument();
    });
  });
});
