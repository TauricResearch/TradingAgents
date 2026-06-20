import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ToolTimeline } from "../components/ToolTimeline";

const mockEvents: any[] = [
  { id: "1", type: "tool_call", ts: "2024-01-01T00:00:00Z", run_id: "r1", data: { tool: "get_stock_data", args: "AAPL" } },
  { id: "2", type: "tool_result", ts: "2024-01-01T00:00:01Z", run_id: "r1", data: { tool: "get_stock_data", summary: "price data", duration_ms: 1200 } },
];

describe("ToolTimeline", () => {
  it("renders empty state", () => {
    render(<ToolTimeline events={[]} />);
    expect(screen.getByText("No tool calls yet.")).toBeInTheDocument();
  });

  it("renders tool call and result", () => {
    render(<ToolTimeline events={mockEvents} />);
    expect(screen.getAllByText(/get_stock_data/).length).toBeGreaterThan(0);
    expect(screen.getByText(/1200ms/)).toBeInTheDocument();
  });

  it("expands on click", () => {
    render(<ToolTimeline events={mockEvents} />);
    fireEvent.click(screen.getAllByText(/get_stock_data/)[0]);
    expect(screen.getByText(/Args:/)).toBeInTheDocument();
  });
});
