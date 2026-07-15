/** Home: the 5-second briefing. Above the fold, in priority order —
 * safety (strip above), the AI's current stance, P&L, prices, alerts,
 * what changed, what's next. No charts here: Workspace owns them. */
import { Eye, EyeOff, Pencil, PencilOff } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { AlertFeedList } from "@/components/AlertFeedList";
import { DecisionCard } from "@/components/DecisionCard";
import { EmptyState } from "@/components/EmptyState";
import { Sparkline } from "@/components/Sparkline";
import { Button } from "@/components/ui/button";
import { SkeletonCard } from "@/components/ui/skeleton";
import { WatchlistPanel } from "@/components/WatchlistPanel";
import { WidgetGrid, type WidgetDef } from "@/components/WidgetGrid";
import {
  useAlerts,
  useBacktest,
  useBars,
  useCalendar,
  useJournal,
  useOverview,
  useRecommendation,
  useRuns,
  useStatus,
} from "@/lib/api/queries";
import { fmtPnl, fmtPrice, fmtDateTime, fmtPct } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useTick } from "@/stores/ticker";
import { useLayoutStore } from "@/stores/layout";
import { useUiStore } from "@/stores/ui";

const BOARD_SYMBOLS = ["XAUUSD", "BTC-USD"] as const;

/** Decision board (G1): one current stance PER SYMBOL. The hero leads
 * with the ACTIVE symbol (the one the header/ticker emphasizes), so the
 * hero's symbol + regime agree with the chrome; the other symbol keeps a
 * compact card — a rejected run for one symbol can't hide the other's. */
function DecisionHero() {
  const activeSymbol = useUiStore((s) => s.symbol);
  const gold = useRecommendation(BOARD_SYMBOLS[0]);
  const btc = useRecommendation(BOARD_SYMBOLS[1]);
  if (gold.isPending || btc.isPending) return <SkeletonCard lines={5} />;
  if (gold.isError && btc.isError)
    return (
      <EmptyState kind="error" title="Decisions unavailable"
                  detail={String(gold.error)} />
    );
  const entries = BOARD_SYMBOLS.map((sym, i) => {
    const query = i === 0 ? gold : btc;
    const rec = query.data ?? null;
    const meta = rec as
      | { run_id?: string; run_started_at?: string; status?: string }
      | null;
    const tf = (rec as { timeframe?: string } | null)?.timeframe;
    // a run exists (traded OR rejected — both are decisions); "no
    // recommendation" means the symbol has never run
    const hasDecision = meta != null && meta.status !== "no recommendation";
    return { sym, rec, runId: meta?.run_id ?? null,
             at: meta?.run_started_at ?? "", tf, hasDecision };
  });
  // hero = the active symbol (BTC-USD by default) so the hero's symbol +
  // regime agree with the chrome — but a symbol WITH a decision always
  // beats one without, so we never lead with an empty hero
  entries.sort((a, b) => {
    if (a.hasDecision !== b.hasDecision) return a.hasDecision ? -1 : 1;
    if (a.sym === activeSymbol) return -1;
    if (b.sym === activeSymbol) return 1;
    return 0;
  });
  const [lead, second] = entries as [typeof entries[0], typeof entries[0]];
  return (
    <div className="space-y-3" data-testid="decision-board">
      <DecisionCard
        rec={lead.rec}
        hero
        kicker={`AI Decision — ${lead.sym}${lead.tf ? ` · ${lead.tf.toUpperCase()}` : ""}`}
        runId={lead.runId}
      />
      <div className="border-t border-border pt-3">
        <div className="mb-1.5 text-[10.5px] font-bold uppercase tracking-[0.09em] text-fg-subtle">
          {second.sym}
        </div>
        <DecisionCard rec={second.rec} compact runId={second.runId} />
      </div>
    </div>
  );
}

