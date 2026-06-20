import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { DecisionTrace } from "../components/DecisionTrace";

const mockEvents: any[] = [
  { id: "1", type: "analyst_completed", ts: "2024-01-01T00:00:00Z", run_id: "r1", data: { stage: "market", node: "Market Analyst", report_excerpt: "Price trending up", report_text: "Full report..." } },
  { id: "2", type: "decision", ts: "2024-01-01T00:05:00Z", run_id: "r1", data: { action: "BUY", target: 200, confidence: 0.75 } },
];

describe("DecisionTrace", () => {
  it("renders empty state", () => {
    render(<DecisionTrace events={[]} />);
    expect(screen.getByText("No decision data yet.")).toBeInTheDocument();
  });

  it("renders stage and decision", () => {
    render(<DecisionTrace events={mockEvents} />);
    expect(screen.getByText("Market Analyst")).toBeInTheDocument();
    expect(screen.getByText(/BUY/)).toBeInTheDocument();
  });

  it("expands stage details on click", () => {
    render(<DecisionTrace events={mockEvents} />);
    fireEvent.click(screen.getByText("Market Analyst"));
    expect(screen.getByText("Full report...")).toBeInTheDocument();
  });
});
