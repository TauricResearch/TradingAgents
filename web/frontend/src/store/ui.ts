import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { WsEvent } from "../lib/events";
import type { CandleResolution } from "../lib/resolution";

export type HistoryPollInterval = 0 | 5_000 | 15_000 | 30_000 | 60_000 | 300_000;

interface UiState {
  // Currently-focused ticker in the rail. Driving the main pane.
  focusedTicker: string | null;
  // Most-recent run id per ticker. Sticky: used to filter the global
  // event buffer when displaying a ticker. Cleared only when the user
  // explicitly resets (or, eventually, when the ticker is removed from
  // the watchlist).
  lastRunIdByTicker: Record<string, string | null>;
  // User-picked historical run id per ticker. When set, the
  // event-display hook prefers this over lastRunIdByTicker so the user
  // can inspect an older run without it being overwritten by a newer
  // one streaming in. Cleared when the user "resets" to the live view
  // (e.g. starts a new run, switches tickers).
  historicalRunIdByTicker: Record<string, string | null>;
  // Run id currently being WS-streamed per ticker. Cleared on terminal
  // events (run_finished / run_failed). Drives `useRunStream` so the
  // hook only opens a WS for the focused ticker while it's still live.
  activeRunIdByTicker: Record<string, string | null>;
  // Wall-clock ms timestamp when each active run started. Set when the
  // run is enqueued (in the start-mutation success handler), so it is
  // available before the run_started WS event arrives. Cleared when
  // the run finishes or fails.
  runStartedAtByTicker: Record<string, number | null>;
  // Global event buffer, bounded to the last 1000 events. Events are
  // already tagged with `run_id` by the server, so display components
  // filter by the focused ticker's run id.
  eventBuffer: WsEvent[];
  // Per-ticker drawer open/closed flag. Lives in the store so the
  // HistoricalAnalysisDrawer can be triggered from anywhere in the app,
  // but is NOT persisted — the drawer should be closed on reload.
  historyOpenByTicker: Record<string, boolean>;
  // Whether the "past runs" drawer (background runs table) is open.
  backgroundRunsOpen: boolean;
  // HOLD threshold in percent (0.1..5.0). Default 1.0. PERSISTED so
  // the user's "is this HOLD within tolerance" knob survives a refresh.
  holdThresholdPct: number;
  // Polling interval in ms for the history chart, or 0 to disable.
  // Default 30_000 (30s). PERSISTED.
  historyPollIntervalMs: HistoryPollInterval;
  // Candle resolution: independent of the data's API resolution and of
  // the verdict Δ window. "auto" = use whatever the API returns;
  // explicit values trigger client-side resampling. PERSISTED so the
  // user's preferred candle size survives a refresh.
  candleResolution: CandleResolution;
  // Per-group collapse/expand state for the watchlist. PERSISTED so
  // group collapse survives a refresh.
  watchlistCollapsedGroups: Record<string, boolean>;
  // User-selected custom colors per group name. PERSISTED.
  customGroupColors: Record<string, string>;
  // Group display order. PERSISTED.
  groupOrder: string[];
  // Mobile sidebar drawer open/closed.
  mobileSidebarOpen: boolean;
  // Desktop sidebar collapsed/expanded.
  sidebarCollapsed: boolean;
  // Ticker Accuracy Agent drawer open/closed.
  tickerAgentDrawerOpen: boolean;
  setFocusedTicker: (t: string | null) => void;
  setTickerAgentDrawerOpen: (open: boolean) => void;
  setLastRunIdForTicker: (ticker: string, runId: string | null) => void;
  setActiveRunIdForTicker: (ticker: string, runId: string | null) => void;
  clearActiveRunForTicker: (ticker: string) => void;
  setHistoricalRunForTicker: (ticker: string, runId: string | null) => void;
  clearHistoricalRunForTicker: (ticker: string) => void;
  appendEvent: (e: WsEvent) => void;
  restoreEvents: (runId: string, events: Array<{ id: string; type: string; ts: string | null; data: unknown }>) => void;
  clearEventBuffer: (runId: string) => void;
  clearLastRunIdForTicker: (ticker: string) => void;
  clearBuffer: () => void;
  setRunStartedAtForTicker: (ticker: string, startedAt: number | null) => void;
  setHistoryOpen: (ticker: string, open: boolean) => void;
  setBackgroundRunsOpen: (open: boolean) => void;
  setHoldThresholdPct: (pct: number) => void;
  setHistoryPollIntervalMs: (ms: HistoryPollInterval) => void;
  setCandleResolution: (r: CandleResolution) => void;
  setWatchlistCollapsedGroup: (name: string, collapsed: boolean) => void;
  setCustomGroupColor: (name: string, color: string) => void;
  removeCustomGroupColor: (name: string) => void;
  setGroupOrder: (order: string[]) => void;
  setMobileSidebarOpen: (open: boolean) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
}

