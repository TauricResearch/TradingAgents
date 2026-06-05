import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
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

  it("marks a stage as 'done' when analyst_completed fires with a report", () => {
    setup([
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", {
        stage: "market",
        summary: "completed",
        report_excerpt: "Bullish on NVDA",
      }, "2"),
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
      evt("NVDA:1", "analyst_completed", { stage: "market", report_excerpt: "Bullish" }, "1"),
      evt("NVDA:2", "analyst_started", { node: "Market Analyst" }, "2"),
    ], "NVDA", "NVDA:1");
    render(<RunTimeline />);
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).toBe("done");
  });

  it("marks all stages as 'errored' after a run_failed event", () => {
    setup([
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", {
        stage: "market",
        report_excerpt: "Bullish",
      }, "2"),
      evt("NVDA:1", "run_failed", { reason: "rate_limited" }, "3"),
    ]);
    render(<RunTimeline />);
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).toBe("done");
    expect(screen.getByTestId("stage-sentiment").getAttribute("data-status")).toBe("errored");
  });

  it("marks a stage as 'errored' if it was started but not completed when run_failed fires", () => {
    setup([
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", {
        stage: "market",
        report_excerpt: "Bullish",
      }, "2"),
      evt("NVDA:1", "analyst_started", { node: "Sentiment Analyst" }, "3"),
      evt("NVDA:1", "analyst_thinking", { text_preview: "reading tweets" }, "4"),
      evt("NVDA:1", "run_failed", { reason: "exception", message: "boom" }, "5"),
    ]);
    render(<RunTimeline />);
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).toBe("done");
    expect(screen.getByTestId("stage-sentiment").getAttribute("data-status")).toBe("errored");
  });

  it("does NOT mark a stage as 'done' when analyst_completed fires without a report", () => {
    // Regression: a completion event with no report_excerpt and no
    // report_text means the runner got node_exited but the underlying
    // node produced no useful output (e.g. tool returned empty). The
    // user used to see a green checkmark next to "Market" and a
    // "No report content." placeholder inside — which is misleading
    // because the stage clearly did not deliver anything.
    setup([
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", { stage: "market", summary: "completed" }, "2"),
    ]);
    render(<RunTimeline />);
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).not.toBe("done");
  });

  it("marks a no-report 'completed' stage as 'errored' when run_failed fires", () => {
    // Mirrors the user's case: news fires analyst_completed with no
    // news_report, then the run later fails. Showing "done" with
    // "No report content." is wrong — the stage did not deliver.
    setup([
      evt("NVDA:1", "analyst_started", { node: "News Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", { stage: "news", summary: "completed" }, "2"),
      evt("NVDA:1", "run_failed", { reason: "exception", message: "boom" }, "3"),
    ]);
    render(<RunTimeline />);
    expect(screen.getByTestId("stage-news").getAttribute("data-status")).toBe("errored");
  });

  it("does NOT show the 'No report content.' placeholder for a stage whose completion lacked a report", () => {
    setup([
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", { stage: "market", summary: "completed" }, "2"),
    ]);
    render(<RunTimeline />);
    fireEvent.click(screen.getByTestId("stage-market"));
    const text = screen.getByTestId("stage-market-details").textContent ?? "";
    expect(text).not.toMatch(/No report content\./);
  });

  it("still marks a stage as 'done' when a debate-style node earlier produced a report (Bull/Bear → Research Manager)", () => {
    // Bull Researcher and Bear Researcher emit analyst_completed for
    // the "research" stage with no report (their state has no
    // investment_plan yet). The Research Manager then emits one WITH
    // the investment_plan. The stage must be 'done' with the report.
    setup([
      evt("NVDA:1", "analyst_started", { node: "Bull Researcher" }, "1"),
      evt("NVDA:1", "analyst_completed", { stage: "research", summary: "completed" }, "2"),
      evt("NVDA:1", "analyst_started", { node: "Bear Researcher" }, "3"),
      evt("NVDA:1", "analyst_completed", { stage: "research", summary: "completed" }, "4"),
      evt("NVDA:1", "analyst_started", { node: "Research Manager" }, "5"),
      evt("NVDA:1", "analyst_completed", {
        stage: "research",
        summary: "completed",
        report_excerpt: "Buy NVDA — bullish on AI demand",
        report_text: "Full investment plan…",
      }, "6"),
    ]);
    render(<RunTimeline />);
    expect(screen.getByTestId("stage-research").getAttribute("data-status")).toBe("done");
  });

  it("stage with a real report remains 'done' even after run_failed (the run failed later, not the stage)", () => {
    setup([
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", {
        stage: "market",
        summary: "completed",
        report_excerpt: "Market is bullish",
        report_text: "Full market report…",
      }, "2"),
      evt("NVDA:1", "analyst_started", { node: "Sentiment Analyst" }, "3"),
      evt("NVDA:1", "run_failed", { reason: "exception", message: "boom" }, "4"),
    ]);
    render(<RunTimeline />);
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).toBe("done");
    expect(screen.getByTestId("stage-sentiment").getAttribute("data-status")).toBe("errored");
  });
});

