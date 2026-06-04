import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { RunTimeline } from "../components/RunTimeline";
import { useUi } from "../store/ui";
import type { WsEvent } from "../lib/events";

const evt = (runId: string, type: string, data: any, id: string): WsEvent => ({
  v: 1, type: type as any, ts: `t${id}`, run_id: runId, data, id,
});

const setup = (events: WsEvent[], focused = "NVDA", runId: string = "NVDA:1") => {
  useUi.setState({
    focusedTicker: focused,
    lastRunIdByTicker: { [focused]: runId },
    eventBuffer: events,
    activeRunIdByTicker: {},
    historicalRunIdByTicker: {},
  });
};

beforeEach(() => {
  useUi.setState({
    focusedTicker: null,
    lastRunIdByTicker: {},
    eventBuffer: [],
    activeRunIdByTicker: {},
    historicalRunIdByTicker: {},
  });
});

describe("RunTimeline — structural", () => {
  it("renders a node for every pipeline stage", () => {
    setup([]);
    render(<RunTimeline />);
    for (const key of ["market", "sentiment", "news", "fundamentals", "research", "risk", "trader"]) {
      expect(screen.getByTestId(`stage-${key}`)).toBeInTheDocument();
    }
  });

  it("shows stage labels under each node", () => {
    setup([]);
    render(<RunTimeline />);
    expect(screen.getByText("Market")).toBeInTheDocument();
    expect(screen.getByText("Sentiment")).toBeInTheDocument();
    expect(screen.getByText("Trader")).toBeInTheDocument();
  });

  it("renders 6 connecting segments between 7 nodes", () => {
    setup([]);
    const { container } = render(<RunTimeline />);
    expect(container.querySelectorAll('[data-testid="timeline-segment"]')).toHaveLength(6);
  });
});

describe("RunTimeline — stage status", () => {
  it("marks every stage as 'idle' when no events have fired", () => {
    setup([]);
    render(<RunTimeline />);
    for (const key of ["market", "sentiment", "news", "fundamentals", "research", "risk", "trader"]) {
      expect(screen.getByTestId(`stage-${key}`).getAttribute("data-status")).toBe("idle");
    }
  });

  it("marks a stage as 'done' when analyst_completed fires", () => {
    setup([
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", { stage: "market", summary: "completed" }, "2"),
    ]);
    render(<RunTimeline />);
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).toBe("done");
    expect(screen.getByTestId("stage-sentiment").getAttribute("data-status")).toBe("idle");
  });

  it("marks a stage as 'running' between started and completed", () => {
    setup([
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_thinking", { text_preview: "analyzing" }, "2"),
    ]);
    render(<RunTimeline />);
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).toBe("running");
  });

  it("does not leak events from a different run into the timeline", () => {
    setup([
      evt("NVDA:1", "analyst_completed", { stage: "market" }, "1"),
      evt("NVDA:2", "analyst_started", { node: "Market Analyst" }, "2"),
    ], "NVDA", "NVDA:1");
    render(<RunTimeline />);
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).toBe("done");
  });

  it("marks all stages as 'errored' after a run_failed event", () => {
    setup([
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", { stage: "market" }, "2"),
      evt("NVDA:1", "run_failed", { reason: "rate_limited" }, "3"),
    ]);
    render(<RunTimeline />);
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).toBe("done");
    expect(screen.getByTestId("stage-sentiment").getAttribute("data-status")).toBe("errored");
  });
});

describe("RunTimeline — segment progress", () => {
  it("the first segment is 'traversed' once market completes", () => {
    setup([
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", { stage: "market" }, "2"),
    ]);
    const { container } = render(<RunTimeline />);
    const segs = container.querySelectorAll('[data-testid="timeline-segment"]');
    expect(segs[0].getAttribute("data-progress")).toBe("traversed");
    expect(segs[1].getAttribute("data-progress")).toBe("future");
  });

  it("the segment leading to the running stage is 'active'", () => {
    setup([
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", { stage: "market" }, "2"),
      evt("NVDA:1", "analyst_started", { node: "Sentiment Analyst" }, "3"),
    ]);
    const { container } = render(<RunTimeline />);
    const segs = container.querySelectorAll('[data-testid="timeline-segment"]');
    expect(segs[0].getAttribute("data-progress")).toBe("traversed");
    expect(segs[1].getAttribute("data-progress")).toBe("active");
    expect(segs[2].getAttribute("data-progress")).toBe("future");
  });
});

describe("RunTimeline — click to expand details", () => {
  it("clicking a node toggles its details panel open", () => {
    setup([
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_thinking", { text_preview: "looking at prices" }, "2"),
    ]);
    render(<RunTimeline />);
    const market = screen.getByTestId("stage-market");
    expect(market.getAttribute("data-expanded")).toBe("false");
    fireEvent.click(market);
    expect(screen.getByTestId("stage-market").getAttribute("data-expanded")).toBe("true");
  });

  it("clicking the same node again collapses the panel", () => {
    setup([
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
    ]);
    render(<RunTimeline />);
    const market = screen.getByTestId("stage-market");
    fireEvent.click(market);
    fireEvent.click(market);
    expect(market.getAttribute("data-expanded")).toBe("false");
  });

  it("opening one stage closes the others (accordion behavior)", () => {
    setup([
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", { stage: "market" }, "2"),
      evt("NVDA:1", "analyst_started", { node: "Sentiment Analyst" }, "3"),
    ]);
    render(<RunTimeline />);
    fireEvent.click(screen.getByTestId("stage-market"));
    expect(screen.getByTestId("stage-market").getAttribute("data-expanded")).toBe("true");
    fireEvent.click(screen.getByTestId("stage-sentiment"));
    expect(screen.getByTestId("stage-market").getAttribute("data-expanded")).toBe("false");
    expect(screen.getByTestId("stage-sentiment").getAttribute("data-expanded")).toBe("true");
  });

  it("a running stage's details panel shows its thinking log", () => {
    setup([
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_thinking", { text_preview: "q1" }, "2"),
      evt("NVDA:1", "analyst_thinking", { text_fragment: "answer chunk" }, "3"),
    ]);
    render(<RunTimeline />);
    fireEvent.click(screen.getByTestId("stage-market"));
    expect(screen.getByText(/q1/)).toBeInTheDocument();
    expect(screen.getByText(/answer chunk/)).toBeInTheDocument();
  });

  it("a done stage's details panel shows its report excerpt", () => {
    setup([
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", {
        stage: "market",
        summary: "completed",
        report_excerpt: "Bullish on NVDA long-term",
        report_text: "Full bullish analysis here…",
      }, "2"),
    ]);
    render(<RunTimeline />);
    fireEvent.click(screen.getByTestId("stage-market"));
    expect(screen.getByText(/Bullish on NVDA long-term/)).toBeInTheDocument();
  });
});
