# History Accuracy Plots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace text stats in the historical analysis drawer with three plots: accuracy vs delta (line), successes & failures vs delta (combined line), with the delta slider moved next to the OHLC chart controls.

**Architecture:** All computation is client-side in `verdicts.ts` (pure functions, no React). Two new recharts components (`AccuracyPlot`, `SuccessFailurePlot`). The drawer wires them together via `useMemo`. The delta slider is moved from below stats into the toolbar row.

**Tech Stack:** TypeScript, React 19, recharts ^2.15.4, vitest, zustand, @tanstack/react-query

---

### Task 1: Add verdict functions for accuracy curve

**Files:**
- Modify: `web/frontend/src/verdicts.ts` (append new functions)
- Modify: `web/frontend/src/verdicts.test.ts` (append new tests)

- [ ] **Step 1: Add tests for `findNearestBar`**

Append to `verdicts.test.ts`:

```typescript
import { ..., findNearestBar, computeAccuracyCurve, ACCURACY_DELTAS } from "./verdicts";

describe("findNearestBar", () => {
  it("returns the bar whose timestamp is closest to the target", () => {
    const bars = [
      bar("2026-06-01T12:00:00Z", 100),
      bar("2026-06-01T13:00:00Z", 101),
      bar("2026-06-01T14:00:00Z", 102),
    ];
    // target exactly at 13:30 → bar at 14:00 is 30m away, 13:00 is 30m away → 13:00 wins (first)
    expect(findNearestBar(bars, new Date("2026-06-01T13:30:00Z").getTime())!.t).toBe("2026-06-01T13:00:00Z");
    // target at 12:45 → 12:00 is 45m away, 13:00 is 15m away → 13:00 wins
    expect(findNearestBar(bars, new Date("2026-06-01T12:45:00Z").getTime())!.t).toBe("2026-06-01T13:00:00Z");
    // target exactly at a bar
    expect(findNearestBar(bars, new Date("2026-06-01T13:00:00Z").getTime())!.t).toBe("2026-06-01T13:00:00Z");
  });

  it("returns null for empty bars", () => {
    expect(findNearestBar([], 1000)).toBeNull();
  });

  it("handles single bar", () => {
    const bars = [bar("2026-06-01T12:00:00Z", 100)];
    expect(findNearestBar(bars, 0)!.t).toBe("2026-06-01T12:00:00Z");
    expect(findNearestBar(bars, 1e15)!.t).toBe("2026-06-01T12:00:00Z");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd web/frontend
npx vitest run src/verdicts.test.ts --reporter=verbose
```
Expected: FAIL — `findNearestBar` not imported/defined.

- [ ] **Step 3: Implement `findNearestBar` in verdicts.ts**

Append before the `computeStats` function:

```typescript
/**
 * Find the bar whose timestamp is closest to `targetTimeMs`.
 * Returns null for an empty array.
 */
export function findNearestBar(bars: Bar[], targetTimeMs: number): Bar | null {
  if (bars.length === 0) return null;
  let best = bars[0];
  let bestDist = Math.abs(isoToMs(bars[0].t) - targetTimeMs);
  for (let i = 1; i < bars.length; i++) {
    const dist = Math.abs(isoToMs(bars[i].t) - targetTimeMs);
    if (dist < bestDist) {
      bestDist = dist;
      best = bars[i];
    }
  }
  return best;
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd web/frontend
npx vitest run src/verdicts.test.ts --reporter=verbose
```
Expected: PASS for `findNearestBar` tests.

- [ ] **Step 5: Add tests for `computeAccuracyCurve` and ACCURACY_DELTAS**

Append to `verdicts.test.ts`:

