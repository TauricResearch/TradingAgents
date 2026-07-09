/** Home: the 5-second briefing. Above the fold, in priority order —
 * safety (strip above), the AI's current stance, P&L, prices, alerts,
 * what changed, what's next. No charts here: Workspace owns them. */
import { Pencil, PencilOff } from "lucide-react";
import { Link } from "react-router-dom";

import { AlertFeedList } from "@/components/AlertFeedList";
import { DecisionCard } from "@/components/DecisionCard";
import { EmptyState } from "@/components/EmptyState";
import { Sparkline } from "@/components/Sparkline";
import { StatCard } from "@/components/StatCard";
import { Button } from "@/components/ui/button";
import { SkeletonCard } from "@/components/ui/skeleton";
import { WatchlistPanel } from "@/components/WatchlistPanel";
import { WidgetGrid, type WidgetDef } from "@/components/WidgetGrid";
import {
  useAlerts,
  useBacktest,
  useCalendar,
  useJournal,
  useOverview,
  useRecommendation,
  useRuns,
  useStatus,
} from "@/lib/api/queries";
import { fmtPnl, fmtPrice, fmtDateTime, fmtPct } from "@/lib/format";
import { useTick } from "@/stores/ticker";
import { useLayoutStore } from "@/stores/layout";
import { useUiStore } from "@/stores/ui";

function DecisionHero() {
  const rec = useRecommendation();
  const overview = useOverview();
  if (rec.isPending) return <SkeletonCard lines={5} />;
  if (rec.isError)
    return <EmptyState kind="error" title="Decision unavailable" detail={String(rec.error)} />;
  return (
    <DecisionCard rec={rec.data} runId={overview.data?.run_id ?? null} />
  );
}

function PortfolioSnapshot() {
  const status = useStatus();
  const journal = useJournal();
  const backtest = useBacktest();
  if (journal.isPending) return <SkeletonCard lines={4} />;
  const j = journal.data;
  return (
    <div className="grid grid-cols-2 gap-2">
      <StatCard
        label="Equity"
        value={status.data?.equity != null ? fmtPrice(status.data.equity, 0) : "—"}
        sub={
          status.data?.attached === false ? "monitor mode — no execution attached" : undefined
        }
      />
      <StatCard
        label="Total P&L"
        value={fmtPnl(j?.total_pnl)}
        tone={j && j.total_pnl >= 0 ? "bull" : "bear"}
        n={j?.n_trades}
        sub={j?.win_rate != null ? `win rate ${fmtPct(j.win_rate, 0)}` : "no closed trades"}
      />
      <div className="col-span-2 flex items-center justify-between rounded-md border border-border bg-surface-2/50 px-3 py-2">
        <span className="text-xs uppercase tracking-wide text-fg-subtle">
          Backtest equity
        </span>
        {backtest.data?.equity_curve && backtest.data.equity_curve.length > 1 ? (
          <Sparkline values={backtest.data.equity_curve} width={160} height={32} />
        ) : (
          <span className="text-xs text-fg-subtle">no backtest yet</span>
        )}
      </div>
      <Link to="/portfolio" className="col-span-2 text-sm text-accent hover:underline">
        Open portfolio →
      </Link>
    </div>
  );
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
            className="rounded-md border border-border bg-surface-2/50 px-3 py-2 hover:border-border-strong"
          >
            <div className="text-xs text-fg-subtle">{row.symbol}</div>
            <div className="font-mono text-lg tabular">{fmtPrice(price)}</div>
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
  const releases = (calendar.data?.releases ?? []).slice(0, 5);
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
  { id: "decision", title: "Decision", render: () => <DecisionHero />, layout: { x: 0, y: 0, w: 7, h: 10, minW: 4, minH: 7 } },
  { id: "snapshot", title: "Portfolio snapshot", render: () => <PortfolioSnapshot />, layout: { x: 7, y: 0, w: 5, h: 6, minW: 3, minH: 5 } },
  { id: "prices", title: "Prices", render: () => <PriceRibbon />, layout: { x: 7, y: 6, w: 5, h: 4, minW: 3, minH: 4 } },
  { id: "alerts", title: "Alerts", render: () => <AlertsWidget />, layout: { x: 0, y: 10, w: 7, h: 6, minW: 3, minH: 4 } },
  { id: "diff", title: "Since you left", render: () => <SinceYouLeft />, layout: { x: 7, y: 10, w: 5, h: 6, minW: 3, minH: 4 } },
  { id: "watchlist", title: "Watchlist", render: () => <WatchlistPanel />, layout: { x: 0, y: 16, w: 7, h: 6, minW: 4, minH: 4 } },
  { id: "next", title: "What's next", render: () => <WhatNext />, layout: { x: 7, y: 16, w: 5, h: 6, minW: 4, minH: 4 } },
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