function PortfolioSnapshot() {
  const status = useStatus();
  const journal = useJournal();
  const backtest = useBacktest();
  const [hidden, setHidden] = useState(false);
  if (journal.isPending) return <SkeletonCard lines={4} />;
  const j = journal.data;
  const mask = (value: string) => (hidden ? "••••••" : value);
  return (
    // brand-gradient panel (mockup): literal blues, not var(--brand) — the
    // dark theme's brand (#7d9ef2) is too light for this card's white text
    <div className="-m-1 flex h-full flex-col gap-3 rounded-[16px] bg-[linear-gradient(135deg,#2456c5,#1a3f96)] p-4 text-white">
      <div>
        <div className="flex items-center justify-between">
          <div className="text-[10.5px] font-bold uppercase tracking-[0.09em] text-white/70">
            Portfolio equity
          </div>
          <button
            onClick={() => setHidden(!hidden)}
            aria-label={hidden ? "Show balance" : "Hide balance"}
            aria-pressed={hidden}
            className="text-white/60 hover:text-white"
          >
            {hidden ? <Eye size={14} /> : <EyeOff size={14} />}
          </button>
        </div>
        <div className="mt-1.5 font-mono text-[34px] font-bold leading-tight tracking-[-0.02em] tabular">
          {status.data?.equity != null
            ? mask(`$${fmtPrice(status.data.equity, 0)}`)
            : "—"}
        </div>
        {status.data?.attached === false && (
          <div className="text-[11px] text-white/70">
            monitor mode — no execution attached
          </div>
        )}
      </div>
      <div className="mt-2.5 flex flex-wrap items-center gap-x-[18px] gap-y-1 text-[13px]">
        <span>
          P&L{" "}
          <span
            className={cn(
              "font-mono font-bold tabular",
              (j?.total_pnl ?? 0) >= 0 ? "text-[#8fe3b4]" : "text-[#ff8a84]",
            )}
          >
            {mask(fmtPnl(j?.total_pnl))}
          </span>
          {j?.n_trades != null && (
            <span className="opacity-70"> (n={j.n_trades})</span>
          )}
        </span>
        <span>
          {j?.win_rate != null ? (
            <>
              win rate{" "}
              <span className="font-mono font-bold tabular">
                {fmtPct(j.win_rate, 0)}
              </span>
            </>
          ) : (
            "no closed trades"
          )}
        </span>
      </div>
      <div className="flex flex-1 items-center justify-between rounded-xl bg-white/10 px-3 py-2">
        <span className="text-[10.5px] font-bold uppercase tracking-[0.09em] text-white/70">
          Backtest equity
        </span>
        {backtest.data?.equity_curve && backtest.data.equity_curve.length > 1 ? (
          <Sparkline values={backtest.data.equity_curve} width={160} height={32} />
        ) : (
          <span className="text-xs text-white/70">no backtest yet</span>
        )}
      </div>
      <Link
        to="/portfolio"
        className="inline-flex items-center rounded-xl border border-white/40 px-3 py-1.5 text-sm font-semibold text-white hover:bg-white/10"
      >
        Open portfolio →
      </Link>
    </div>
  );
}

function PriceSpark({ symbol }: { symbol: string }) {
  const bars = useBars(symbol, "1h", 40);
  const closes = (bars.data ?? []).map((bar) => bar.close);
  if (closes.length < 2) return null;
  return <Sparkline values={closes} width={150} height={30} />;
}

function PriceRibbon() {
  const btc = useTick("BTC-USD");
  const gold = useTick("XAUUSD");
  const overview = useOverview();
  const rows = [
    { symbol: "BTC-USD", tick: btc, live: true },
    { symbol: "XAUUSD", tick: gold, live: false },
  ];
  return (
    <div className="grid grid-cols-2 gap-2">
      {rows.map((row) => {
        const fallback =
          overview.data?.symbol === row.symbol ? overview.data.last_close : null;
        const price = row.tick?.last ?? fallback;
        return (
          <Link
            key={row.symbol}
            to={`/trade/${row.symbol}`}
            className="rounded-[14px] bg-surface-2 px-3.5 py-2.5 transition-colors hover:bg-surface-solid hover:shadow-sm"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold">{row.symbol}</span>
              <span
                className={
                  row.tick
                    ? "rounded-full bg-bull-muted px-2 py-0.5 text-[10px] font-bold text-bull"
                    : "rounded-full border border-dashed border-stale px-2 py-0.5 text-[10px] font-bold text-stale"
                }
              >
                {row.tick ? "LIVE" : "EOD"}
              </span>
            </div>
            <div className="font-mono text-[17.5px] tabular">{fmtPrice(price)}</div>
            <div className="text-bull">
              <PriceSpark symbol={row.symbol} />
            </div>
            <div className="text-[11px] text-fg-subtle">
              {row.tick
                ? `live · ${row.tick.source}`
                : price != null
                  ? "EOD — delayed daily data"
                  : "waiting for first tick"}
            </div>
          </Link>
        );
      })}
    </div>
  );
}

