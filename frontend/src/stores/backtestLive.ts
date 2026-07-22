/** Live state of the CURRENT interactive backtest run, fed by SSE
 * (backtest_progress / backtest_trade / backtest_done / backtest_error)
 * with a polling fallback. Terminal events are SLIM — the saved record +
 * artifacts carry the full result, fetched via queries — so this store
 * only tracks the in-flight view. Reset when a new run starts. */
import { create } from "zustand";

import type { BacktestTrade } from "@/lib/api/types";

export interface BacktestProgress {
  /** "fetching" while bars are paged from the vendor; absent while deciding */
  phase?: string;
  bars_have?: number;
  bars_needed?: number;
  decisions?: number;
  total?: number;
  pct?: number;
  open_count?: number;
  closed_trades?: number;
  equity?: number;
  pnl?: number;
  last_time?: string;
}

interface BacktestLiveState {
  jobId: string | null;
  /** wall-clock ms when the client learned the run started — grace window
   * before an "idle" poll is treated as a lost job */
  startedAt: number | null;
  status: "idle" | "running" | "done" | "cancelled" | "error";
  /** id of the finished run to show as the result (set by the slim
   * terminal event; the page fetches the record + artifacts) */
  finishedRunId: string | null;
  progress: BacktestProgress | null;
  openTrades: BacktestTrade[];
  closedTrades: BacktestTrade[];
  closedTotal: number;
  equityCurve: number[];
  error: string | null;
  start: (jobId: string) => void;
  setProgress: (p: BacktestProgress, open: BacktestTrade[]) => void;
  addTrade: (t: BacktestTrade) => void;
  syncClosed: (trades: BacktestTrade[], total: number) => void;
  finish: (status: "done" | "cancelled", runId: string | null) => void;
  setError: (message: string) => void;
  reset: () => void;
}

const EMPTY = {
  jobId: null,
  startedAt: null,
  status: "idle" as const,
  finishedRunId: null,
  progress: null,
  openTrades: [] as BacktestTrade[],
  closedTrades: [] as BacktestTrade[],
  closedTotal: 0,
  equityCurve: [] as number[],
  error: null,
};

export const useBacktestLiveStore = create<BacktestLiveState>()((set) => ({
  ...EMPTY,
  start: (jobId) =>
    set({ ...EMPTY, jobId, startedAt: Date.now(), status: "running" }),
  // monotonic: ignore stale frames (SSE and the polling fallback can arrive
  // out of order); only append to the equity curve when the run advances
  setProgress: (progress, openTrades) =>
    set((s) => {
      const prev = s.progress?.decisions ?? -1;
      const next = progress.decisions ?? -1;
      if (progress.phase !== "fetching" && next >= 0 && next < prev) return s;
      const advanced = next > prev && progress.equity != null;
      return {
        status: "running",
        progress,
        openTrades,
        equityCurve: advanced
          ? [...s.equityCurve, progress.equity!]
          : s.equityCurve,
      };
    }),
  addTrade: (t) =>
    set((s) => ({
      closedTrades: [...s.closedTrades, t],
      closedTotal: Math.max(s.closedTotal + 1, s.closedTrades.length + 1),
    })),
  // reconcile from a polled snapshot (last-100 tail + authoritative total)
  syncClosed: (trades, total) =>
    set((s) =>
      total > s.closedTotal ? { closedTrades: trades, closedTotal: total } : s,
    ),
  finish: (status, runId) =>
    set({ status, finishedRunId: runId, progress: null, openTrades: [] }),
  setError: (error) => set({ status: "error", error }),
  reset: () => set({ ...EMPTY }),
}));
