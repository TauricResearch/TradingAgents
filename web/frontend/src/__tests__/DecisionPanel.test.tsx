import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DecisionPanel } from "../components/DecisionPanel";

describe("DecisionPanel", () => {
  it("renders action, target, and confidence bar", () => {
    render(<DecisionPanel action="BUY" target={260.5} confidence={0.82} rationale="looks good" />);
    expect(screen.getByText(/BUY/)).toBeInTheDocument();
    expect(screen.getByText(/\$260/)).toBeInTheDocument();
    expect(screen.getByText(/looks good/)).toBeInTheDocument();
  });
});
