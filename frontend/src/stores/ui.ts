import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Theme = "dark" | "light";

/** Live progress of an in-flight on-demand pipeline run (SSE `stage`
 * events; cleared by the terminal `run` event). Not persisted. */
export interface GridCell {
  symbol: string;
  timeframe: string;
}

export interface PipelineProgress {
  symbol: string;
  stage: string;
}

interface UiState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  paletteOpen: boolean;
  setPaletteOpen: (open: boolean) => void;
  notificationsOpen: boolean;
  setNotificationsOpen: (open: boolean) => void;
  shortcutsOpen: boolean;
  setShortcutsOpen: (open: boolean) => void;
  symbol: string;
  setSymbol: (symbol: string) => void;
  timeframe: string;
  setTimeframe: (tf: string) => void;
  indicators: string[];
  toggleIndicator: (name: string) => void;
  showVolume: boolean;
  toggleVolume: () => void;
  logScale: boolean;
  toggleLogScale: () => void;
  chartStyle: string;
  setChartStyle: (style: string) => void;
  showProfile: boolean;
  toggleProfile: () => void;
  gridCells: GridCell[];
  setGridCells: (cells: GridCell[]) => void;
  updateGridCell: (index: number, cell: Partial<GridCell>) => void;
  compare: boolean;
  setCompare: (on: boolean) => void;
  lastSeenAt: number; // powers the "since you left" diff panel
  markSeen: () => void;
  runDialogOpen: boolean;
  setRunDialogOpen: (open: boolean) => void;
  pipelineProgress: PipelineProgress | null;
  setPipelineProgress: (progress: PipelineProgress | null) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      theme: "light",
      setTheme: (theme) => {
        document.documentElement.dataset.theme = theme;
        set({ theme });
      },
      paletteOpen: false,
      setPaletteOpen: (paletteOpen) => set({ paletteOpen }),
      notificationsOpen: false,
      setNotificationsOpen: (notificationsOpen) => set({ notificationsOpen }),
      shortcutsOpen: false,
      setShortcutsOpen: (shortcutsOpen) => set({ shortcutsOpen }),
      symbol: "BTC-USD",
      setSymbol: (symbol) => set({ symbol }),
      timeframe: "1h",
      setTimeframe: (timeframe) => set({ timeframe }),
      // mockup default: EMA 10 overlay on ("Indicators (1)")
      indicators: ["EMA_10"],
      toggleIndicator: (name) =>
        set((state) => ({
          indicators: state.indicators.includes(name)
            ? state.indicators.filter((n) => n !== name)
            : [...state.indicators, name],
        })),
      // mockup default: volume pane on
      showVolume: true,
      toggleVolume: () => set((state) => ({ showVolume: !state.showVolume })),
      logScale: false,
      toggleLogScale: () => set((state) => ({ logScale: !state.logScale })),
      chartStyle: "candles",
      setChartStyle: (chartStyle) => set({ chartStyle }),
      // volume profile off by default — opt-in visual weight
      showProfile: false,
      toggleProfile: () => set((state) => ({ showProfile: !state.showProfile })),
      // multi-chart grid (P2.6): extra synced cells under the main chart
      gridCells: [],
      setGridCells: (cells) => set({ gridCells: cells }),
      updateGridCell: (index, cell) =>
        set((state) => ({
          gridCells: state.gridCells.map((c, i) =>
            i === index ? { ...c, ...cell } : c,
          ),
        })),
      compare: false,
      setCompare: (compare) => set({ compare }),
      lastSeenAt: Date.now(),
      markSeen: () => set({ lastSeenAt: Date.now() }),
      runDialogOpen: false,
      setRunDialogOpen: (runDialogOpen) => set({ runDialogOpen }),
      pipelineProgress: null,
      setPipelineProgress: (pipelineProgress) => set({ pipelineProgress }),
    }),
    {
      name: "pro-ui",
      // v1: the Accops reskin made LIGHT the default — migrate persisted
      // sessions to it once; the toggle still persists a choice afterwards
      // v2: mockup chart defaults (volume pane + EMA 10) applied once
      version: 2,
      migrate: (persisted, version) => {
        const state = (persisted ?? {}) as Partial<UiState>;
        if (version < 1) state.theme = "light";
        if (version < 2) {
          state.showVolume = true;
          if (!state.indicators?.length) state.indicators = ["EMA_10"];
        }
        return state as UiState;
      },
      partialize: (s) => ({
        theme: s.theme,
        symbol: s.symbol,
        timeframe: s.timeframe,
        lastSeenAt: s.lastSeenAt,
        indicators: s.indicators,
        showVolume: s.showVolume,
        logScale: s.logScale,
        chartStyle: s.chartStyle,
        showProfile: s.showProfile,
        gridCells: s.gridCells,
      }),
    },
  ),
);

export function usePipelineProgress() {
  return useUiStore((s) => s.pipelineProgress);
}

export function applyPersistedTheme() {
  document.documentElement.dataset.theme = useUiStore.getState().theme;
}
