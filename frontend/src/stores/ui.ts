import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Theme = "dark" | "light";

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
  lastSeenAt: number; // powers the "since you left" diff panel
  markSeen: () => void;
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
      lastSeenAt: Date.now(),
      markSeen: () => set({ lastSeenAt: Date.now() }),
    }),
    {
      name: "pro-ui",
      partialize: (s) => ({
        theme: s.theme,
        symbol: s.symbol,
        timeframe: s.timeframe,
        lastSeenAt: s.lastSeenAt,
      }),
    },
  ),
);

export function applyPersistedTheme() {
  document.documentElement.dataset.theme = useUiStore.getState().theme;
}
