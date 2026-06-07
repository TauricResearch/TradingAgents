import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { HistoryChart } from "./components/HistoryChart";
import type { Bar, RunLike, Verdict } from "./verdicts";

const t0 = "2026-06-01T12:00:00Z";
const t1 = "2026-06-01T13:00:00Z";
const bars: Bar[] = [
  { t: t0, o: 100, h: 101, l: 99, c: 100.5, v: 1000 },
  { t: t1, o: 100.5, h: 102, l: 100, c: 101, v: 1000 },
];
const runBuy: RunLike = { id: "buy-1", startedAt: t0, decisionAction: "BUY", decisionTarget: 105, startPrice: 100 };
const runHold: RunLike = { id: "hold-1", startedAt: t0, decisionAction: "HOLD", decisionTarget: null, startPrice: 100 };
const verdicts = new Map<string, Verdict>([
  ["buy-1",  { runId: "buy-1",  status: "right", reason: "target_hit",         pctMove: 1.0, targetHit: true,  maxHigh: 102, minLow: 100, endPrice: 101 }],
  ["hold-1", { runId: "hold-1", status: "right", reason: "within_threshold",  pctMove: 1.0, targetHit: null, maxHigh: 102, minLow: 100, endPrice: 101 }],
]);

const baseProps = {
  bars, runs: [runBuy, runHold], verdicts,
  deltaMs: 60 * 60 * 1000, holdThresholdPct: 1.0,
  nowIso: "2026-06-01T15:00:00Z", selectedRunId: "buy-1",
  resolution: "1h" as const, rangeStartIso: t0, rangeEndIso: t1,
};

describe("HistoryChart", () => {
  it("renders a recharts Surface", () => {
    const { container } = render(<HistoryChart {...baseProps} />);
    expect(container.querySelector(".recharts-surface")).toBeTruthy();
  });

  it("renders one ReferenceArea per run", () => {
    const { container } = render(<HistoryChart {...baseProps} />);
    expect(container.querySelectorAll(".recharts-reference-area")).toHaveLength(2);
  });

  it("renders a ReferenceLine for BUY target but not for HOLD, plus the now-cursor", () => {
    const { container } = render(<HistoryChart {...baseProps} />);
    // 1 target line for BUY, 1 now cursor. HOLD has no target line.
    expect(container.querySelectorAll(".recharts-reference-line")).toHaveLength(2);
  });

  it("renders a ReferenceDot per run", () => {
    const { container } = render(<HistoryChart {...baseProps} />);
    expect(container.querySelectorAll(".recharts-reference-dot")).toHaveLength(2);
  });

  it("always renders the now-cursor ReferenceLine even with no runs", () => {
    const { container } = render(
      <HistoryChart {...baseProps} runs={[]} verdicts={new Map()} selectedRunId={null} />,
    );
    // No runs → 0 target lines, 1 now cursor.
    expect(container.querySelectorAll(".recharts-reference-line")).toHaveLength(1);
  });
});
