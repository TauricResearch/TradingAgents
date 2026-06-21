import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ObservatoryDag } from "../components/ObservatoryDag";

const mockEvents: any[] = [
  { id: "1", type: "analyst_started", ts: "2024-01-01T00:00:00Z", run_id: "r1", data: { node: "Market Analyst" } },
  { id: "2", type: "analyst_completed", ts: "2024-01-01T00:01:00Z", run_id: "r1", data: { node: "Market Analyst", stage: "market" } },
];

describe("ObservatoryDag", () => {
  it("renders all agent nodes", () => {
    render(<ObservatoryDag events={mockEvents} onNodeClick={() => {}} />);
    expect(screen.getByText("Market Analyst")).toBeInTheDocument();
    expect(screen.getByText("Bull Researcher")).toBeInTheDocument();
    expect(screen.getByText("Portfolio Manager")).toBeInTheDocument();
  });

  it("shows correct status per agent", () => {
    render(<ObservatoryDag events={mockEvents} onNodeClick={() => {}} />);
    const market = screen.getByTestId("dag-node-Market Analyst");
    expect(market.className).toContain("emerald");
  });

  it("calls onNodeClick when a node is clicked", () => {
    const onClick = vi.fn();
    render(<ObservatoryDag events={mockEvents} onNodeClick={onClick} />);
    fireEvent.click(screen.getByTestId("dag-node-Market Analyst"));
    expect(onClick).toHaveBeenCalledWith("Market Analyst");
  });
});
