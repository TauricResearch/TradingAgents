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

  it("shows exception class and message on run_failed", () => {
    useUi.setState({
      eventBuffer: [
        {
          v: 1,
          type: "run_failed",
          ts: "t1",
          run_id: 1,
          data: {
            reason: "exception",
            exception_class: "RateLimitError",
            message: "OpenRouter 429: rate limit exceeded",
          },
          id: 10,
        },
      ],
    });
    render(<LiveEventStream />);
    expect(screen.getByTestId("event-10")).toHaveTextContent(
      /failed: exception.*RateLimitError.*OpenRouter 429/
    );
  });

  it("falls back to reason-only when exception class/message absent", () => {
    useUi.setState({
      eventBuffer: [
        {
          v: 1,
          type: "run_failed",
          ts: "t1",
          run_id: 1,
          data: { reason: "cancelled" },
          id: 11,
        },
      ],
    });
    render(<LiveEventStream />);
    expect(screen.getByTestId("event-11")).toHaveTextContent("failed: cancelled");
  });

  it("shows message on tool_call_warning", () => {
    useUi.setState({
      eventBuffer: [
        {
          v: 1,
          type: "tool_call_warning",
          ts: "t1",
          run_id: 1,
          data: { message: "retrying after RateLimitError: 429" },
          id: 20,
        },
      ],
    });
    render(<LiveEventStream />);
    expect(screen.getByTestId("event-20")).toHaveTextContent(
      /warning: retrying after RateLimitError: 429/
    );
  });

  it("shows node name on analyst_started", () => {
    useUi.setState({
      eventBuffer: [
        {
          v: 1,
          type: "analyst_started",
          ts: "t1",
          run_id: 1,
          data: { node: "Market Analyst" },
          id: 30,
        },
        {
          v: 1,
          type: "analyst_started",
          ts: "t2",
          run_id: 1,
          data: { node: "News Analyst" },
          id: 31,
        },
      ],
    });
    render(<LiveEventStream />);
    expect(screen.getByTestId("event-30")).toHaveTextContent(/analyst_started: Market Analyst/);
    expect(screen.getByTestId("event-31")).toHaveTextContent(/analyst_started: News Analyst/);
  });

  it("falls back to stage on analyst_completed and appends summary", () => {
    useUi.setState({
      eventBuffer: [
        {
          v: 1,
          type: "analyst_completed",
          ts: "t1",
          run_id: 1,
          data: { stage: "market", summary: "bullish" },
          id: 40,
        },
      ],
    });
    render(<LiveEventStream />);
    expect(screen.getByTestId("event-40")).toHaveTextContent(
      /analyst_completed: market — bullish/
    );
  });
});
