/** Per-symbol chart annotations. localStorage for instant boot; the
 * AppShell prefs mirror ships them into UserPrefs.layouts (client-owned
 * blob) so drawings follow the operator across machines. Per-symbol
 * undo/redo (PC.2) keeps a bounded history of each symbol's set. */
import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { Drawing } from "@/components/charts/drawings/types";

const MAX_PER_SYMBOL = 100;
const MAX_HISTORY = 50;

interface DrawingsState {
  bySymbol: Record<string, Drawing[]>;
  past: Record<string, Drawing[][]>;
  future: Record<string, Drawing[][]>;
  add: (symbol: string, drawing: Drawing) => void;
  remove: (symbol: string, id: string) => void;
  toggleHidden: (symbol: string, id: string) => void;
  clear: (symbol: string) => void;
  undo: (symbol: string) => void;
  redo: (symbol: string) => void;
  canUndo: (symbol: string) => boolean;
  canRedo: (symbol: string) => boolean;
  hydrate: (data: unknown) => void;
}

export const useDrawingsStore = create<DrawingsState>()(
  persist(
    (set, get) => {
      /** Apply a transform to one symbol's drawings, recording the prior
       * state on the undo stack and clearing the redo stack. */
      const mutate = (
        symbol: string,
        fn: (prev: Drawing[]) => Drawing[],
      ) =>
        set((state) => {
          const prev = state.bySymbol[symbol] ?? [];
          const next = fn(prev).slice(-MAX_PER_SYMBOL);
          return {
            bySymbol: { ...state.bySymbol, [symbol]: next },
            past: {
              ...state.past,
              [symbol]: [...(state.past[symbol] ?? []), prev].slice(
                -MAX_HISTORY,
              ),
            },
            future: { ...state.future, [symbol]: [] },
          };
        });

      return {
        bySymbol: {},
        past: {},
        future: {},
        add: (symbol, drawing) =>
          mutate(symbol, (prev) => [...prev, drawing]),
        remove: (symbol, id) =>
          mutate(symbol, (prev) => prev.filter((d) => d.id !== id)),
        toggleHidden: (symbol, id) =>
          mutate(symbol, (prev) =>
            prev.map((d) =>
              d.id === id ? { ...d, hidden: !d.hidden } : d,
            ),
          ),
        clear: (symbol) => mutate(symbol, () => []),
        undo: (symbol) =>
          set((state) => {
            const stack = state.past[symbol] ?? [];
            if (stack.length === 0) return state;
            const prev = stack[stack.length - 1]!;
            const current = state.bySymbol[symbol] ?? [];
            return {
              bySymbol: { ...state.bySymbol, [symbol]: prev },
              past: { ...state.past, [symbol]: stack.slice(0, -1) },
              future: {
                ...state.future,
                [symbol]: [current, ...(state.future[symbol] ?? [])].slice(
                  0,
                  MAX_HISTORY,
                ),
              },
            };
          }),
        redo: (symbol) =>
          set((state) => {
            const stack = state.future[symbol] ?? [];
            if (stack.length === 0) return state;
            const next = stack[0]!;
            const current = state.bySymbol[symbol] ?? [];
            return {
              bySymbol: { ...state.bySymbol, [symbol]: next },
              past: {
                ...state.past,
                [symbol]: [...(state.past[symbol] ?? []), current].slice(
                  -MAX_HISTORY,
                ),
              },
              future: { ...state.future, [symbol]: stack.slice(1) },
            };
          }),
        canUndo: (symbol) => (get().past[symbol]?.length ?? 0) > 0,
        canRedo: (symbol) => (get().future[symbol]?.length ?? 0) > 0,
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
      };
    },
    {
      name: "pro-drawings",
      // history is session-scoped; only the drawings themselves persist
      partialize: (s) => ({ bySymbol: s.bySymbol }),
    },
  ),
);