```typescript
describe("computeAccuracyCurve", () => {
  const t0 = "2026-06-01T12:00:00Z";

  function runWith(id: string, action: "BUY" | "SELL" | "HOLD", target: number | null, startPrice: number): RunLike {
    return { id, startedAt: t0, decisionAction: action, decisionTarget: target, startPrice };
  }

  it("returns one point per delta, filtering out unscored deltas", () => {
    // build bars covering every delta target time
    const bars: Bar[] = [];
    // prices go up → BUY without target is right
    const testDeltas = [5 * 60_000, 30 * 60_000]; // 5m, 30m
    for (const d of testDeltas) {
      const t = new Date(new Date(t0).getTime() + d).toISOString().replace(/\.\d{3}Z$/, "Z");
      bars.push(bar(t, 105, 100, 106, 99, 1000));
    }
    const runs = [runWith("r1", "BUY", null, 100)];

    const curve = computeAccuracyCurve(runs, bars, testDeltas, 1.0, "2026-06-02T12:00:00Z");
    expect(curve.length).toBe(2);
    for (const p of curve) {
      expect(p.right).toBe(1);
      expect(p.wrong).toBe(0);
      expect(p.rightPct).toBe(1.0);
    }
  });

  it("omits deltas where no runs have scoring data", () => {
    const bars: Bar[] = [bar(t0, 100)];
    const runs = [runWith("r1", "BUY", null, 100)];
    const deltas = [5 * 60_000]; // no bar at T+5m
    const curve = computeAccuracyCurve(runs, bars, deltas, 1.0, "2026-06-02T12:00:00Z");
    // 5m delta: no bar at T+5m → nearest bar is T itself → no_data? Actually nearestBar is T, startPrice=100, endPrice=100 → tie → unknown
    // So no scored runs → filtered out
    expect(curve.length).toBe(0);
  });

  it("works with the full ACCURACY_DELTAS set", () => {
    const bars: Bar[] = [];
    for (const d of ACCURACY_DELTAS) {
      const t = new Date(new Date(t0).getTime() + d).toISOString().replace(/\.\d{3}Z$/, "Z");
      bars.push(bar(t, 105, 100, 106, 99, 1000));
    }
    const runs = [runWith("r1", "BUY", null, 100)];
    const curve = computeAccuracyCurve(runs, bars, ACCURACY_DELTAS, 1.0, "2026-06-02T12:00:00Z");
    expect(curve.length).toBe(ACCURACY_DELTAS.length);
    for (const p of curve) {
      expect(p.rightPct).toBe(1.0);
    }
  });

  it("respects holdThresholdPct", () => {
    const bars = [bar(new Date(new Date(t0).getTime() + 5 * 60_000).toISOString().replace(/\.\d{3}Z$/, "Z"), 100.2)];
    const runs = [runWith("r1", "HOLD", null, 100)]; // 0.2% move, within 0.5% threshold
    const curve = computeAccuracyCurve(runs, bars, [5 * 60_000], 0.5, "2026-06-02T12:00:00Z");
    expect(curve[0].right).toBe(1);
    expect(curve[0].rightPct).toBe(1.0);
  });
});
```

- [ ] **Step 6: Run tests to verify failures**

```bash
cd web/frontend
npx vitest run src/verdicts.test.ts --reporter=verbose
```
Expected: FAIL — `computeAccuracyCurve`, `ACCURACY_DELTAS` not imported/defined.

- [ ] **Step 7: Implement `AccuracyPoint`, `ACCURACY_DELTAS`, `computeAccuracyCurve` in verdicts.ts**

Append to `verdicts.ts` after `computeStats`:

