import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { WsEvent } from "../lib/events";

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
  // Global event buffer, bounded to the last 1000 events. Events are
  // already tagged with `run_id` by the server, so display components
  // filter by the focused ticker's run id.
  eventBuffer: WsEvent[];

  setFocusedTicker: (t: string | null) => void;
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
}

export const useUi = create<UiState>()(
  persist(
    (set) => ({
      focusedTicker: null,
      lastRunIdByTicker: {},
      historicalRunIdByTicker: {},
      activeRunIdByTicker: {},
      eventBuffer: [],
      setFocusedTicker: (t) => set({ focusedTicker: t }),
      setLastRunIdForTicker: (ticker, runId) =>
        set((s) => ({ lastRunIdByTicker: { ...s.lastRunIdByTicker, [ticker]: runId } })),
      setActiveRunIdForTicker: (ticker, runId) =>
        set((s) => ({ activeRunIdByTicker: { ...s.activeRunIdByTicker, [ticker]: runId } })),
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
      }),
    },
  ),
);
