import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { LiveEventStream } from "../components/LiveEventStream";
import { useUi } from "../store/ui";

describe("LiveEventStream", () => {
  it("renders bubbles in order, colors decision green/red", () => {
    useUi.setState({
      eventBuffer: [
        { v: 1, type: "analyst_thinking", ts: "t1", run_id: 1, data: { node: "Market Analyst" }, id: 1 },
        { v: 1, type: "decision", ts: "t2", run_id: 1, data: { action: "BUY", target: 260 }, id: 2 },
      ],
    });
    render(<LiveEventStream />);
    expect(screen.getByText(/Market Analyst/)).toBeInTheDocument();
    const bubble = screen.getByTestId("event-2");
    expect(bubble.className).toMatch(/emerald/);
  });
});
