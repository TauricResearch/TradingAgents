import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ThinkingStream } from "../components/ThinkingStream";

const mockEvents: any[] = [
  { id: "1", type: "analyst_thinking", ts: "2024-01-01T00:00:00Z", run_id: "r1", data: { node: "Market Analyst", text_fragment: "Analyzing price trends..." } },
];

describe("ThinkingStream", () => {
  it("renders empty state when no events", () => {
    render(<ThinkingStream events={[]} agentName="Market Analyst" />);
    expect(screen.getByText("No thinking data yet.")).toBeInTheDocument();
  });

  it("renders thinking text for matching agent", () => {
    render(<ThinkingStream events={mockEvents} agentName="Market Analyst" />);
    expect(screen.getByText("Analyzing price trends...")).toBeInTheDocument();
  });

  it("filters out events for other agents", () => {
    render(<ThinkingStream events={mockEvents} agentName="Sentiment Analyst" />);
    expect(screen.getByText("No thinking data yet.")).toBeInTheDocument();
  });
});
