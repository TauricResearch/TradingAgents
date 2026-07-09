/** Settings: theme, layout presets, Binance WS host, and the kill-switch
 * explainer. Halting is displayed but executed operator-side (touch the
 * KILL file / engage()) — the dashboard is read-only over execution by
 * design, and says so instead of pretending. */
import { useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { binanceHost, setBinanceHost } from "@/lib/binance";
import { patchPrefs, usePrefs, useStatus } from "@/lib/api/queries";
import { PRESET_DESCRIPTIONS, useLayoutStore, type PresetId } from "@/stores/layout";
import { useUiStore } from "@/stores/ui";

export default function SettingsPage() {
  const { theme, setTheme } = useUiStore();
  const { preset, setPreset, reset } = useLayoutStore();
  const status = useStatus();
  const prefs = usePrefs();
  const client = useQueryClient();
  const views = prefs.data?.views ?? [];
  const muted = prefs.data?.muted_events ?? [];
  const [host, setHost] = useState(binanceHost());
  const [confirm, setConfirm] = useState("");

  return (
    <div className="max-w-2xl space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Appearance</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center gap-3">
          {(["dark", "light"] as const).map((t) => (
            <Button
              key={t}
              variant={theme === t ? "default" : "outline"}
              size="sm"
              onClick={() => setTheme(t)}
              className="capitalize"
            >
              {t}
            </Button>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Layout presets</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex gap-2">
            {(["operator", "analyst", "risk"] as PresetId[]).map((p) => (
              <Button
                key={p}
                variant={preset === p ? "default" : "outline"}
                size="sm"
                onClick={() => setPreset(p)}
                className="capitalize"
              >
                {p}
              </Button>
            ))}
          </div>
          <p className="text-xs text-fg-subtle">{PRESET_DESCRIPTIONS[preset]}</p>
          <Button variant="ghost" size="sm" onClick={() => reset()}>
            Reset all layouts to preset defaults
          </Button>
          <p className="text-xs text-fg-subtle">
            The status strip and halt banner are not customizable — safety
            chrome stays put.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Data connections</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <label className="block text-sm">
            Binance WebSocket host
            <Input
              className="mt-1 font-mono"
              value={host}
              onChange={(event) => setHost(event.target.value)}
              onBlur={() => setBinanceHost(host)}
            />
          </label>
          <p className="text-xs text-fg-subtle">
            Use wss://stream.binance.us:9443 in US regions. Takes effect on
            next reconnect.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Saved views</CardTitle>
        </CardHeader>
        <CardContent>
          {views.length === 0 ? (
            <p className="text-sm text-fg-subtle">
              None yet — save one from the command palette (⌘K → "Save current
              view").
            </p>
          ) : (
            <ul className="space-y-1" data-testid="saved-views">
              {views.map((view) => (
                <li key={view.path} className="flex items-center gap-2 text-sm">
                  <Link to={view.path} className="text-accent hover:underline">
                    {view.name}
                  </Link>
                  <span className="grow font-mono text-xs text-fg-subtle">
                    {view.path}
                  </span>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-6 w-6"
                    aria-label={`delete view ${view.name}`}
                    onClick={() =>
                      void patchPrefs(client, {
                        views: views.filter((v) => v.path !== view.path),
                      })
                    }
                  >
                    <X size={12} />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Muted notification types</CardTitle>
        </CardHeader>
        <CardContent>
          {muted.length === 0 ? (
            <p className="text-sm text-fg-subtle">
              Nothing muted. Mute a type from any notification in the bell
              panel; muted types are hidden, never deleted.
            </p>
          ) : (
            <ul className="flex flex-wrap gap-2" data-testid="muted-events">
              {muted.map((event) => (
                <li key={event}>
                  <Badge variant="stale" className="gap-1">
                    {event}
                    <button
                      aria-label={`unmute ${event}`}
                      onClick={() =>
                        void patchPrefs(client, {
                          muted_events: muted.filter((m) => m !== event),
                        })
                      }
                    >
                      <X size={11} />
                    </button>
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card className="border-bear/40">
        <CardHeader>
          <CardTitle className="text-bear">Halt trading (kill switch)</CardTitle>
          {status.data?.kill_switch?.engaged && <Badge variant="bear">ENGAGED</Badge>}
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p className="text-fg-muted">
            The kill switch is an operator action, not a dashboard button:
            engaging it requires shell access (<code className="font-mono text-xs">touch
            &lt;data&gt;/KILL</code>) or <code className="font-mono text-xs">
            kill_switch.engage(reason)</code>, and resetting demands an operator
            identity. The dashboard reads that state; it cannot write it. This
            is deliberate — a browser session must never be one click away from
            halting (or un-halting) the loop.
          </p>
          <label className="block">
            Type <span className="font-mono">HALT</span> to reveal the runbook
            command:
            <Input
              className="mt-1 w-40 font-mono"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              aria-label="halt confirmation"
            />
          </label>
          {confirm === "HALT" && (
            <pre className="rounded-md border border-bear/40 bg-bear-muted p-3 font-mono text-xs">
              docker exec pro-dashboard touch /data/KILL
            </pre>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
