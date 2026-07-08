/** cmdk palette: navigation, trade context, actions, run/global search.
 * Halting trading deliberately requires typing HALT in the settings
 * flow — it is findable here but never one keystroke away. */
import { useQueryClient } from "@tanstack/react-query";
import { Command } from "cmdk";
import { useLocation, useNavigate } from "react-router-dom";

import { Kbd } from "./ui/kbd";
import { patchPrefs, usePrefs, useRuns } from "@/lib/api/queries";
import { fmtDateTime } from "@/lib/format";
import { useUiStore } from "@/stores/ui";
import { useLayoutStore, type PresetId } from "@/stores/layout";

const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d", "1w"];

export function CommandPalette() {
  const navigate = useNavigate();
  const location = useLocation();
  const client = useQueryClient();
  const prefs = usePrefs();
  const {
    paletteOpen,
    setPaletteOpen,
    symbol,
    setSymbol,
    setTimeframe,
    theme,
    setTheme,
    setShortcutsOpen,
  } = useUiStore();
  const setPreset = useLayoutStore((s) => s.setPreset);
  const runs = useRuns();

  const close = () => setPaletteOpen(false);
  const go = (to: string) => {
    navigate(to);
    close();
  };

  return (
    <Command.Dialog
      open={paletteOpen}
      onOpenChange={setPaletteOpen}
      label="Command palette"
      className="fixed left-1/2 top-24 z-50 w-full max-w-lg -translate-x-1/2 overflow-hidden rounded-lg border border-border-strong bg-surface shadow-(--shadow-2)"
    >
      <Command.Input
        placeholder="Search commands, runs, symbols…"
        className="w-full border-b border-border bg-transparent px-4 py-3 text-sm outline-none placeholder:text-fg-subtle"
      />
      <Command.List className="max-h-80 overflow-y-auto p-2 text-sm">
        <Command.Empty className="px-3 py-6 text-center text-fg-subtle">
          Nothing matches.
        </Command.Empty>

        <Command.Group heading="Navigate" className="cmdk-group">
          {[
            ["Home", "/", "g h"],
            ["Trading Workspace", `/trade/${symbol}`, "g t"],
            ["AI Decision Center", "/decisions", "g d"],
            ["Portfolio", "/portfolio", "g p"],
            ["Market Intelligence", "/intel", "g i"],
            ["Settings", "/settings", "g s"],
            ["Monthly report (print/PDF)", "/report", ""],
          ].map(([label, to, keys]) => (
            <Command.Item
              key={to}
              onSelect={() => go(to!)}
              className="flex cursor-pointer items-center justify-between rounded px-3 py-2 aria-selected:bg-surface-2"
            >
              <span>{label}</span>
              {keys && <Kbd>{keys}</Kbd>}
            </Command.Item>
          ))}
        </Command.Group>

        <Command.Group heading="Trade context">
          <Command.Item
            onSelect={() => {
              setSymbol(symbol === "BTC-USD" ? "XAUUSD" : "BTC-USD");
              close();
            }}
            className="flex cursor-pointer items-center justify-between rounded px-3 py-2 aria-selected:bg-surface-2"
          >
            <span>Switch symbol ({symbol === "BTC-USD" ? "→ XAUUSD" : "→ BTC-USD"})</span>
            <Kbd>x</Kbd>
          </Command.Item>
          {TIMEFRAMES.map((tf, i) => (
            <Command.Item
              key={tf}
              onSelect={() => {
                setTimeframe(tf);
                close();
              }}
              className="flex cursor-pointer items-center justify-between rounded px-3 py-2 aria-selected:bg-surface-2"
            >
              <span>Timeframe {tf}</span>
              <Kbd>{i + 1}</Kbd>
            </Command.Item>
          ))}
        </Command.Group>

        <Command.Group heading="Actions">
          <Command.Item
            onSelect={() => {
              setTheme(theme === "dark" ? "light" : "dark");
              close();
            }}
            className="flex cursor-pointer items-center justify-between rounded px-3 py-2 aria-selected:bg-surface-2"
          >
            <span>Toggle theme</span>
            <Kbd>⇧D</Kbd>
          </Command.Item>
          {(["operator", "analyst", "risk"] as PresetId[]).map((preset) => (
            <Command.Item
              key={preset}
              onSelect={() => {
                setPreset(preset);
                close();
              }}
              className="cursor-pointer rounded px-3 py-2 capitalize aria-selected:bg-surface-2"
            >
              Apply layout preset: {preset}
            </Command.Item>
          ))}
          <Command.Item
            onSelect={() => {
              window.open("/api/export/journal.csv", "_blank");
              close();
            }}
            className="cursor-pointer rounded px-3 py-2 aria-selected:bg-surface-2"
          >
            Export trade journal (CSV)
          </Command.Item>
          <Command.Item
            onSelect={() => {
              setShortcutsOpen(true);
              close();
            }}
            className="flex cursor-pointer items-center justify-between rounded px-3 py-2 aria-selected:bg-surface-2"
          >
            <span>Keyboard shortcuts</span>
            <Kbd>?</Kbd>
          </Command.Item>
          <Command.Item
            onSelect={() => go("/settings")}
            className="cursor-pointer rounded px-3 py-2 text-bear aria-selected:bg-surface-2"
          >
            Halt trading… (kill switch — confirm in Settings)
          </Command.Item>
        </Command.Group>

        <Command.Group heading="Views">
          <Command.Item
            onSelect={() => {
              const path = location.pathname + location.search;
              const name = `${location.pathname.replaceAll("/", " ").trim() || "home"} · ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
              const existing = prefs.data?.views ?? [];
              void patchPrefs(client, {
                views: [...existing.filter((v) => v.path !== path),
                        { name, path }].slice(-50),
              });
              close();
            }}
            className="cursor-pointer rounded px-3 py-2 aria-selected:bg-surface-2"
          >
            Save current view
          </Command.Item>
          {(prefs.data?.views ?? []).map((view) => (
            <Command.Item
              key={view.path}
              value={`view ${view.name} ${view.path}`}
              onSelect={() => go(view.path)}
              className="flex cursor-pointer items-center justify-between rounded px-3 py-2 aria-selected:bg-surface-2"
            >
              <span>{view.name}</span>
              <span className="text-xs text-fg-subtle">{view.path}</span>
            </Command.Item>
          ))}
        </Command.Group>

        <Command.Group heading="Runs">
          {(runs.data ?? [])
            .slice(-30)
            .reverse()
            .map((run) => (
              <Command.Item
                key={run.run_id}
                value={`run ${run.run_id} ${run.symbol} ${run.action ?? "rejected"} ${run.started_at}`}
                onSelect={() => go(`/decisions/${run.run_id}`)}
                className="flex cursor-pointer items-center justify-between rounded px-3 py-2 aria-selected:bg-surface-2"
              >
                <span>
                  {run.symbol}{" "}
                  <span className={run.action ? "text-bull" : "text-neutral"}>
                    {run.action ?? `rejected@${run.rejected_at}`}
                  </span>
                </span>
                <span className="text-xs text-fg-subtle">
                  {fmtDateTime(run.started_at)}
                </span>
              </Command.Item>
            ))}
        </Command.Group>
      </Command.List>
    </Command.Dialog>
  );
}
