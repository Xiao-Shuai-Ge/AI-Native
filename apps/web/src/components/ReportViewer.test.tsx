import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ReportViewer } from "./ReportViewer";

describe("ReportViewer", () => {
  it("shows an empty state when there is no report yet", () => {
    render(<ReportViewer report={null} />);
    expect(screen.getByText("报告尚未生成")).toBeInTheDocument();
  });

  it("renders Markdown headings and lists as real DOM elements", () => {
    render(<ReportViewer report={"# Title\n\n- item one\n- item two"} />);
    expect(screen.getByRole("heading", { level: 1, name: "Title" })).toBeInTheDocument();
    expect(screen.getByText("item one")).toBeInTheDocument();
    expect(screen.getByText("item two")).toBeInTheDocument();
  });
});
