import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Theme = "dark" | "light";

/** Live progress of an in-flight on-demand pipeline run (SSE `stage`
 * events; cleared by the terminal `run` event). Not persisted. */
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
      theme: "dark",
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
      indicators: [],
      toggleIndicator: (name) =>
        set((state) => ({
          indicators: state.indicators.includes(name)
            ? state.indicators.filter((n) => n !== name)
            : [...state.indicators, name],
        })),
      showVolume: false,
      toggleVolume: () => set((state) => ({ showVolume: !state.showVolume })),
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
      partialize: (s) => ({
        theme: s.theme,
        symbol: s.symbol,
        timeframe: s.timeframe,
        lastSeenAt: s.lastSeenAt,
        indicators: s.indicators,
        showVolume: s.showVolume,
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
