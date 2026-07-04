import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import App from "./App";

vi.mock("./api/providers", () => ({
  getProviders: vi.fn().mockResolvedValue({
    provider: "deepseek",
    model: "deepseek-chat",
    capabilities: {
      supports_streaming: true,
      supports_tools: true,
      supports_structured_output: true,
      max_context_tokens: 64000,
    },
  }),
}));

describe("App", () => {
  it("renders platform navigation", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "多智能体协作控制台" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "新建任务" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "历史与设置" })).toBeInTheDocument();
  });
});
