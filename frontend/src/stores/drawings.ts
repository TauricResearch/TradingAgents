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
        if (!data || typeof data !== "object" || Array.isArray(data)) return;
        // MERGE by id, never overwrite: the server mirror is a debounced
        // snapshot and can be staler than local state (review: a reload
        // 1.5s after drawing wiped the drawing). Union keeps both sides;
        // the next mirror tick pushes the merged set back up.
        const incoming = data as Record<string, Drawing[]>;
        set((state) => {
          const merged: Record<string, Drawing[]> = { ...state.bySymbol };
          for (const [symbol, drawings] of Object.entries(incoming)) {
            if (!Array.isArray(drawings)) continue;
            const existing = merged[symbol] ?? [];
            const seen = new Set(existing.map((d) => d.id));
            merged[symbol] = [
              ...existing,
              ...drawings.filter((d) => d && !seen.has(d.id)),
            ].slice(-MAX_PER_SYMBOL);
          }
          return { bySymbol: merged };
        });
      },
    }),
    { name: "pro-drawings" },
  ),
);
