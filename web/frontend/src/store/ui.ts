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
  lastRunIdByTicker: Record<string, number | null>;
  // Run id currently being WS-streamed per ticker. Cleared on terminal
  // events (run_finished / run_failed). Drives `useRunStream` so the
  // hook only opens a WS for the focused ticker while it's still live.
  activeRunIdByTicker: Record<string, number | null>;
  // Global event buffer, bounded to the last 1000 events. Events are
  // already tagged with `run_id` by the server, so display components
  // filter by the focused ticker's run id.
  eventBuffer: WsEvent[];

  setFocusedTicker: (t: string | null) => void;
  setLastRunIdForTicker: (ticker: string, runId: number | null) => void;
  setActiveRunIdForTicker: (ticker: string, runId: number | null) => void;
  clearActiveRunForTicker: (ticker: string) => void;
  appendEvent: (e: WsEvent) => void;
  restoreEvents: (runId: number, events: WsEvent[]) => void;
  clearLastRunIdForTicker: (ticker: string) => void;
  clearBuffer: () => void;
}

export const useUi = create<UiState>()(
  persist(
    (set) => ({
      focusedTicker: null,
      lastRunIdByTicker: {},
      activeRunIdByTicker: {},
      eventBuffer: [],
      setFocusedTicker: (t) => set({ focusedTicker: t }),
      setLastRunIdForTicker: (ticker, runId) =>
        set((s) => ({ lastRunIdByTicker: { ...s.lastRunIdByTicker, [ticker]: runId } })),
      setActiveRunIdForTicker: (ticker, runId) =>
        set((s) => ({ activeRunIdByTicker: { ...s.activeRunIdByTicker, [ticker]: runId } })),
      clearActiveRunForTicker: (ticker) =>
        set((s) => ({ activeRunIdByTicker: { ...s.activeRunIdByTicker, [ticker]: null } })),
      appendEvent: (e) => set((s) => ({ eventBuffer: [...s.eventBuffer, e].slice(-1000) })),
      restoreEvents: (runId, events) => set((s) => {
        const others = s.eventBuffer.filter((e) => e.run_id !== runId);
        const restored = events.map((e) => ({ ...e, run_id: runId }));
        return { eventBuffer: [...others, ...restored].slice(-1000) };
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
      // dominate the main thread during a busy run).
      partialize: (s) => ({
        focusedTicker: s.focusedTicker,
        lastRunIdByTicker: s.lastRunIdByTicker,
      }),
    },
  ),
);
