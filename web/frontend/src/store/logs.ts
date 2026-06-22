import { create } from "zustand";

export interface LogEntry {
  id: string;
  ts: string;
  level: "DEBUG" | "INFO" | "WARNING" | "ERROR";
  logger: string;
  message: string;
  source: "server" | "client";
}

interface LogState {
  entries: LogEntry[];
  append: (entry: LogEntry) => void;
  clear: () => void;
}

const MAX_ENTRIES = 1000;

export const useLogStore = create<LogState>()((set) => ({
  entries: [],
  append: (entry) =>
    set((s) => ({ entries: [...s.entries, entry].slice(-MAX_ENTRIES) })),
  clear: () => set({ entries: [] }),
}));