import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getTickerHistory, type HistoryRange, type RunDetail, type Bar,
} from "../lib/api";
import { useUi } from "../store/ui";
import {
  computeStats, computeVerdict, type Verdict,
} from "../verdicts";
import { HistoryStats } from "./HistoryStats";
import { HistoryChart } from "./HistoryChart";
import { HistoryControls, type CandleResolution } from "./HistoryControls";
import { RunListItem } from "./RunListItem";

// --- helpers ---

function scaleFor(resolution: "1m" | "5m" | "15m" | "1h" | "4h" | "1d"): "m" | "h" | "d" {
  if (resolution === "1d") return "d";
  if (resolution === "1h" || resolution === "4h") return "h";
  return "m";
}

const RESOLUTION_MS: Record<Exclude<CandleResolution, "auto">, number> = {
  "1m": 60_000,
  "5m": 5 * 60_000,
  "15m": 15 * 60_000,
  "1h": 60 * 60_000,
  "4h": 4 * 60 * 60_000,
  "1d": 24 * 60 * 60_000,
};

/**
 * Re-bin raw API bars into a coarser resolution. Bars are bucketed by
 * their UTC timestamp; each bucket is collapsed into a single OHLCV
 * bar (first o, max h, min l, last c, sum v). If the chosen resolution
 * is finer than the source data, each bar lands in its own bucket so
 * the result is the same set of bars (no aggregation, no data loss).
 */
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
  const focusedRunId = useUi((s) => {
    const hist = s.historicalRunIdByTicker[ticker];
    if (hist != null) return hist;
    return s.lastRunIdByTicker[ticker] ?? null;
  });
  const setHistoricalRunForTicker = useUi((s) => s.setHistoricalRunForTicker);

  const [range, setRange] = useState<HistoryRange>("auto");
  // Default Δ = 1h so most "done" runs (which complete in minutes) are
  // evaluated immediately. The user can slide up to 3y to see the
  // "we don't know yet" cases for recent runs.
  const [deltaMs, setDeltaMs] = useState<number>(60 * 60 * 1000);
  // Candle resolution is independent of the data's API resolution and
  // independent of the verdict Δ window. "auto" = use whatever the API
  // returned; explicit values trigger client-side resampling.
  const [candleResolution, setCandleResolution] = useState<CandleResolution>("auto");
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

  // Effective resolution: explicit candle choice wins, otherwise the API's.
  const effectiveResolution: "1m" | "5m" | "15m" | "1h" | "4h" | "1d" =
    candleResolution === "auto" ? apiResolution : candleResolution;
  const scale = scaleFor(effectiveResolution);

  // Resample once when bars or the candle resolution change.
  const resampledBars: Bar[] = useMemo(
    () => (candleResolution === "auto" ? bars : resampleBars(bars, candleResolution)),
    [bars, candleResolution],
  );

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

  const stats = useMemo(
    () => computeStats(runs.map(toRunLike), bars, deltaMs, holdThresholdPct, tick.nowIso),
    [runs, bars, deltaMs, holdThresholdPct, tick.nowIso],
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

      <HistoryStats stats={stats} />

      <div className="flex-1 min-h-0">
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
        )}
      </div>

      <HistoryControls
        deltaMs={deltaMs}
        onDeltaChange={setDeltaMs}
        candleResolution={candleResolution}
        onCandleResolutionChange={setCandleResolution}
      />

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
    </div>
  );
}
