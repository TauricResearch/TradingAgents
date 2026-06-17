/* eslint-disable @typescript-eslint/no-explicit-any */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PipelineFlow } from "../components/PipelineFlow";
import type { WsEvent } from "../lib/events";

const evt = (runId: string, type: string, data: any, id: string): WsEvent => ({
  v: 1, type: type as any, ts: `t${id}`, run_id: runId, data, id,
});

describe("PipelineFlow — structural", () => {
  it("renders all 5 team cards", () => {
    render(<PipelineFlow events={[]} />);
    expect(screen.getAllByText("Analyst Team").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Research Team")).toBeInTheDocument();
    expect(screen.getByText("Trading Team")).toBeInTheDocument();
    expect(screen.getByText("Risk Management")).toBeInTheDocument();
    expect(screen.getByText("Portfolio Mgmt")).toBeInTheDocument();
  });

  it("shows agent rows inside team cards", () => {
    render(<PipelineFlow events={[]} />);
    expect(screen.getByText("Market Analyst")).toBeInTheDocument();
    expect(screen.getByText("Trader")).toBeInTheDocument();
    expect(screen.getByText("Portfolio Manager")).toBeInTheDocument();
  });
});

describe("PipelineFlow — team card status", () => {
  it("shows done count as 0/total when idle", () => {
    render(<PipelineFlow events={[]} />);
    // Analyst Team has 0/4 when idle
    const cards = screen.getAllByText(/\/\d+/);
    expect(cards.length).toBeGreaterThanOrEqual(1);
  });

  it("increments agent count as analysts complete", () => {
    render(<PipelineFlow events={[
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", { stage: "market", report_excerpt: "ok" }, "2"),
    ]} />);
    expect(screen.getByText("1/4")).toBeInTheDocument();
  });
});

describe("PipelineFlow — agent row click opens stage detail", () => {
  it("clicking an agent name opens its stage detail panel", () => {
    render(<PipelineFlow events={[
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_thinking", { text_preview: "analyzing prices" }, "2"),
    ]} />);
    fireEvent.click(screen.getByText("Market Analyst"));
    expect(screen.getByTestId("stage-market-details")).toBeInTheDocument();
  });

  it("clicking an agent name of a done stage shows the report", () => {
    render(<PipelineFlow events={[
      evt("NVDA:1", "analyst_started", { node: "Trader" }, "1"),
      evt("NVDA:1", "analyst_completed", { stage: "trader", report_excerpt: "Buy signal confirmed" }, "2"),
    ]} />);
    fireEvent.click(screen.getByTestId("agent-row-Trader"));
    expect(screen.getByText(/Buy signal confirmed/)).toBeInTheDocument();
  });

  it("clicking a different agent closes previous detail panel", () => {
    render(<PipelineFlow events={[
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", { stage: "market", report_excerpt: "market ok" }, "2"),
      evt("NVDA:1", "analyst_started", { node: "Sentiment Analyst" }, "3"),
      evt("NVDA:1", "analyst_completed", { stage: "sentiment", report_excerpt: "sentiment ok" }, "4"),
    ]} />);
    fireEvent.click(screen.getByText("Market Analyst"));
    expect(screen.getByTestId("stage-market-details")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Sentiment Analyst"));
    expect(screen.getByTestId("stage-sentiment-details")).toBeInTheDocument();
    expect(screen.queryByTestId("stage-market-details")).not.toBeInTheDocument();
  });
});

describe("PipelineFlow — stage detail content", () => {
  it("shows thinking log when stage is running", () => {
    render(<PipelineFlow events={[
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_thinking", { text_preview: "q1" }, "2"),
      evt("NVDA:1", "analyst_thinking", { text_fragment: "answer chunk" }, "3"),
    ]} />);
    fireEvent.click(screen.getByText("Market Analyst"));
    expect(screen.getByText(/q1/)).toBeInTheDocument();
    expect(screen.getByText(/answer chunk/)).toBeInTheDocument();
  });

  it("shows report excerpt for done stage", () => {
    render(<PipelineFlow events={[
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "1"),
      evt("NVDA:1", "analyst_completed", { stage: "market", summary: "completed", report_excerpt: "Bullish on NVDA long-term", report_text: "Full analysis" }, "2"),
    ]} />);
    fireEvent.click(screen.getByText("Market Analyst"));
    expect(screen.getByText(/Bullish on NVDA long-term/)).toBeInTheDocument();
  });
});

describe("PipelineFlow — team timer", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-14T10:00:10.000Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows live elapsed timer for an active team", () => {
    const e: WsEvent = {
      v: 1, type: "analyst_started", ts: "2026-06-14T10:00:05.000Z",
      run_id: "NVDA:1", data: { node: "Market Analyst" }, id: "1",
    };
    render(<PipelineFlow events={[e]} />);
    expect(screen.getByText("5s")).toBeInTheDocument();
  });
});