```typescript
// ---- Accuracy-curve types and functions ----

export type AccuracyPoint = {
  delta: number;
  total: number;
  right: number;
  wrong: number;
  unknown: number;
  rightPct: number | null;
};

/** Fixed set of delta horizons for the accuracy curve. */
export const ACCURACY_DELTAS: number[] = [
  5 * 60_000,               // 5m
  15 * 60_000,              // 15m
  30 * 60_000,              // 30m
  60 * 60_000,              // 1h
  2 * 60 * 60_000,          // 2h
  4 * 60 * 60_000,          // 4h
  8 * 60 * 60_000,          // 8h
  24 * 60 * 60_000,         // 1d
  3 * 24 * 60 * 60_000,     // 3d
  7 * 24 * 60 * 60_000,     // 1w
  14 * 24 * 60 * 60_000,    // 2w
  30 * 24 * 60 * 60_000,    // 1mo (approx)
  90 * 24 * 60 * 60_000,    // 3mo
  182 * 24 * 60 * 60_000,   // 6mo
  365 * 24 * 60 * 60_000,   // 1y
];

/**
 * Compute a verdict for a run using the single bar nearest to T+Δ.
 * Thin wrapper around `computeVerdict` — finds the closest bar to the
 * target time and passes it as a single-element window.
 */
export function computeVerdictNearestPrice(
  run: RunLike,
  bars: Bar[],
  deltaMs: number,
  holdThresholdPct: number,
  nowIso: string,
): Verdict {
  const targetTimeMs = isoToMs(run.startedAt) + deltaMs;
  const nearestBar = findNearestBar(bars, targetTimeMs);
  const windowBars = nearestBar ? [nearestBar] : [];
  return computeVerdict(run, windowBars, deltaMs, holdThresholdPct, nowIso);
}

/**
 * Compute the accuracy curve: for each delta horizon, compute aggregate
 * stats across all runs using nearest-price evaluation.
 *
 * Deltas where no runs have scoring data (right + wrong === 0) are
 * omitted from the result array.
 */
export function computeAccuracyCurve(
  runs: RunLike[],
  bars: Bar[],
  deltas: number[],
  holdThresholdPct: number,
  nowIso: string,
): AccuracyPoint[] {
  const out: AccuracyPoint[] = [];
  for (const delta of deltas) {
    let right = 0, wrong = 0, unknown = 0;
    for (const run of runs) {
      const v = computeVerdictNearestPrice(run, bars, delta, holdThresholdPct, nowIso);
      if (v.status === "right") right++;
      else if (v.status === "wrong") wrong++;
      else unknown++;
    }
    if (right + wrong === 0) continue; // skip unscored
    const rightPct = right / (right + wrong);
    out.push({ delta, total: runs.length, right, wrong, unknown, rightPct });
  }
  return out;
}
```

- [ ] **Step 8: Update the import in verdicts.test.ts**

Replace the existing import line:
```typescript
import { barsInWindow, computeVerdict, computeStats, type Bar, type RunLike } from "./verdicts";
```
With:
```typescript
import { barsInWindow, computeVerdict, computeStats, findNearestBar, computeAccuracyCurve, ACCURACY_DELTAS, type Bar, type RunLike } from "./verdicts";
```

- [ ] **Step 9: Run all verdict tests to verify they pass**

```bash
cd web/frontend
npx vitest run src/verdicts.test.ts --reporter=verbose
```
Expected: ALL PASS

- [ ] **Step 10: Commit**

```bash
git add web/frontend/src/verdicts.ts web/frontend/src/verdicts.test.ts
git commit -m "feat(verdicts): add findNearestBar, computeAccuracyCurve, ACCURACY_DELTAS"
```

---

### Task 2: Create AccuracyPlot component

**Files:**
- Create: `web/frontend/src/components/AccuracyPlot.tsx`

- [ ] **Step 1: Write the AccuracyPlot component**

```typescript
import { useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import type { AccuracyPoint } from "../verdicts";
import { fmtDelta, fmtPct } from "../lib/format";

// Recharts log scale doesn't handle 0 well; clamp domain floor to 5m.
const MIN_DELTA_MS = 5 * 60_000;

interface AccuracyPlotProps {
  data: AccuracyPoint[];
}

interface ChartPoint {
  delta: number;
  rightPct: number;
  label: string;
}

export function AccuracyPlot({ data }: AccuracyPlotProps) {
  const chartData: ChartPoint[] = useMemo(
    () => data.map((p) => ({ delta: p.delta, rightPct: p.rightPct ?? 0, label: fmtDelta(p.delta) })),
    [data],
  );

  if (chartData.length === 0) {
    return (
      <div className="h-48 flex items-center justify-center text-xs text-slate-400">
        No scored data for any delta.
      </div>
    );
  }

  return (
    <div className="h-48 border-b border-slate-200" data-testid="accuracy-plot">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
          <CartesianGrid stroke="#e2e8f0" strokeDasharray="2 2" />
          <XAxis
            dataKey="delta"
            type="number"
            scale="log"
            domain={[Math.min(...data.map(p => p.delta)), Math.max(...data.map(p => p.delta))]}
            tickFormatter={fmtDelta}
            tick={{ fontSize: 10, fill: "#64748b" }}
            stroke="#cbd5e1"
            minTickGap={24}
          />
          <YAxis
            domain={[0, 1]}
            tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
            width={36}
            tick={{ fontSize: 10, fill: "#64748b" }}
            stroke="#cbd5e1"
          />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const p = payload[0].payload as ChartPoint;
              const orig = data.find(d => d.delta === p.delta);
              if (!orig) return null;
              return (
                <div className="bg-white border border-slate-200 rounded shadow-sm px-2 py-1 text-xs">
                  <div className="font-medium text-slate-900">Δ {fmtDelta(orig.delta)}</div>
                  <div className="text-slate-700">Accuracy {fmtPct(orig.rightPct! * 100)}</div>
                  <div className="text-slate-500">{orig.right} right · {orig.wrong} wrong · {orig.unknown} unknown</div>
                </div>
              );
            }}
          />
          <Line
            type="monotone"
            dataKey="rightPct"
            stroke="#2563eb"
            strokeWidth={2}
            dot={{ r: 3, fill: "#2563eb", strokeWidth: 0 }}
            isAnimationActive={false}
            name="Accuracy"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/frontend/src/components/AccuracyPlot.tsx
git commit -m "feat(ui): create AccuracyPlot component"
```