describe("RunTimeline — per-stage thinking log", () => {
  it("shows thinking events from a single stage's iteration, in order", () => {
    setup([
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_thinking", { text_preview: "first" }, "2"),
      evt("NVDA:1", "analyst_thinking", { text_fragment: "second" }, "3"),
    ]);
    render(<RunTimeline />);
    fireEvent.click(screen.getByTestId("stage-market"));
    const text = screen.getByTestId("stage-market-details").textContent ?? "";
    expect(text).toMatch(/first/);
    expect(text).toMatch(/second/);
    // Order preserved
    expect(text.indexOf("first")).toBeLessThan(text.indexOf("second"));
  });

  it("attributes thinking across multiple iterations of the same stage to that stage", () => {
    // Simulate: Market Analyst started, tool called, started again (after tool),
    // then more thinking. The "running" log should still be Market's, and
    // should include events from BOTH iterations — not just the last.
    setup([
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_thinking", { text_preview: "iter1-thought" }, "2"),
      // tool node fires and ends (not an analyst_started/completed for market)
      evt("NVDA:1", "tool_call", { name: "fetch_prices" }, "3"),
      evt("NVDA:1", "tool_result", {}, "4"),
      // market re-enters (a second analyst_started for Market Analyst)
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "5"),
      evt("NVDA:1", "analyst_thinking", { text_preview: "iter2-thought" }, "6"),
    ]);
    render(<RunTimeline />);
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).toBe("running");
    fireEvent.click(screen.getByTestId("stage-market"));
    const text = screen.getByTestId("stage-market-details").textContent ?? "";
    // BOTH iteration's thoughts must appear, attributed to Market (not lost).
    expect(text).toMatch(/iter1-thought/);
    expect(text).toMatch(/iter2-thought/);
  });

  it("does not leak another stage's thinking into a stage's running log", () => {
    setup([
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", {
        stage: "market",
        report_excerpt: "Market report",
      }, "2"),
      evt("NVDA:1", "analyst_started", { node: "Sentiment Analyst" }, "3"),
      evt("NVDA:1", "analyst_thinking", { text_preview: "tweets-are-positive" }, "4"),
    ]);
    render(<RunTimeline />);
    // Market is done; click it and confirm only its report shows.
    fireEvent.click(screen.getByTestId("stage-market"));
    const marketText = screen.getByTestId("stage-market-details").textContent ?? "";
    expect(marketText).not.toMatch(/tweets-are-positive/);
  });

  it("attributes thinking across iterations even after a tool node boundary", () => {
    // Regression: log must continue to attribute to Market after a tool
    // round-trip, not get reset to the last analyst_started. Stage stays
    // in "running" state (no analyst_completed) so the running log is
    // what we observe in the UI.
    setup([
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_thinking", { text_preview: "before-tool" }, "2"),
      evt("NVDA:1", "tool_call", { name: "fetch_prices" }, "3"),
      evt("NVDA:1", "tool_result", {}, "4"),
      evt("NVDA:1", "analyst_thinking", { text_preview: "after-tool" }, "5"),
    ]);
    render(<RunTimeline />);
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).toBe("running");
    fireEvent.click(screen.getByTestId("stage-market"));
    const text = screen.getByTestId("stage-market-details").textContent ?? "";
    expect(text).toMatch(/before-tool/);
    expect(text).toMatch(/after-tool/);
  });
});

