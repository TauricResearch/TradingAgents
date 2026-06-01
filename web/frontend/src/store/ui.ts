import { create } from "zustand";
import type { WsEvent } from "../lib/events";

interface UiState {
  focusedTicker: string | null;
  connectedRunId: number | null;
  eventBuffer: WsEvent[];
  setFocusedTicker: (t: string | null) => void;
  setConnectedRunId: (rid: number | null) => void;
  appendEvent: (e: WsEvent) => void;
  clearBuffer: () => void;
}

export const useUi = create<UiState>((set) => ({
  focusedTicker: null,
  connectedRunId: null,
  eventBuffer: [],
  setFocusedTicker: (t) => set({ focusedTicker: t, eventBuffer: [], connectedRunId: null }),
  setConnectedRunId: (rid) => set({ connectedRunId: rid }),
  appendEvent: (e) => set((s) => ({ eventBuffer: [...s.eventBuffer, e].slice(-1000) })),
  clearBuffer: () => set({ eventBuffer: [] }),
}));
