import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { Outlet, useNavigate } from "react-router-dom";

import { AuthGate } from "./AuthGate";
import { ErrorBoundary } from "./ErrorBoundary";
import { Sidebar } from "./Sidebar";
import { ArmingBanner, HaltBanner, StatusStrip } from "./StatusStrip";
import { CommandPalette } from "@/components/CommandPalette";
import { NotificationCenter } from "@/components/NotificationCenter";
import { RunPipelineDialog } from "@/components/RunPipelineDialog";
import { ShortcutCheatsheet } from "@/components/ShortcutCheatsheet";
import { UpdateToast } from "@/components/UpdateToast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { patchPrefs, usePrefs } from "@/lib/api/queries";
import { useBinanceTicker } from "@/lib/binance";
import { installKeyboardHandler } from "@/lib/shortcuts";
import { startEventStream } from "@/lib/sse";
import { recordSuccess } from "@/lib/staleness";
import { useDrawingsStore } from "@/stores/drawings";
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

  const drawingsBySymbol = useDrawingsStore((state) => state.bySymbol);

  // one-time hydrate of layouts + drawings from server prefs, then mirror
  useEffect(() => {
    if (prefs.data && !hydratedRef.current) {
      hydratedRef.current = true;
      layoutStore.hydrate(prefs.data.layouts);
      const layouts = prefs.data.layouts as { drawings?: unknown };
      useDrawingsStore.getState().hydrate(layouts?.drawings);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefs.data]);

  useEffect(() => {
    if (!hydratedRef.current) return;
    const timer = setTimeout(() => {
      // MERGE over the server document (patchPrefs), never a from-scratch
      // object: a bare savePrefs here silently reset every field this
      // mirror didn't carry (views, muted_events, operator_label)
      void patchPrefs(client, {
        theme: ui.theme,
        default_symbol: ui.symbol,
        layouts: {
          ...layoutStore.exportForPrefs(),
          drawings: useDrawingsStore.getState().bySymbol,
        },
        version: 1,
      }).catch(() => undefined); // offline is fine; localStorage still has it
    }, 1500);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layoutStore.overrides, layoutStore.preset, ui.theme, ui.symbol,
      drawingsBySymbol]);

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
        {/* ambient blur blobs behind everything (motion-safe via CSS) */}
        <div className="bg-blob bg-blob--brand" aria-hidden="true" />
        <div className="bg-blob bg-blob--violet" aria-hidden="true" />
        {/* rail owns the full viewport column; banners + top bar + content
            live entirely in the right column (mockup full-height sidebar) */}
        <div className="flex h-screen flex-row gap-3 p-[14px] max-md:p-2">
          <Sidebar />
          <div className="flex min-w-0 grow flex-col gap-3">
            <HaltBanner />
            <ArmingBanner />
            <StatusStrip />
            <main className="min-h-0 min-w-0 grow overflow-y-auto max-md:pb-20">
              <ErrorBoundary label="This page">
                <Outlet />
              </ErrorBoundary>
            </main>
          </div>
        </div>
        <CommandPalette />
        <NotificationCenter />
        <RunPipelineDialog />
        <ShortcutCheatsheet />
        <UpdateToast />
      </TooltipProvider>
    </AuthGate>
  );
}
