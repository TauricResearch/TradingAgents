import { render, screen } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { DebateFlow } from "../components/DebateFlow";

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

const mockDebate: any[] = [
  { id: "1", type: "debate_message", ts: "2024-01-01T00:00:00Z", run_id: "r1", data: { side: "Bull Researcher", text: "I think this is a buy", turn: 1 } },
  { id: "2", type: "debate_message", ts: "2024-01-01T00:01:00Z", run_id: "r1", data: { side: "Bear Researcher", text: "I disagree", turn: 1 } },
];

describe("DebateFlow", () => {
  it("renders empty state", () => {
    render(<DebateFlow events={[]} type="debate" />);
    expect(screen.getByText("No debate messages yet.")).toBeInTheDocument();
  });

  it("renders debate messages", () => {
    render(<DebateFlow events={mockDebate} type="debate" />);
    expect(screen.getByText(/I think this is a buy/)).toBeInTheDocument();
    expect(screen.getByText(/I disagree/)).toBeInTheDocument();
  });

  it("shows side labels", () => {
    render(<DebateFlow events={mockDebate} type="debate" />);
    expect(screen.getAllByText(/Round 1/).length).toBe(2);
  });

  it("shows risk empty state for risk type", () => {
    render(<DebateFlow events={[]} type="risk" />);
    expect(screen.getByText("No risk messages yet.")).toBeInTheDocument();
  });
});