---

### Task 3: Create SuccessFailurePlot component

**Files:**
- Create: `web/frontend/src/components/SuccessFailurePlot.tsx`

- [ ] **Step 1: Write the SuccessFailurePlot component**

```typescript
import { useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import type { AccuracyPoint } from "../verdicts";
import { fmtDelta } from "../lib/format";

interface SuccessFailurePlotProps {
  data: AccuracyPoint[];
}

interface ChartPoint {
  delta: number;
  success: number;
  failure: number;
  label: string;
}

export function SuccessFailurePlot({ data }: SuccessFailurePlotProps) {
  const chartData: ChartPoint[] = useMemo(
    () => data.map((p) => ({ delta: p.delta, success: p.right, failure: p.wrong, label: fmtDelta(p.delta) })),
    [data],
  );

  if (chartData.length === 0) {
    return (
      <div className="h-40 flex items-center justify-center text-xs text-slate-400">
        No scored data for any delta.
      </div>
    );
  }

  return (
    <div className="h-40 border-b border-slate-200" data-testid="success-failure-plot">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
          <CartesianGrid stroke="#e2e8f0" strokeDasharray="2 2" />
          <XAxis
            dataKey="delta"
            type="number"
            scale="log"
            domain={[Math.min(...data.map(p => p.delta)), Math.max(...data.map(p => p.delta))]}
            tickFormatter={fmtDelta}
            tick={{ fontSize: 10, fill: "#64748b" }}
            stroke="#cbd5e1"
            minTickGap={24}
          />
          <YAxis
            domain={[0, "auto"]}
            width={28}
            tick={{ fontSize: 10, fill: "#64748b" }}
            stroke="#cbd5e1"
            allowDecimals={false}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const p = payload[0].payload as ChartPoint;
              return (
                <div className="bg-white border border-slate-200 rounded shadow-sm px-2 py-1 text-xs">
                  <div className="font-medium text-slate-900">Δ {fmtDelta(p.delta)}</div>
                  <div className="text-green-600">{p.success} succeeded</div>
                  <div className="text-red-600">{p.failure} failed</div>
                </div>
              );
            }}
          />
          <Legend
            wrapperStyle={{ fontSize: 10, color: "#64748b" }}
            iconType="plainline"
          />
          <Line
            type="monotone"
            dataKey="success"
            stroke="#16a34a"
            strokeWidth={2}
            dot={{ r: 3, fill: "#16a34a", strokeWidth: 0 }}
            isAnimationActive={false}
            name="Successes"
          />
          <Line
            type="monotone"
            dataKey="failure"
            stroke="#dc2626"
            strokeWidth={2}
            dot={{ r: 3, fill: "#dc2626", strokeWidth: 0 }}
            isAnimationActive={false}
            name="Failures"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/frontend/src/components/SuccessFailurePlot.tsx
git commit -m "feat(ui): create SuccessFailurePlot component"
```

---

### Task 4: Update HistoricalAnalysisDrawer

**Files:**
- Modify: `web/frontend/src/components/HistoricalAnalysisDrawer.tsx`

- [ ] **Step 1: Modify the drawer to wire new plots and move controls**

Replace the content of `HistoricalAnalysisDrawer.tsx` with the updated version:

