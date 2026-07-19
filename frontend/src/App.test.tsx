import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { App } from "./App";

describe("App shell", () => {
  it("renders the V2 three-column layout brand and localhost pill", () => {
    render(<App />);
    // Brand renders the approved V2 title even before any backend data lands.
    expect(screen.getByText(/Research Console/)).toBeInTheDocument();
    // The localhost pill is the distinct local-safety affordance in the topbar.
    expect(screen.getByText(/● localhost/)).toBeInTheDocument();
    // The three persistent columns exist with their approved headings.
    expect(screen.getByRole("heading", { name: "分析输入" })).toBeInTheDocument();
    // Right column is the G3 Inspector with its top-level audit tabs.
    expect(screen.getByRole("button", { name: "角色输入" })).toBeInTheDocument();
  });
});