/** Immovable safety chrome: connection state, loop/risk state, feed
 * health, session, prices. The halt banner renders above everything
 * when trading is halted — it cannot be hidden or moved. */
import { useQueryClient } from "@tanstack/react-query";
import { Bell, Moon, Search, Sun } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api/client";
import { qk } from "@/lib/api/queries";
import { useNotifications, useOverview, useStatus } from "@/lib/api/queries";
import { fmtPrice, fmtTime } from "@/lib/format";
import { useConnectionState } from "@/lib/staleness";
import { cn } from "@/lib/utils";
import { useTick } from "@/stores/ticker";
import { useUiStore } from "@/stores/ui";

function ConnPill() {
  const { state, ageSeconds, lastSuccess } = useConnectionState();
  return (
    <span
      className={cn(
        "text-xs font-bold",
        state === "live" && "text-bull",
        state === "stale" && "text-stale",
        state === "disconnected" && "text-bear",
      )}
      data-testid="conn-state"
    >
      {state === "live" && "LIVE"}
      {state === "stale" && `STALE ${ageSeconds}s`}
      {state === "disconnected" && "DISCONNECTED"}
      {state === "live" && lastSuccess > 0 && (
        <span className="ml-2 font-normal text-fg-subtle max-md:hidden">
          updated {fmtTime(new Date(lastSuccess).toISOString())}
        </span>
      )}
    </span>
  );
}

function PriceTicker({ symbol }: { symbol: string }) {
  const tick = useTick(symbol);
  const overview = useOverview();
  const fallback =
    overview.data?.symbol === symbol ? overview.data.last_close : null;
  const price = tick?.last ?? fallback;
  return (
    <Badge className="font-mono" data-testid={`ticker-${symbol}`}>
      {symbol}{" "}
      <span className={tick ? "text-fg" : "text-fg-muted"}>{fmtPrice(price)}</span>
      {!tick && <span className="text-[10px] text-stale">EOD</span>}
    </Badge>
  );
}

export function HaltBanner() {
  const status = useStatus();
  const s = status.data;
  if (!s?.trading_halted) return null;
  const reason = s.kill_switch?.engaged
    ? `kill switch: ${s.kill_switch.reason}`
    : `circuit breaker: ${s.circuit_breaker?.reason ?? ""}`;
  return (
    <div
      role="alert"
      className="bg-bear px-4 py-2 text-sm font-bold text-[#0d1117]"
      data-testid="halt-banner"
    >
      ⛔ TRADING HALTED — {reason}
    </div>
  );
}

/** Live-armed banner: a sibling of HaltBanner, immovable, shown whenever
 * any pair is armed at a live tier. Real capital is exposed — say so. */
export function ArmingBanner() {
  const status = useStatus();
  const arming = status.data?.arming;
  if (!arming) return null;
  const armed = Object.values(arming).filter((a) =>
    ["canary", "live"].includes(a.tier),
  );
  if (armed.length === 0) return null;
  return (
    <div
      role="alert"
      className="flex items-center justify-between gap-2 bg-[#8a6d00] px-4 py-1.5 text-sm font-bold text-[#0d1117]"
      data-testid="arming-banner"
    >
      <span>
        🔴 LIVE — ARMED:{" "}
        {armed.map((a) => `${a.pair} (${a.tier})`).join(", ")}
      </span>
      <EmergencyFlattenButton />
    </div>
  );
}

/** The ONE sanctioned dashboard→execution write. Auth (session cookie)
 * plus a typed confirmation; on success the kill switch engages and every
 * pair disarms. Documented in DASHBOARD.md as the deliberate exception to
 * read-only-over-execution. */
function EmergencyFlattenButton() {
  const client = useQueryClient();
  const flatten = async () => {
    const typed = window.prompt(
      "EMERGENCY FLATTEN cancels all orders and closes all positions at " +
        "market, then disarms. Type FLATTEN to confirm.",
    );
    if (typed !== "FLATTEN") return;
    try {
      await apiFetch("/api/flatten", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: "FLATTEN" }),
      });
    } finally {
      void client.invalidateQueries({ queryKey: qk.status });
    }
  };
  return (
    <button
      onClick={() => void flatten()}
      className="rounded border border-[#0d1117] bg-bear px-2 py-0.5 text-xs font-bold text-[#0d1117] hover:brightness-110"
      data-testid="emergency-flatten"
    >
      EMERGENCY FLATTEN
    </button>
  );
}

export function StatusStrip() {
  const status = useStatus();
  const overview = useOverview();
  const notifications = useNotifications();
  const { theme, setTheme, setPaletteOpen, setNotificationsOpen } = useUiStore();

  const s = status.data;
  const o = overview.data;
  const unread = notifications.data?.unread ?? 0;

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-bg/95 backdrop-blur">
      {/* one row always: on mobile only safety-critical items stay
          (LIVE state, risk, degraded count) — context badges are md+ */}
      <div className="flex items-center gap-x-3 gap-y-1 px-4 py-2 max-md:gap-x-2 md:flex-wrap">
        <span className="text-sm font-bold max-md:hidden">TradingAgents Pro</span>
        <span className="whitespace-nowrap text-sm font-bold md:hidden">TA Pro</span>
        <ConnPill />
        <Badge variant="accent" className="max-lg:hidden">
          {o?.regime ?? "regime —"}
        </Badge>
        <Badge className="max-lg:hidden">
          {o?.session ? `session ${o.session}` : "session —"}
        </Badge>
        {s?.attached ? (
          <Badge
            variant={s.trading_halted ? "bear" : "bull"}
            data-testid="risk-badge"
          >
            {s.trading_halted
              ? s.kill_switch?.engaged
                ? "KILL SWITCH"
                : "BREAKER TRIPPED"
              : "risk OK"}
            {s.equity != null && ` · $${fmtPrice(s.equity, 0)}`}
          </Badge>
        ) : (
          <Badge variant="locked" data-testid="risk-badge">
            monitor only
          </Badge>
        )}
        {s?.attached && (
          <Badge data-testid="positions-badge" className="max-md:hidden">
            {s.open_positions && s.open_positions.length > 0
              ? `pos ${s.open_positions
                  .map((p) => `${p.symbol} ${p.quantity > 0 ? "+" : ""}${p.quantity.toFixed(2)}`)
                  .join(", ")}`
              : "no positions"}
          </Badge>
        )}
        {(o?.missing_feeds?.length ?? 0) > 0 && (
          <Badge variant="stale">{o!.missing_feeds!.length} feeds degraded</Badge>
        )}
        <span className="grow" />
        <span className="contents max-md:hidden">
          <PriceTicker symbol="BTC-USD" />
          <PriceTicker symbol="XAUUSD" />
        </span>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Search and commands (Cmd+K)"
          onClick={() => setPaletteOpen(true)}
        >
          <Search size={15} />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Notifications${unread ? ` (${unread} unread)` : ""}`}
          className="relative"
          onClick={() => setNotificationsOpen(true)}
        >
          <Bell size={15} />
          {unread > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-bear px-1 text-[10px] font-bold text-white">
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Toggle theme"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        >
          {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
        </Button>
      </div>
    </header>
  );
}
