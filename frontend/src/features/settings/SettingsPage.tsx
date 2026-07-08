/** Settings: theme, layout presets, Binance WS host, and the kill-switch
 * explainer. Halting is displayed but executed operator-side (touch the
 * KILL file / engage()) — the dashboard is read-only over execution by
 * design, and says so instead of pretending. */
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { binanceHost, setBinanceHost } from "@/lib/binance";
import { useStatus } from "@/lib/api/queries";
import { useLayoutStore, type PresetId } from "@/stores/layout";
import { useUiStore } from "@/stores/ui";

export default function SettingsPage() {
  const { theme, setTheme } = useUiStore();
  const { preset, setPreset, reset } = useLayoutStore();
  const status = useStatus();
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