function SinceYouLeft() {
  const { lastSeenAt, markSeen } = useUiStore();
  const runs = useRuns();
  const journal = useJournal();
  const alerts = useAlerts();
  const since = new Date(lastSeenAt);

  const newRuns = (runs.data ?? []).filter((r) => new Date(r.started_at) > since);
  const closed = (journal.data?.entries ?? []).filter(
    (e) => new Date(e.closed_at) > since,
  );
  const newAlerts = (alerts.data?.alerts ?? []).filter(
    (a) => new Date(a.time) > since,
  );

  if (newRuns.length + closed.length + newAlerts.length === 0) {
    return (
      <EmptyState
        kind="empty"
        title="Nothing changed since you were last here"
        detail={`watching since ${fmtDateTime(since.toISOString())}`}
        action={
          <Button size="sm" variant="ghost" onClick={markSeen}>
            Reset marker
          </Button>
        }
      />
    );
  }
  return (
    <div className="space-y-1.5 text-sm">
      {newRuns.length > 0 && (
        <p>
          <span className="font-semibold">{newRuns.length}</span> new run(s) —
          latest:{" "}
          <Link
            to={`/decisions/${newRuns[newRuns.length - 1]!.run_id}`}
            className="text-accent hover:underline"
          >
            {newRuns[newRuns.length - 1]!.action ?? "rejected"}
          </Link>
        </p>
      )}
      {closed.length > 0 && (
        <p>
          <span className="font-semibold">{closed.length}</span> trade(s) closed,
          net{" "}
          <span
            className={
              closed.reduce((s, e) => s + e.pnl, 0) >= 0 ? "text-bull" : "text-bear"
            }
          >
            {fmtPnl(closed.reduce((s, e) => s + e.pnl, 0))}
          </span>
        </p>
      )}
      {newAlerts.length > 0 && (
        <p>
          <span className="font-semibold">{newAlerts.length}</span> alert(s),{" "}
          {newAlerts.filter((a) => a.severity === "critical").length} critical
        </p>
      )}
      <Button size="sm" variant="ghost" onClick={markSeen}>
        Mark seen
      </Button>
    </div>
  );
}

function WhatNext() {
  const calendar = useCalendar();
  const all = calendar.data?.releases ?? [];
  // market-moving releases first; fall back to everything if none flagged
  const majors = all.filter((r) => r.major);
  const releases = (majors.length > 0 ? majors : all).slice(0, 5);
  if (calendar.isPending) return <SkeletonCard lines={3} />;
  if (releases.length === 0)
    return (
      <EmptyState
        kind="empty"
        title="No macro releases in window"
        detail={
          calendar.data?.missing_feeds.length
            ? `calendar degraded: ${calendar.data.missing_feeds[0]}`
            : "next 30 days are clear"
        }
      />
    );
  return (
    <ul className="space-y-1 text-sm">
      {releases.map((release, i) => (
        <li key={i} className="flex justify-between">
          <span className="text-fg-muted">{release.release}</span>
          <span className="font-mono text-xs tabular">{release.date}</span>
        </li>
      ))}
    </ul>
  );
}

function AlertsWidget() {
  const alerts = useAlerts();
  if (alerts.isPending) return <SkeletonCard lines={3} />;
  return <AlertFeedList alerts={alerts.data?.alerts ?? []} limit={5} />;
}

const WIDGETS: WidgetDef[] = [
  // right column is non-overlapping so RGL keeps the mockup order:
  // Portfolio Equity → Prices → Since you left → What's next
  { id: "decision", title: "Decision", chromeless: true, render: () => <DecisionHero />, layout: { x: 0, y: 0, w: 7, h: 13, minW: 4, minH: 8 } },
  { id: "snapshot", title: "Portfolio snapshot", chromeless: true, render: () => <PortfolioSnapshot />, layout: { x: 7, y: 0, w: 5, h: 7, minW: 3, minH: 6 } },
  { id: "prices", title: "Prices", render: () => <PriceRibbon />, layout: { x: 7, y: 7, w: 5, h: 4, minW: 3, minH: 4 } },
  { id: "alerts", title: "Alerts", render: () => <AlertsWidget />, layout: { x: 0, y: 13, w: 7, h: 6, minW: 3, minH: 4 } },
  { id: "diff", title: "Since you left", render: () => <SinceYouLeft />, layout: { x: 7, y: 11, w: 5, h: 6, minW: 3, minH: 4 } },
  { id: "watchlist", title: "Watchlist", render: () => <WatchlistPanel />, layout: { x: 0, y: 19, w: 7, h: 6, minW: 4, minH: 4 } },
  { id: "next", title: "What's next", render: () => <WhatNext />, layout: { x: 7, y: 17, w: 5, h: 6, minW: 4, minH: 4 } },
];

export default function HomePage() {
  const { editing, setEditing } = useLayoutStore();
  return (
    <div>
      <div className="mb-2 flex items-center justify-end no-print">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setEditing(!editing)}
          aria-pressed={editing}
        >
          {editing ? <PencilOff size={14} /> : <Pencil size={14} />}
          {editing ? "Done" : "Edit layout"}
        </Button>
      </div>
      <WidgetGrid module="home" widgets={WIDGETS} />
    </div>
  );
}