export const useUi = create<UiState>()(
  persist(
    (set) => ({
      focusedTicker: null,
      lastRunIdByTicker: {},
      historicalRunIdByTicker: {},
      activeRunIdByTicker: {},
      runStartedAtByTicker: {},
      eventBuffer: [],
      historyOpenByTicker: {},
      backgroundRunsOpen: false,
      holdThresholdPct: 1.0,
      historyPollIntervalMs: 30_000,
      candleResolution: "auto",
      watchlistCollapsedGroups: {},
      customGroupColors: {},
      groupOrder: [],
      mobileSidebarOpen: false,
      tickerAgentDrawerOpen: false,
      sidebarCollapsed: false,
      setFocusedTicker: (t) => { set({ focusedTicker: t, mobileSidebarOpen: false }); },
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
      setTickerAgentDrawerOpen: (open) => set({ tickerAgentDrawerOpen: open }),
      setLastRunIdForTicker: (ticker, runId) =>
        set((s) => ({ lastRunIdByTicker: { ...s.lastRunIdByTicker, [ticker]: runId } })),
      setActiveRunIdForTicker: (ticker, runId) =>
        set((s) => ({ activeRunIdByTicker: { ...s.activeRunIdByTicker, [ticker]: runId } })),
      setRunStartedAtForTicker: (ticker, startedAt) =>
        set((s) => ({ runStartedAtByTicker: { ...s.runStartedAtByTicker, [ticker]: startedAt } })),
      clearActiveRunForTicker: (ticker) =>
        set((s) => ({ activeRunIdByTicker: { ...s.activeRunIdByTicker, [ticker]: null } })),
      setHistoricalRunForTicker: (ticker, runId) =>
        set((s) => ({ historicalRunIdByTicker: { ...s.historicalRunIdByTicker, [ticker]: runId } })),
      clearHistoricalRunForTicker: (ticker) =>
        set((s) => ({
          historicalRunIdByTicker: { ...s.historicalRunIdByTicker, [ticker]: null },
        })),
      appendEvent: (e) => set((s) => ({ eventBuffer: [...s.eventBuffer, e].slice(-1000) })),
      restoreEvents: (runId, events) => set((s) => {
        const others = s.eventBuffer.filter((e) => e.run_id !== runId);
        // Server-side REST events come back as {id, type, ts, data} (no
        // `v`, no `run_id`). Tag them with the canonical v=1 and the
        // focused run_id so the buffer is uniformly WsEvent[].
        const restored: WsEvent[] = events.map((e) => ({
          v: 1,
          type: e.type as WsEvent["type"],
          ts: e.ts ?? "",
          run_id: runId,
          data: e.data,
          id: e.id,
        }));
        return { eventBuffer: [...others, ...restored].slice(-1000) };
      }),
      clearEventBuffer: (runId) => set((s) => {
        const next = s.eventBuffer.filter((e) => e.run_id !== runId);
        return { eventBuffer: next };
      }),
      clearLastRunIdForTicker: (ticker) => set((s) => {
        const next = { ...s.lastRunIdByTicker };
        delete next[ticker];
        return { lastRunIdByTicker: next };
      }),
      clearBuffer: () => set({ eventBuffer: [] }),
      setHistoryOpen: (ticker, open) =>
        set((s) => ({ historyOpenByTicker: { ...s.historyOpenByTicker, [ticker]: open } })),
      setBackgroundRunsOpen: (open) => set({ backgroundRunsOpen: open }),
      setHoldThresholdPct: (pct) => set({ holdThresholdPct: pct }),
      setHistoryPollIntervalMs: (ms) => set({ historyPollIntervalMs: ms }),
      setCandleResolution: (r) => set({ candleResolution: r }),
      setWatchlistCollapsedGroup: (name, collapsed) =>
        set((s) => ({ watchlistCollapsedGroups: { ...s.watchlistCollapsedGroups, [name]: collapsed } })),
      setCustomGroupColor: (name, color) =>
        set((s) => ({ customGroupColors: { ...s.customGroupColors, [name]: color } })),
      removeCustomGroupColor: (name) =>
        set((s) => {
          const next = { ...s.customGroupColors };
          delete next[name];
          return { customGroupColors: next };
        }),
      setGroupOrder: (order) => set({ groupOrder: order }),
      setMobileSidebarOpen: (open) => set({ mobileSidebarOpen: open }),
    }),
    {
      name: "tradingagents-ui",
      storage: createJSONStorage(() => localStorage),
      // Persist only the user-visible state. The runtime-only
      // `activeRunIdByTicker` map and the bounded `eventBuffer` are
      // omitted: active runs are re-derived on hydration from the
      // server, and the event buffer is for live streaming only (a
      // 1000-event buffer re-stringified on every WS append would
      // dominate the main thread during a busy run). The historical
      // run selection IS persisted so the user can refresh and keep
      // viewing the same older run.
      partialize: (s) => ({
        focusedTicker: s.focusedTicker,
        lastRunIdByTicker: s.lastRunIdByTicker,
        historicalRunIdByTicker: s.historicalRunIdByTicker,
        holdThresholdPct: s.holdThresholdPct,
        historyPollIntervalMs: s.historyPollIntervalMs,
        candleResolution: s.candleResolution,
        watchlistCollapsedGroups: s.watchlistCollapsedGroups,
        customGroupColors: s.customGroupColors,
        groupOrder: s.groupOrder,
        tickerAgentDrawerOpen: s.tickerAgentDrawerOpen,
      }),
    },
  ),
);

export const useUiStore = useUi;
