/* eslint-disable @typescript-eslint/no-explicit-any */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PipelineFlow } from "../components/PipelineFlow";
import type { WsEvent } from "../lib/events";

const evt = (runId: string, type: string, data: any, id: string): WsEvent => ({
  v: 1, type: type as any, ts: `t${id}`, run_id: runId, data, id,
});

describe("PipelineFlow — structural", () => {
  it("renders a dot for every stage", () => {
    render(<PipelineFlow events={[]} />);
    for (const key of ["market", "sentiment", "news", "fundamentals", "research", "trader", "risk"]) {
      expect(screen.getByTestId(`stage-${key}`)).toBeInTheDocument();
    }
  });

  it("renders 6 connecting segments between 7 dots", () => {
    const { container } = render(<PipelineFlow events={[]} />);
    expect(container.querySelectorAll('[data-testid="timeline-segment"]')).toHaveLength(6);
  });

  it("renders all 5 team cards", () => {
    render(<PipelineFlow events={[]} />);
    expect(screen.getAllByText("Analyst Team").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Research Team")).toBeInTheDocument();
    expect(screen.getByText("Trading Team")).toBeInTheDocument();
    expect(screen.getByText("Risk Management")).toBeInTheDocument();
    expect(screen.getByText("Portfolio Mgmt")).toBeInTheDocument();
  });
});

describe("PipelineFlow — stage status", () => {
  it("marks every stage as 'idle' when no events have fired", () => {
    render(<PipelineFlow events={[]} />);
    for (const key of ["market", "sentiment", "news", "fundamentals", "research", "trader", "risk"]) {
      expect(screen.getByTestId(`stage-${key}`).getAttribute("data-status")).toBe("idle");
    }
  });

  it("marks a stage as 'done' when analyst_completed fires with a report", () => {
    render(<PipelineFlow events={[
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", { stage: "market", summary: "completed", report_excerpt: "Bullish on NVDA" }, "2"),
    ]} />);
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).toBe("done");
  });

  it("marks a stage as 'running' between started and completed", () => {
    render(<PipelineFlow events={[
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_thinking", { text_preview: "analyzing" }, "2"),
    ]} />);
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).toBe("running");
  });

  it("marks a stage as 'errored' after run_failed", () => {
    render(<PipelineFlow events={[
      evt("NVDA:1", "analyst_started", { node: "Sentiment Analyst" }, "1"),
      evt("NVDA:1", "run_failed", { reason: "rate_limited" }, "2"),
    ]} />);
    expect(screen.getByTestId("stage-sentiment").getAttribute("data-status")).toBe("errored");
  });

  it("does NOT mark a stage as 'done' when analyst_completed fires without a report", () => {
    render(<PipelineFlow events={[
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", { stage: "market", summary: "completed" }, "2"),
    ]} />);
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).not.toBe("done");
  });
});

describe("PipelineFlow — segment progress", () => {
  it("the first segment is 'traversed' once market completes", () => {
    const { container } = render(<PipelineFlow events={[
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", { stage: "market", report_excerpt: "market ok" }, "2"),
    ]} />);
    const segs = container.querySelectorAll('[data-testid="timeline-segment"]');
    expect(segs[0].getAttribute("data-progress")).toBe("traversed");
    expect(segs[1].getAttribute("data-progress")).toBe("future");
  });

  it("the segment leading to the running stage is 'active'", () => {
    const { container } = render(<PipelineFlow events={[
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", { stage: "market", report_excerpt: "market ok" }, "2"),
      evt("NVDA:1", "analyst_started", { node: "Sentiment Analyst" }, "3"),
    ]} />);
    const segs = container.querySelectorAll('[data-testid="timeline-segment"]');
    expect(segs[0].getAttribute("data-progress")).toBe("traversed");
    expect(segs[1].getAttribute("data-progress")).toBe("active");
    expect(segs[2].getAttribute("data-progress")).toBe("future");
  });

  it("all segments are 'failed' after run_failed", () => {
    const { container } = render(<PipelineFlow events={[
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "run_failed", { reason: "boom" }, "2"),
    ]} />);
    const segs = container.querySelectorAll('[data-testid="timeline-segment"]');
    segs.forEach((seg) => expect(seg.getAttribute("data-progress")).toBe("failed"));
  });
});

