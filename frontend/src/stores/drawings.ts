/** Per-symbol chart annotations. localStorage for instant boot; the
 * AppShell prefs mirror ships them into UserPrefs.layouts (client-owned
 * blob) so drawings follow the operator across machines. */
import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { Drawing } from "@/components/charts/drawings/types";

const MAX_PER_SYMBOL = 100;

interface DrawingsState {
  bySymbol: Record<string, Drawing[]>;
  add: (symbol: string, drawing: Drawing) => void;
  remove: (symbol: string, id: string) => void;
  clear: (symbol: string) => void;
  hydrate: (data: unknown) => void;
}

export const useDrawingsStore = create<DrawingsState>()(
  persist(
    (set) => ({
      bySymbol: {},
      add: (symbol, drawing) =>
        set((state) => ({
          bySymbol: {
            ...state.bySymbol,
            [symbol]: [...(state.bySymbol[symbol] ?? []), drawing].slice(
              -MAX_PER_SYMBOL,
            ),
          },
        })),
      remove: (symbol, id) =>
        set((state) => ({
          bySymbol: {
            ...state.bySymbol,
            [symbol]: (state.bySymbol[symbol] ?? []).filter((d) => d.id !== id),
          },
        })),
      clear: (symbol) =>
        set((state) => ({
          bySymbol: { ...state.bySymbol, [symbol]: [] },
        })),
      hydrate: (data) => {
        if (data && typeof data === "object" && !Array.isArray(data)) {
          set({ bySymbol: data as Record<string, Drawing[]> });
        }
      },
    }),
    { name: "pro-drawings" },
  ),
);
