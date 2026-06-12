import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getTickerHistory, type HistoryRange, type RunDetail, type Bar,
} from "../lib/api";
import { useUi, type HistoryPollInterval } from "../store/ui";
import {
  computeStats, computeVerdict, computeAccuracyCurve, computeDeltasFromRuns,
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

  // Max plot points from env (default 100)
  const maxPlotPoints = Number(import.meta.env.VITE_ACCURACY_PLOT_POINTS) || 100;

  // Derive deltas from actual run-bar data (independent of slider)
  const accuracyDeltas: number[] = useMemo(
    () => computeDeltasFromRuns(runs.map(toRunLike), bars, maxPlotPoints),
    [runs, bars, maxPlotPoints],
  );

  // Accuracy curve across all deltas
  const accuracyCurve: AccuracyPoint[] = useMemo(
    () => computeAccuracyCurve(runs.map(toRunLike), bars, accuracyDeltas, holdThresholdPct, tick.nowIso),
    [runs, bars, accuracyDeltas, holdThresholdPct, tick.nowIso],
  );

  // Zoom state for accuracy plots (shared x-axis domain)
  const [zoomLevel, setZoomLevel] = useState(0);
  const accuracyXDomain: [number, number] | undefined = useMemo(() => {
    if (accuracyCurve.length === 0) return undefined;
    if (zoomLevel === 0) return undefined;
    const fullMin = Math.min(...accuracyCurve.map(p => p.delta));
    const fullMax = Math.max(...accuracyCurve.map(p => p.delta));
    if (fullMin <= 0) return undefined;
    const logMin = Math.log(fullMin);
    const logMax = Math.log(fullMax);
    const logCenter = (logMin + logMax) / 2;
    const logHalfSpan = (logMax - logMin) / 2;
    const factor = Math.pow(0.8, -zoomLevel); // negative zoomLevel = zoom in
    const newLogHalfSpan = logHalfSpan * factor;
    return [Math.exp(logCenter - newLogHalfSpan), Math.exp(logCenter + newLogHalfSpan)] as [number, number];
  }, [accuracyCurve, zoomLevel]);

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
            {accuracyCurve.length > 0 && (
              <div className="relative">
                <div className="absolute top-1 right-2 z-10 flex items-center gap-1">
                  <button
                    onClick={() => setZoomLevel(z => z + 1)}
                    className="text-xs text-slate-500 hover:text-slate-900 bg-white/80 rounded px-1"
                    title="Zoom in"
                  >+</button>
                  <button
                    onClick={() => setZoomLevel(z => Math.min(z - 1, 0))}
                    className="text-xs text-slate-500 hover:text-slate-900 bg-white/80 rounded px-1"
                    title="Zoom out"
                  >-</button>
                  <button
                    onClick={() => setZoomLevel(0)}
                    className="text-xs text-slate-500 hover:text-slate-900 bg-white/80 rounded px-1"
                    title="Reset zoom"
                  >↺</button>
                </div>
                <AccuracyPlot data={accuracyCurve} xDomain={accuracyXDomain} />
              </div>
            )}

            {/* Successes & Failures vs Δ plot */}
            {accuracyCurve.length > 0 && <SuccessFailurePlot data={accuracyCurve} xDomain={accuracyXDomain} />}

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