```typescript
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getTickerHistory, type HistoryRange, type RunDetail, type Bar,
} from "../lib/api";
import { useUi, type HistoryPollInterval } from "../store/ui";
import {
  computeStats, computeVerdict, computeAccuracyCurve, ACCURACY_DELTAS,
  type Verdict, type AccuracyPoint,
} from "../verdicts";
import { HistoryChart } from "./HistoryChart";
import { HistoryControls } from "./HistoryControls";
import { AccuracyPlot } from "./AccuracyPlot";
import { SuccessFailurePlot } from "./SuccessFailurePlot";
import { RunListItem } from "./RunListItem";
import { type CandleResolution, RESOLUTION_MS, scaleFor } from "../lib/resolution";

// --- helpers ---

function resampleBars(bars: Bar[], resolution: Exclude<CandleResolution, "auto">): Bar[] {
  const targetMs = RESOLUTION_MS[resolution];
  if (bars.length === 0) return [];
  const buckets = new Map<number, Bar[]>();
  for (const b of bars) {
    const t = new Date(b.t).getTime();
    const bucket = Math.floor(t / targetMs) * targetMs;
    let arr = buckets.get(bucket);
    if (!arr) { arr = []; buckets.set(bucket, arr); }
    arr.push(b);
  }
  return Array.from(buckets.keys()).sort((a, b) => a - b).map((k) => {
    const group = buckets.get(k)!;
    return {
      t: new Date(k).toISOString().replace(/\.\d{3}Z$/, "Z"),
      o: group[0].o,
      h: group.reduce((m, b) => Math.max(m, b.h), -Infinity),
      l: group.reduce((m, b) => Math.min(m, b.l), Infinity),
      c: group[group.length - 1].c,
      v: group.reduce((s, b) => s + b.v, 0),
    };
  });
}

const CANDLE_OPTIONS: Array<{ label: string; value: CandleResolution }> = [
  { label: "Auto", value: "auto" },
  { label: "1m", value: "1m" },
  { label: "5m", value: "5m" },
  { label: "15m", value: "15m" },
  { label: "1h", value: "1h" },
  { label: "4h", value: "4h" },
  { label: "1d", value: "1d" },
  { label: "1w", value: "1w" },
];

const REFRESH_OPTIONS: Array<{ label: string; value: HistoryPollInterval }> = [
  { label: "Off", value: 0 },
  { label: "5s", value: 5_000 },
  { label: "15s", value: 15_000 },
  { label: "30s", value: 30_000 },
  { label: "1m", value: 60_000 },
  { label: "5m", value: 300_000 },
];

function toRunLike(run: RunDetail) {
  return {
    id: run.id,
    startedAt: run.started_at ?? "",
    decisionAction: (run.decision_action ?? null) as "BUY" | "SELL" | "HOLD" | null,
    decisionTarget: run.decision_target,
    startPrice: run.start_price,
  };
}

function useTickingNow(intervalMs: number): { nowIso: string; nowMs: number } {
  const [tick, setTick] = useState(() => {
    const d = new Date();
    return { nowIso: d.toISOString(), nowMs: d.getTime() };
  });
  useEffect(() => {
    if (intervalMs <= 0) return;
    const id = window.setInterval(() => {
      const d = new Date();
      setTick({ nowIso: d.toISOString(), nowMs: d.getTime() });
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return tick;
}

// --- main component ---

export function HistoricalAnalysisDrawer({ ticker, onClose }: { ticker: string; onClose: () => void }) {
  const holdThresholdPct = useUi((s) => s.holdThresholdPct);
  const historyPollIntervalMs = useUi((s) => s.historyPollIntervalMs);
  const setHistoryPollIntervalMs = useUi((s) => s.setHistoryPollIntervalMs);
  const focusedRunId = useUi((s) => {
    const hist = s.historicalRunIdByTicker[ticker];
    if (hist != null) return hist;
    return s.lastRunIdByTicker[ticker] ?? null;
  });
  const setHistoricalRunForTicker = useUi((s) => s.setHistoricalRunForTicker);

  const [range, setRange] = useState<HistoryRange>("auto");
  const [deltaMs, setDeltaMs] = useState<number>(60 * 60 * 1000);
  const candleResolution = useUi((s) => s.candleResolution);
  const setCandleResolution = useUi((s) => s.setCandleResolution);
  const tick = useTickingNow(1000);

  const query = useQuery({
    queryKey: ["ticker-history", ticker, range],
    queryFn: () => getTickerHistory(ticker, range),
    refetchInterval: historyPollIntervalMs > 0 ? historyPollIntervalMs : false,
    staleTime: 0,
    enabled: !!ticker,
  });

  const data = query.data;
  const runs: RunDetail[] = data?.runs ?? [];
  const bars: Bar[] = data?.bars ?? [];
  const apiResolution = (data?.resolution ?? "1h") as "1m" | "1h" | "1d";
  const rangeStartIso = data?.range_start ?? tick.nowIso;
  const rangeEndIso = data?.range_end ?? tick.nowIso;

  const effectiveResolution: "1m" | "5m" | "15m" | "1h" | "4h" | "1d" | "1w" =
    candleResolution === "auto" ? apiResolution : candleResolution;
  const scale = scaleFor(effectiveResolution);

  const resampledBars: Bar[] = useMemo(
    () => (candleResolution === "auto" ? bars : resampleBars(bars, candleResolution)),
    [bars, candleResolution],
  );

  // Single-delta verdicts for OHLC chart (uses the slider-selected deltaMs)
  const verdicts = useMemo(() => {
    const out = new Map<string, Verdict>();
    for (const run of runs) {
      const rl = toRunLike(run);
      const startMs = new Date(rl.startedAt).getTime();
      const endMs = Math.min(startMs + deltaMs, tick.nowMs);
      const win = bars.filter((b) => {
        const t = new Date(b.t).getTime();
        return t >= startMs && t <= endMs;
      });
      out.set(run.id, computeVerdict(rl, win, deltaMs, holdThresholdPct, tick.nowIso));
    }
    return out;
  }, [runs, bars, deltaMs, holdThresholdPct, tick.nowIso, tick.nowMs]);

  // Accuracy curve across all deltas (independent of slider)
  const accuracyCurve: AccuracyPoint[] = useMemo(
    () => computeAccuracyCurve(runs.map(toRunLike), bars, ACCURACY_DELTAS, holdThresholdPct, tick.nowIso),
    [runs, bars, holdThresholdPct, tick.nowIso],
  );

  return (
    <div
      className="fixed inset-y-0 right-0 w-[28rem] max-w-full bg-white border-l border-slate-200 shadow-xl z-20 flex flex-col"
      data-testid="history-drawer"
    >
      <div className="flex items-center justify-between p-3 border-b border-slate-200">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold">{ticker}</h3>
          <select
            data-testid="range-select"
            value={range}
            onChange={(e) => setRange(e.target.value as HistoryRange)}
            className="text-xs border border-slate-300 rounded px-1 py-0.5 bg-white"
          >
            <option value="auto">Auto</option>
            <option value="1d">1d</option>
            <option value="5d">5d</option>
            <option value="1mo">1mo</option>
            <option value="3mo">3mo</option>
            <option value="6mo">6mo</option>
            <option value="1y">1y</option>
            <option value="all">All</option>
          </select>
        </div>
        <button onClick={onClose} className="text-sm text-slate-500">Close</button>
      </div>

      <div className="flex-1 min-h-0 flex flex-col">
        {query.isLoading ? (
          <div className="p-4 text-xs text-slate-500">Loading…</div>
        ) : query.isError ? (
          <div className="p-4 text-xs text-slate-700 space-y-2">
            <p>Failed to load price history: <span className="font-mono">{(query.error as Error).message}</span></p>
            <button onClick={() => query.refetch()} className="text-blue-600">Retry</button>
          </div>
        ) : bars.length === 0 && runs.length > 0 ? (
          <div className="p-4 text-xs text-slate-700 space-y-2">
            <p>No price data for this range.</p>
            <p className="text-slate-500">Try a different range preset — yfinance 1m data is only available for the last 7 days.</p>
            <button onClick={() => setRange("1y")} className="text-blue-600">Use 1y</button>
          </div>
        ) : (
          <>
            {/* Toolbar — Candle, Refresh, and Δ slider grouped together */}
            <div className="flex flex-col gap-1 border-b border-slate-100 shrink-0">
              <div className="flex items-center justify-end gap-3 px-2 py-1 text-xs">
                <div className="flex items-center gap-1">
                  <label htmlFor="candle-res-select" className="text-slate-500">Candle</label>
                  <select
                    id="candle-res-select"
                    data-testid="candle-res-select"
                    value={candleResolution}
                    onChange={(e) => setCandleResolution(e.target.value as CandleResolution)}
                    className="border border-slate-300 rounded px-1 py-0.5 bg-white"
                  >
                    {CANDLE_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
                <div className="flex items-center gap-1">
                  <label htmlFor="refresh-select" className="text-slate-500">Refresh</label>
                  <select
                    id="refresh-select"
                    data-testid="refresh-select"
                    value={historyPollIntervalMs}
                    onChange={(e) => setHistoryPollIntervalMs(Number(e.target.value) as HistoryPollInterval)}
                    className="border border-slate-300 rounded px-1 py-0.5 bg-white"
                  >
                    {REFRESH_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
              </div>
              {/* Δ slider moved here, below Candle/Refresh */}
              <div className="px-2 pb-1">
                <HistoryControls
                  deltaMs={deltaMs}
                  onDeltaChange={setDeltaMs}
                  compact
                />
              </div>
            </div>

            {/* OHLC Chart */}
            <div className="shrink-0">
              <HistoryChart
                bars={resampledBars}
                runs={runs.map(toRunLike)}
                verdicts={verdicts}
                deltaMs={deltaMs}
                holdThresholdPct={holdThresholdPct}
                nowIso={tick.nowIso}
                selectedRunId={focusedRunId}
                resolution={effectiveResolution}
                rangeStartIso={rangeStartIso}
                rangeEndIso={rangeEndIso}
              />
            </div>

            {/* Accuracy vs Δ plot */}
            {accuracyCurve.length > 0 && <AccuracyPlot data={accuracyCurve} />}

            {/* Successes & Failures vs Δ plot */}
            {accuracyCurve.length > 0 && <SuccessFailurePlot data={accuracyCurve} />}

            {/* Run list */}
            <div className="flex-1 min-h-0 overflow-y-auto border-t border-slate-200">
              {runs.length === 0 ? (
                <div className="p-4 text-xs text-slate-500">No runs for {ticker}.</div>
              ) : (
                runs.map((run) => (
                  <RunListItem
                    key={run.id}
                    run={{
                      id: run.id,
                      started_at: run.started_at,
                      decision_action: run.decision_action,
                      decision_target: run.decision_target,
                      start_price: run.start_price,
                    }}
                    verdict={verdicts.get(run.id) ?? {
                      runId: run.id, status: "unknown", reason: "no_data",
                      pctMove: null, targetHit: null, maxHigh: null, minLow: null, endPrice: null,
                    }}
                    selected={run.id === focusedRunId}
                    scale={scale}
                    onClick={() => setHistoricalRunForTicker(ticker, run.id)}
                  />
                ))
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/frontend/src/components/HistoricalAnalysisDrawer.tsx
git commit -m "feat(ui): wire accuracy plots, move delta slider to toolbar"
```

