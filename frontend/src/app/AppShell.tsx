import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { Outlet, useNavigate } from "react-router-dom";

import { AuthGate } from "./AuthGate";
import { ErrorBoundary } from "./ErrorBoundary";
import { Sidebar } from "./Sidebar";
import { HaltBanner, StatusStrip } from "./StatusStrip";
import { CommandPalette } from "@/components/CommandPalette";
import { NotificationCenter } from "@/components/NotificationCenter";
import { ShortcutCheatsheet } from "@/components/ShortcutCheatsheet";
import { TooltipProvider } from "@/components/ui/tooltip";
import { savePrefs, usePrefs } from "@/lib/api/queries";
import { useBinanceTicker } from "@/lib/binance";
import { installKeyboardHandler } from "@/lib/shortcuts";
import { startEventStream } from "@/lib/sse";
import { recordSuccess } from "@/lib/staleness";
import { useLayoutStore } from "@/stores/layout";
import { useUiStore } from "@/stores/ui";

const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d", "1w"];

function Wiring() {
  const client = useQueryClient();
  const navigate = useNavigate();
  const ui = useUiStore();
  const layoutStore = useLayoutStore();
  const prefs = usePrefs();
  const hydratedRef = useRef(false);

  // any successful query bumps global freshness
  useEffect(() => {
    const cache = client.getQueryCache();
    return cache.subscribe((event) => {
      if (event.type === "updated" && event.action.type === "success") {
        recordSuccess();
      }
    });
  }, [client]);

  // SSE transport
  useEffect(() => startEventStream(client), [client]);

  // live BTC ticks
  useBinanceTicker(true);

  // one-time hydrate of layouts from server prefs, then debounced mirror
  useEffect(() => {
    if (prefs.data && !hydratedRef.current) {
      hydratedRef.current = true;
      layoutStore.hydrate(prefs.data.layouts);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefs.data]);

  useEffect(() => {
    if (!hydratedRef.current) return;
    const timer = setTimeout(() => {
      void savePrefs(client, {
        theme: ui.theme,
        default_symbol: ui.symbol,
        layouts: layoutStore.exportForPrefs(),
        version: 1,
      }).catch(() => undefined); // offline is fine; localStorage still has it
    }, 1500);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layoutStore.overrides, layoutStore.preset, ui.theme, ui.symbol]);

  // keyboard chords
  useEffect(
    () =>
      installKeyboardHandler({
        go: (key) => {
          const map: Record<string, string> = {
            h: "/",
            t: `/trade/${useUiStore.getState().symbol}`,
            d: "/decisions",
            p: "/portfolio",
            i: "/intel",
            s: "/settings",
          };
          if (map[key]) navigate(map[key]);
        },
        openPalette: () => ui.setPaletteOpen(true),
        openSearch: () => ui.setPaletteOpen(true),
        openCheatsheet: () => ui.setShortcutsOpen(true),
        toggleSymbol: () =>
          ui.setSymbol(useUiStore.getState().symbol === "BTC-USD" ? "XAUUSD" : "BTC-USD"),
        setTimeframe: (index) => {
          const tf = TIMEFRAMES[index];
          if (tf) ui.setTimeframe(tf);
        },
        toggleTheme: () =>
          ui.setTheme(useUiStore.getState().theme === "dark" ? "light" : "dark"),
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [navigate],
  );

  return null;
}

export function AppShell() {
  return (
    <AuthGate>
      <TooltipProvider>
        <Wiring />
        <div className="flex h-screen flex-col">
          <HaltBanner />
          <StatusStrip />
          <div className="flex min-h-0 grow">
            <Sidebar />
            <main className="min-w-0 grow overflow-y-auto p-4 max-md:pb-20">
              <ErrorBoundary label="This page">
                <Outlet />
              </ErrorBoundary>
            </main>
          </div>
        </div>
        <CommandPalette />
        <NotificationCenter />
        <ShortcutCheatsheet />
      </TooltipProvider>
    </AuthGate>
  );
}
