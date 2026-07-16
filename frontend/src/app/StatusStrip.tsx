/** Immovable safety chrome: connection state, loop/risk state, feed
 * health, session, prices. The halt banner renders above everything
 * when trading is halted — it cannot be hidden or moved. */
import { useQueryClient } from "@tanstack/react-query";
import { Bell, Moon, Search, Sun } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api/client";
import { qk } from "@/lib/api/queries";
import { useNotifications, useOverview, useRegime, useStatus } from "@/lib/api/queries";
import { fmtPnl, fmtPrice, TZ_LABEL } from "@/lib/format";
import { useConnectionState } from "@/lib/staleness";
import { cn } from "@/lib/utils";
import { useTick } from "@/stores/ticker";
import { useUiStore } from "@/stores/ui";

function ConnPill() {
  const { state, ageSeconds, lastSuccess } = useConnectionState();
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-bold",
        state === "live" && "bg-bull-muted text-bull",
        state === "stale" && "border border-dashed border-stale text-stale",
        state === "disconnected" && "bg-bear-muted text-bear",
      )}
      data-testid="conn-state"
    >
      {state === "live" && (
        <>
          <span className="live-dot" aria-hidden="true" />
          LIVE
        </>
      )}
      {state === "stale" && `STALE ${ageSeconds}s`}
      {state === "disconnected" && "DISCONNECTED"}
      {state === "live" && lastSuccess > 0 && (
        <span className="font-normal text-fg-subtle max-md:hidden">
          updated{" "}
          {new Date(lastSuccess).toLocaleTimeString()}
          {TZ_LABEL && (
            <span className="max-[1440px]:hidden"> {TZ_LABEL}</span>
          )}
        </span>
      )}
    </span>
  );
}

/** Navy ticker chip; the price flashes bull/bear on each tick (visual
 * only — a prev-value ref, no store changes). */
function PriceTicker({ symbol }: { symbol: string }) {
  const tick = useTick(symbol);
  const overview = useOverview();
  const fallback =
    overview.data?.symbol === symbol ? overview.data.last_close : null;
  const price = tick?.last ?? fallback;
  const prev = useRef<number | null>(null);
  // last tick direction tints the price (mockup: #5ad48e/#ff8a84 — picked
  // for contrast on the navy chip, not the standard bull/bear tokens)
  const [dir, setDir] = useState<"up" | "down" | "">("");
  useEffect(() => {
    if (price == null) return;
    if (prev.current != null && price !== prev.current) {
      setDir(price > prev.current ? "up" : "down");
    }
    prev.current = price;
  }, [price]);
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full bg-navy px-3 py-1 font-mono text-xs text-(--chrome-fg) tabular"
      data-testid={`ticker-${symbol}`}
    >
      <span className="text-(--chrome-fg-muted)">{symbol}</span>{" "}
      <span
        className={cn(
          "font-semibold",
          !tick && "text-(--chrome-fg-muted)",
          dir === "up" && "text-[#5ad48e]",
          dir === "down" && "text-[#ff8a84]",
        )}
      >
        {fmtPrice(price)}
      </span>
      {!tick && <span className="text-[10px] text-stale">EOD</span>}
    </span>
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
      className="rounded-2xl bg-bear px-4 py-2 text-sm font-bold text-on-solid"
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
      className="flex items-center justify-between gap-2 rounded-2xl bg-neutral px-4 py-1.5 text-sm font-bold text-on-solid"
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
      className="rounded-lg bg-bear px-2.5 py-1 text-xs font-bold text-on-solid ring-1 ring-white/60 hover:brightness-110"
      data-testid="emergency-flatten"
    >
      EMERGENCY FLATTEN
    </button>
  );
}

export function StatusStrip() {
  const status = useStatus();
  const overview = useOverview();
  const regime = useRegime();
  const notifications = useNotifications();
  const { theme, symbol, setTheme, setPaletteOpen, setNotificationsOpen } =
    useUiStore();

  const s = status.data;
  const o = overview.data;
  const unread = notifications.data?.unread ?? 0;
  // symbol-aware regime (G3): the chip shows the ACTIVE symbol's regime
  // from the deterministic per-symbol endpoint, never another symbol's
  const activeRegime = regime.data?.symbols?.[symbol]?.regime ?? null;
  const regimeTitle = regime.data
    ? "live regime — " +
      Object.entries(regime.data.symbols)
        .map(([sym, r]) => `${sym}: ${r.regime ?? "—"}`)
        .join(" · ") +
      " (decision cards show the regime at decision time)"
    : undefined;

  return (
    <header className="z-40 rounded-[18px] border border-border bg-surface shadow-(--shadow-1) backdrop-blur-[16px]">
      {/* one row always: on mobile only safety-critical items stay
          (LIVE state, risk, degraded count) — context badges shrink away */}
      {/* user-removed: page title + search field (⌘K still opens the
          palette; the bell menu keeps a mouse path via its shortcut hint) */}
      <div className="flex items-center gap-x-3 gap-y-1 px-4 py-2.5 max-md:gap-x-2">
        <span className="grow" />
        <ConnPill />
        <Badge
          variant="accent"
          className="max-[1250px]:hidden"
          title={regimeTitle}
          data-testid="regime-badge"
        >
          {(activeRegime != null
            ? `${symbol.replace("-USD", "")} ${activeRegime.replaceAll("_", " ")}`
            : (o?.regime ?? "regime —")) +
            " · " +
            (regime.data?.session ?? o?.session
              ? `session ${(regime.data?.session ?? o?.session ?? "").replaceAll("_", " ")}`
              : "session —")}
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
          <Badge
            data-testid="positions-badge"
            className="max-[1550px]:hidden"
            title={s.open_positions
              ?.map((p) => p.unrealized_pnl != null
                ? `${p.symbol} unrealized ${fmtPnl(p.unrealized_pnl)}`
                : p.symbol)
              .join(" · ")}
          >
            {s.open_positions && s.open_positions.length > 0
              ? `pos ${s.open_positions
                  .map((p) =>
                    `${p.symbol} ${p.quantity > 0 ? "+" : ""}${p.quantity.toFixed(2)}`)
                  .join(", ")}`
              : "no positions"}
          </Badge>
        )}
        {(o?.missing_feeds?.length ?? 0) > 0 && (
          <Badge variant="stale" className="max-[1450px]:hidden">{o!.missing_feeds!.length} feeds degraded</Badge>
        )}
        <span className="contents max-[980px]:hidden">
          <PriceTicker symbol="BTC-USD" />
        </span>
        {/* the mockup header carries one ticker (BTC-USD); the XAU chip
            only appears on ultra-wide screens — its price also lives on
            the Home Prices card and the Trade page */}
        <span className="contents max-[1680px]:hidden">
          <PriceTicker symbol="XAUUSD" />
        </span>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Search (Cmd+K)"
          className="min-[981px]:hidden"
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
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-bear px-1 text-[10px] font-bold text-on-solid">
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
