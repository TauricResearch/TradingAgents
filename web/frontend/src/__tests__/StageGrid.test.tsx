import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { StageGrid } from "../components/StageGrid";
import { useUi } from "../store/ui";
import type { WsEvent } from "../lib/events";

const evt = (runId: number, type: string, data: any, id: number): WsEvent => ({
  v: 1, type: type as any, ts: `t${id}`, run_id: runId, data, id,
});

const setup = (events: WsEvent[], focused = "NVDA", runId = 1) => {
  useUi.setState({
    focusedTicker: focused,
    lastRunIdByTicker: { [focused]: runId },
    eventBuffer: events,
    activeRunIdByTicker: {},
  });
};

describe("StageGrid", () => {
  beforeEach(() => {
    useUi.setState({
      focusedTicker: null,
      lastRunIdByTicker: {},
      eventBuffer: [],
      activeRunIdByTicker: {},
    });
  });

  it("marks a stage as done when analyst_completed fires", () => {
    setup([
      evt(1, "analyst_started", { node: "Market Analyst" }, 1),
      evt(1, "analyst_completed", { stage: "market", summary: "completed" }, 2),
    ]);
    render(<StageGrid />);
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).toBe("done");
  });

  it("stays done when subsequent tool nodes fire", () => {
    setup([
      evt(1, "analyst_started", { node: "Market Analyst" }, 1),
      evt(1, "analyst_completed", { stage: "market", summary: "completed" }, 2),
      evt(1, "analyst_started", { node: "tools_market" }, 3),
    ]);
    render(<StageGrid />);
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).toBe("done");
  });

  it("uses the stage key map for completion, not node-name substring", () => {
    setup([
      evt(1, "analyst_started", { node: "Sentiment Analyst" }, 1),
      evt(1, "analyst_completed", { stage: "sentiment", summary: "completed" }, 2),
    ]);
    render(<StageGrid />);
    expect(screen.getByTestId("stage-sentiment").getAttribute("data-status")).toBe("done");
  });

  it("only considers the focused run's events", () => {
    setup([
      evt(1, "analyst_completed", { stage: "market", summary: "completed" }, 1),
      evt(2, "analyst_started", { node: "Market Analyst" }, 2),
    ], "NVDA", 1);
    render(<StageGrid />);
    // Focused run 1 has the completion; the stray started from run 2 must not affect stage-market.
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).toBe("done");
  });
});