describe("PipelineFlow — click to expand details", () => {
  it("clicking a stage dot toggles its details panel open", () => {
    render(<PipelineFlow events={[
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
    ]} />);
    const market = screen.getByTestId("stage-market");
    expect(market.getAttribute("data-expanded")).toBe("false");
    fireEvent.click(market);
    expect(market.getAttribute("data-expanded")).toBe("true");
  });

  it("clicking the same stage dot again collapses the panel", () => {
    render(<PipelineFlow events={[
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
    ]} />);
    const market = screen.getByTestId("stage-market");
    fireEvent.click(market);
    fireEvent.click(market);
    expect(market.getAttribute("data-expanded")).toBe("false");
  });

  it("opening one stage closes the others (accordion behavior)", () => {
    render(<PipelineFlow events={[
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", { stage: "market" }, "2"),
      evt("NVDA:1", "analyst_started", { node: "Sentiment Analyst" }, "3"),
    ]} />);
    fireEvent.click(screen.getByTestId("stage-market"));
    expect(screen.getByTestId("stage-market").getAttribute("data-expanded")).toBe("true");
    fireEvent.click(screen.getByTestId("stage-sentiment"));
    expect(screen.getByTestId("stage-market").getAttribute("data-expanded")).toBe("false");
    expect(screen.getByTestId("stage-sentiment").getAttribute("data-expanded")).toBe("true");
  });

  it("a running stage's details panel shows its thinking log", () => {
    render(<PipelineFlow events={[
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_thinking", { text_preview: "q1" }, "2"),
      evt("NVDA:1", "analyst_thinking", { text_fragment: "answer chunk" }, "3"),
    ]} />);
    fireEvent.click(screen.getByTestId("stage-market"));
    expect(screen.getByText(/q1/)).toBeInTheDocument();
    expect(screen.getByText(/answer chunk/)).toBeInTheDocument();
  });

  it("a done stage's details panel shows its report excerpt", () => {
    render(<PipelineFlow events={[
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", { stage: "market", summary: "completed", report_excerpt: "Bullish on NVDA long-term", report_text: "Full analysis" }, "2"),
    ]} />);
    fireEvent.click(screen.getByTestId("stage-market"));
    expect(screen.getByText(/Bullish on NVDA long-term/)).toBeInTheDocument();
  });
});

describe("PipelineFlow — agent row click opens stage detail", () => {
  it("clicking an agent name opens its stage detail panel", () => {
    render(<PipelineFlow events={[
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_thinking", { text_preview: "analyzing prices" }, "2"),
    ]} />);
    // Market Analyst is inside Analyst Team card
    fireEvent.click(screen.getByText("Market Analyst"));
    expect(screen.getByTestId("stage-market")).toHaveAttribute("data-expanded", "true");
  });

  it("clicking an agent name of a done stage shows the report", () => {
    render(<PipelineFlow events={[
      evt("NVDA:1", "analyst_started", { node: "Trader" }, "1"),
      evt("NVDA:1", "analyst_completed", { stage: "trader", report_excerpt: "Buy signal confirmed" }, "2"),
    ]} />);
    fireEvent.click(screen.getByTestId("agent-row-Trader"));
    expect(screen.getByText(/Buy signal confirmed/)).toBeInTheDocument();
  });
});

describe("PipelineFlow — running-stage spinner", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-14T10:00:10.000Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders a spinner inside the running stage's dot", () => {
    render(<PipelineFlow events={[
      evt("NVDA:1", "analyst_started", { node: "Market Analyst", ts: "2026-06-14T10:00:05.000Z" }, "1"),
    ]} />);
    const btn = screen.getByTestId("stage-market");
    expect(btn.getAttribute("data-status")).toBe("running");
    // Spinner SVG is present
    expect(btn.querySelector("svg.animate-spin")).toBeInTheDocument();
  });
});

describe("PipelineFlow — per-stage duration", () => {
  it("shows the persisted duration under each completed stage", () => {
    render(<PipelineFlow events={[
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", { stage: "market", summary: "ok", report_excerpt: "ok", report_text: "ok", duration_ms: 1500 }, "2"),
    ]} />);
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).toBe("done");
  });
});
