import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { NewTaskPage } from "./NewTaskPage";

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

vi.mock("../api/tasks", () => ({
  createTask: vi.fn().mockResolvedValue({
    task_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  }),
}));

describe("NewTaskPage", () => {
  it("submits task and navigates to detail page", async () => {
    const { createTask } = await import("../api/tasks");

    render(
      <MemoryRouter>
        <NewTaskPage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText("研究主题"), {
      target: { value: "测试主题" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建任务" }));

    await vi.waitFor(() => {
      expect(createTask).toHaveBeenCalledWith({
        user_query: "测试主题",
        engine: "auto",
      });
    });
    expect(navigateMock).toHaveBeenCalledWith(
      "/tasks/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    );
  });
});
