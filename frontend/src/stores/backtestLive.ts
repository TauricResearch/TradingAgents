/** Live state of the CURRENT interactive backtest run, fed by SSE
 * (backtest_progress / backtest_trade / backtest_done / backtest_error).
 * Reset when a new run starts. Not persisted — the completed run is
 * durable server-side in the Saved Runs history. */
import { create } from "zustand";

import type { BacktestRunView, BacktestTrade } from "@/lib/api/types";

export interface BacktestProgress {
  decisions: number;
  total: number;
  pct: number;
  open_count: number;
  closed_trades: number;
  equity: number;
  pnl: number;
  last_time?: string;
}

interface BacktestLiveState {
  jobId: string | null;
  status: "idle" | "running" | "done" | "error";
  progress: BacktestProgress | null;
  openTrades: BacktestTrade[];
  closedTrades: BacktestTrade[];
  equityCurve: number[];
  result: BacktestRunView | null;
  error: string | null;
  start: (jobId: string) => void;
  setProgress: (p: BacktestProgress, open: BacktestTrade[]) => void;
  addTrade: (t: BacktestTrade) => void;
  syncClosed: (trades: BacktestTrade[]) => void;
  setDone: (view: BacktestRunView) => void;
  setError: (message: string) => void;
  reset: () => void;
}

const EMPTY = {
  jobId: null,
  status: "idle" as const,
  progress: null,
  openTrades: [] as BacktestTrade[],
  closedTrades: [] as BacktestTrade[],
  equityCurve: [] as number[],
  result: null,
  error: null,
};

export const useBacktestLiveStore = create<BacktestLiveState>()((set) => ({
  ...EMPTY,
  start: (jobId) => set({ ...EMPTY, jobId, status: "running" }),
  // monotonic: ignore stale frames (SSE and the polling fallback can arrive
  // out of order); only append to the equity curve when the run advances
  setProgress: (progress, openTrades) =>
    set((s) => {
      if (s.progress && progress.decisions < s.progress.decisions) return s;
      const advanced = !s.progress || progress.decisions > s.progress.decisions;
      return {
        status: "running",
        progress,
        openTrades,
        equityCurve: advanced
          ? [...s.equityCurve, progress.equity]
          : s.equityCurve,
      };
    }),
  addTrade: (t) => set((s) => ({ closedTrades: [...s.closedTrades, t] })),
  // reconcile the closed list from a polled snapshot when SSE dropped some
  syncClosed: (trades) =>
    set((s) => (trades.length > s.closedTrades.length ? { closedTrades: trades } : s)),
  setDone: (result) => set({ status: "done", result, progress: null, openTrades: [] }),
  setError: (error) => set({ status: "error", error }),
  reset: () => set({ ...EMPTY }),
}));
