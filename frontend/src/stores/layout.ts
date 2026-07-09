/** Widget-grid personalization: layouts per module, presets, hidden
 * widgets. localStorage for instant boot; debounced mirror to
 * PUT /api/prefs so layouts survive across machines. Safety chrome
 * (status strip, halt banner) is NOT part of any layout by design. */
import type { Layout } from "react-grid-layout";
import { create } from "zustand";
import { persist } from "zustand/middleware";

export type ModuleId = "home" | "workspace" | "portfolio" | "intel";
export type PresetId = "operator" | "analyst" | "risk";

/** Presets are real (review finding: a preset that changes nothing is
 * fake). Each seeds per-module hidden-widget sets; the operator preset
 * is the full default. */
export const PRESETS: Record<PresetId, Partial<Record<ModuleId, string[]>>> = {
  operator: {},
  // reasoning-first: strip money/market tiles, keep decision context
  analyst: { home: ["prices", "watchlist", "snapshot"] },
  // risk-first: strip discovery widgets, keep alerts/portfolio/decision
  risk: { home: ["watchlist", "diff", "next"] },
};

export const PRESET_DESCRIPTIONS: Record<PresetId, string> = {
  operator: "Everything — the full briefing (default)",
  analyst: "Reasoning-first: hides prices, watchlist, and the portfolio tile",
  risk: "Risk-first: hides watchlist, diff, and calendar to foreground alerts",
};

export interface ModuleLayout {
  layout: Layout[];
  hidden: string[];
}

interface LayoutState {
  preset: PresetId;
  editing: boolean;
  overrides: Partial<Record<ModuleId, ModuleLayout>>;
  setPreset: (preset: PresetId) => void;
  setEditing: (editing: boolean) => void;
  saveLayout: (module: ModuleId, layout: Layout[]) => void;
  hideWidget: (module: ModuleId, id: string) => void;
  showWidget: (module: ModuleId, id: string) => void;
  reset: (module?: ModuleId) => void;
  hydrate: (data: unknown) => void;
  exportForPrefs: () => Record<string, unknown>;
}

export const useLayoutStore = create<LayoutState>()(
  persist(
    (set, get) => ({
      preset: "operator",
      editing: false,
      overrides: {},
      setPreset: (preset) =>
        set({
          preset,
          overrides: Object.fromEntries(
            Object.entries(PRESETS[preset]).map(([module, hidden]) => [
              module,
              { layout: [], hidden: [...hidden] },
            ]),
          ) as LayoutState["overrides"],
        }),
      setEditing: (editing) => set({ editing }),
      saveLayout: (module, layout) =>
        set((state) => ({
          overrides: {
            ...state.overrides,
            [module]: {
              layout,
              hidden: state.overrides[module]?.hidden ?? [],
            },
          },
        })),
      hideWidget: (module, id) =>
        set((state) => ({
          overrides: {
            ...state.overrides,
            [module]: {
              layout: state.overrides[module]?.layout ?? [],
              hidden: [...(state.overrides[module]?.hidden ?? []), id],
            },
          },
        })),
      showWidget: (module, id) =>
        set((state) => ({
          overrides: {
            ...state.overrides,
            [module]: {
              layout: state.overrides[module]?.layout ?? [],
              hidden: (state.overrides[module]?.hidden ?? []).filter(
                (h) => h !== id,
              ),
            },
          },
        })),
      reset: (module) =>
        set((state) => {
          if (!module) return { overrides: {} };
          const overrides = { ...state.overrides };
          delete overrides[module];
          return { overrides };
        }),
      hydrate: (data) => {
        if (data && typeof data === "object" && "preset" in data) {
          const d = data as { preset?: PresetId; overrides?: LayoutState["overrides"] };
          set({
            preset: d.preset ?? "operator",
            overrides: d.overrides ?? {},
          });
        }
      },
      exportForPrefs: () => ({
        preset: get().preset,
        overrides: get().overrides,
      }),
    }),
    { name: "pro-layout", partialize: (s) => ({ preset: s.preset, overrides: s.overrides }) },
  ),
);