describe("RunTimeline — segment progress", () => {
  it("the first segment is 'traversed' once market completes", () => {
    setup([
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt(
        "NVDA:1",
        "analyst_completed",
        { stage: "market", report_excerpt: "market ok" },
        "2",
      ),
    ]);
    const { container } = render(<RunTimeline />);
    const segs = container.querySelectorAll('[data-testid="timeline-segment"]');
    expect(segs[0].getAttribute("data-progress")).toBe("traversed");
    expect(segs[1].getAttribute("data-progress")).toBe("future");
  });

  it("the segment leading to the running stage is 'active'", () => {
    setup([
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt(
        "NVDA:1",
        "analyst_completed",
        { stage: "market", report_excerpt: "market ok" },
        "2",
      ),
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

describe("RunTimeline — per-stage duration", () => {
  it("shows the persisted duration under each completed stage", () => {
    const events = [
      evt("NVDA:1", "run_started", { ticker: "NVDA" }, "1"),
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "2"),
      evt("NVDA:1", "analyst_completed", {
        stage: "market",
        summary: "ok",
        report_excerpt: "ok",
        report_text: "ok",
        duration_ms: 1500,
      }, "3"),
    ];
    setup(events);
    render(<RunTimeline />);
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).toBe("done");
    expect(screen.getByTestId("stage-market").parentElement?.textContent ?? "").toMatch(/ms|s$/);
  });
});

describe("RunTimeline — running-stage pill", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Pin "now" to a deterministic instant for elapsed math.
    vi.setSystemTime(new Date("2026-06-04T10:00:10.000Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders a spinner + elapsed text in the running stage's button", () => {
    // Market analyst started 5s ago; no completion yet.
    const events = [
      evt("NVDA:1", "run_started", { ticker: "NVDA" }, "1"),
      evt("NVDA:1", "analyst_started", {
        node: "Market Analyst",
        ts: "2026-06-04T10:00:05.000Z",
      }, "2"),
    ];
    setup(events);
    render(<RunTimeline />);
    const btn = screen.getByTestId("stage-market");
    expect(btn.getAttribute("data-status")).toBe("running");
    // Spinner SVG is present (animate-spin class on an svg child).
    expect(btn.querySelector("svg.animate-spin")).toBeInTheDocument();
    // Elapsed text is "5s".
    expect(btn.textContent).toMatch(/5s/);
  });

  it("advances the elapsed counter on a 1 Hz tick", () => {
    const events = [
      evt("NVDA:1", "run_started", { ticker: "NVDA" }, "1"),
      evt("NVDA:1", "analyst_started", {
        node: "Market Analyst",
        ts: "2026-06-04T10:00:00.000Z",
      }, "2"),
    ];
    setup(events);
    render(<RunTimeline />);
    expect(screen.getByTestId("stage-market").textContent).toMatch(/10s/);
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(screen.getByTestId("stage-market").textContent).toMatch(/13s/);
  });

  it("collapses back to a circle + ✓ when the stage completes", () => {
    const events = [
      evt("NVDA:1", "run_started", { ticker: "NVDA" }, "1"),
      evt("NVDA:1", "analyst_started", {
        node: "Market Analyst",
        ts: "2026-06-04T10:00:00.000Z",
      }, "2"),
    ];
    setup(events);
    const { rerender } = render(<RunTimeline />);
    expect(screen.getByTestId("stage-market").querySelector("svg.animate-spin")).toBeInTheDocument();
    // Add completion event, re-render with the new buffer.
    useUi.setState({
      eventBuffer: [
        ...events,
        evt("NVDA:1", "analyst_completed", {
          stage: "market",
          summary: "ok",
          report_excerpt: "ok",
          report_text: "ok",
          duration_ms: 10_000,
        }, "3"),
      ],
    });
    rerender(<RunTimeline />);
    const btn = screen.getByTestId("stage-market");
    expect(btn.getAttribute("data-status")).toBe("done");
    expect(btn.querySelector("svg.animate-spin")).not.toBeInTheDocument();
    expect(btn.textContent).toContain("✓");
  });
});