---

### Task 5: Update HistoryControls for compact mode + remove HistoryStats

**Files:**
- Modify: `web/frontend/src/components/HistoryControls.tsx`
- Delete: `web/frontend/src/components/HistoryStats.tsx`

- [ ] **Step 1: Add compact prop to HistoryControls**

Update `HistoryControls.tsx` to support a `compact` prop that removes labels and reduces padding:

```typescript
import { useUi } from "../store/ui";
import { fmtDelta, fmtPct } from "../lib/format";

export function HistoryControls({
  deltaMs,
  onDeltaChange,
  compact,
}: {
  deltaMs: number;
  onDeltaChange: (ms: number) => void;
  compact?: boolean;
}) {
  const holdThresholdPct = useUi((s) => s.holdThresholdPct);
  const setHoldThresholdPct = useUi((s) => s.setHoldThresholdPct);

  const min = 5 * 60_000;
  const max = 3 * 365 * 24 * 60 * 60_000;
  const logMin = Math.log(min);
  const logMax = Math.log(max);
  const posToDelta = (pos: number): number =>
    Math.exp(logMin + (pos / 1000) * (logMax - logMin));
  const deltaToPos = (ms: number): number =>
    ((Math.log(ms) - logMin) / (logMax - logMin)) * 1000;

  if (compact) {
    return (
      <div className="flex items-center gap-2 text-xs">
        <label htmlFor="delta-slider" className="text-slate-500 shrink-0">Δ</label>
        <input
          id="delta-slider"
          data-testid="delta-slider"
          type="range"
          min={0}
          max={1000}
          value={deltaToPos(deltaMs)}
          onChange={(e) => onDeltaChange(posToDelta(Number(e.target.value)))}
          className="flex-1 h-1.5"
        />
        <span className="w-10 text-right font-medium text-slate-900 shrink-0">{fmtDelta(deltaMs)}</span>
        <span className="text-slate-300 mx-1">|</span>
        <label htmlFor="hold-slider" className="text-slate-500 shrink-0">HOLD%</label>
        <input
          id="hold-slider"
          data-testid="hold-threshold-slider"
          type="range"
          min={0.1}
          max={5.0}
          step={0.1}
          value={holdThresholdPct}
          onChange={(e) => setHoldThresholdPct(Number(e.target.value))}
          className="w-16 h-1.5"
        />
        <span className="w-8 text-right font-medium text-slate-900 shrink-0">{fmtPct(holdThresholdPct)}</span>
      </div>
    );
  }

  return (
    <div className="border-b border-slate-200 px-3 py-2 text-xs space-y-2">
      <div className="flex items-center gap-2">
        <label htmlFor="delta-slider" className="w-12 text-slate-600">Δ</label>
        <input
          id="delta-slider"
          data-testid="delta-slider"
          type="range"
          min={0}
          max={1000}
          value={deltaToPos(deltaMs)}
          onChange={(e) => onDeltaChange(posToDelta(Number(e.target.value)))}
          className="flex-1"
        />
        <span className="w-12 text-right font-medium text-slate-900">{fmtDelta(deltaMs)}</span>
      </div>
      <div className="flex items-center gap-2">
        <label htmlFor="hold-slider" className="w-12 text-slate-600">HOLD%</label>
        <input
          id="hold-slider"
          data-testid="hold-threshold-slider"
          type="range"
          min={0.1}
          max={5.0}
          step={0.1}
          value={holdThresholdPct}
          onChange={(e) => setHoldThresholdPct(Number(e.target.value))}
          className="flex-1"
        />
        <span className="w-12 text-right font-medium text-slate-900">{fmtPct(holdThresholdPct)}</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Delete HistoryStats.tsx**

```bash
Remove-Item -LiteralPath "web/frontend/src/components/HistoryStats.tsx"
```

- [ ] **Step 3: Remove HistoryStats import from any remaining files**

Check for remaining imports:
```bash
rg "HistoryStats" web/frontend/src/
```
Expected: no matches (the import was removed from HistoricalAnalysisDrawer.tsx in Task 4).

- [ ] **Step 4: Verify the app builds**

```bash
cd web/frontend
npx tsc --noEmit
```
Expected: TypeScript compiles without errors.

- [ ] **Step 5: Run all tests**

```bash
cd web/frontend
npx vitest run --reporter=verbose
```
Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add web/frontend/src/components/HistoryControls.tsx
git add -A web/frontend/src/components/HistoryStats.tsx
git commit -m "feat(ui): add compact mode to HistoryControls, remove HistoryStats"
```

---

### Self-review check

1. **Spec coverage:**
   - ✓ Accuracy vs Δ line chart (Task 2)
   - ✓ Successes & Failures vs Δ line chart (Task 3)
   - ✓ OHLC chart kept as-is (Task 4)
   - ✓ Delta slider moved near OHLC chart (Tasks 4, 5)
   - ✓ HistoryStats removed (Task 5)
   - ✓ Discrete delta set (Task 1)
   - ✓ Nearest-price lookup for handling data gaps (Task 1)
   - ✓ Edge cases: empty data, all pending (built into plot components with conditional rendering)

2. **Placeholder scan:** No TBDs, TODOs, or "implement later" patterns. All code is complete.

3. **Type consistency:** All function signatures match across tasks (AccuracyPoint, findNearestBar, computeAccuracyCurve, ACCURACY_DELTAS). The `compact` prop on HistoryControls is new but backward compatible.
