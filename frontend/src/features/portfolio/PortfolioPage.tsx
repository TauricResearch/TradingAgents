/** Portfolio: interactive equity curve + Monte Carlo, stats with sample
 * sizes, trades table (every P&L row links to its run — the killer
 * feature), memory-driven journal, integrity panel, exports. */
import { Download } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { EquityCurve } from "@/components/charts/EquityCurve";
import { DirectionBadge } from "@/components/DirectionBadge";
import { EmptyState } from "@/components/EmptyState";
import { StatCard } from "@/components/StatCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SkeletonCard } from "@/components/ui/skeleton";
import { useQueryClient } from "@tanstack/react-query";

import { Sparkline } from "@/components/Sparkline";
import { apiFetch } from "@/lib/api/client";
import {
  qk,
  useBacktest,
  useJournal,
  useMemoryInsights,
  usePortfolioStats,
  useRiskBudget,
  useRuns,
  useStatus,
} from "@/lib/api/queries";
import { fmtDateTime, fmtPct, fmtPnl, fmtPrice } from "@/lib/format";
import { cn } from "@/lib/utils";

export default function PortfolioPage() {
  const journal = useJournal();
  const backtest = useBacktest();
  const status = useStatus();
  const memory = useMemoryInsights();
  const runs = useRuns();
  const [showDrawdown, setShowDrawdown] = useState(true);
  const [symbolFilter, setSymbolFilter] = useState("all");
  const [outcomeFilter, setOutcomeFilter] = useState("all");

  const j = journal.data;
  const stats = usePortfolioStats();
  const budget = useRiskBudget();
  const client = useQueryClient();
  const [btRunning, setBtRunning] = useState(false);
  const runReplay = async () => {
    setBtRunning(true);
    try {
      await apiFetch("/api/backtest/run?symbol=XAUUSD&timeframe=1d", {
        method: "POST",
      });
      await client.invalidateQueries({ queryKey: qk.backtest });
    } finally {
      setBtRunning(false);
    }
  };
  const perf = stats.data;
  const exposure = perf?.exposure;
  const budgetUsedPct = budget.data?.daily_loss_used_pct_of_budget ?? null;

  const symbolsInJournal = useMemo(
    () => [...new Set((j?.entries ?? []).map((e) => e.symbol))],
    [j],
  );
  const filteredEntries = (j?.entries ?? []).filter(
    (entry) =>
      (symbolFilter === "all" || entry.symbol === symbolFilter) &&
      (outcomeFilter === "all" ||
        (outcomeFilter === "won" ? entry.won === true : entry.won === false)),
  );

  return (
    <div className="space-y-[14px]">
      <div className="grid gap-[14px] lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card>
          <CardHeader>
            <CardTitle>Backtest equity</CardTitle>
            <Badge variant="stale">simulation — not live P&L</Badge>
          </CardHeader>
          <CardContent>
            {backtest.isPending ? (
              <SkeletonCard lines={6} />
            ) : backtest.data?.equity_curve && backtest.data.equity_curve.length > 1 ? (
              <>
                <label className="mb-1 flex items-center gap-1.5 text-xs text-fg-muted">
                  <input
                    type="checkbox"
                    className="accent-[var(--brand)]"
                    checked={showDrawdown}
                    onChange={() => setShowDrawdown(!showDrawdown)}
                  />
                  drawdown pane
                </label>
                <EquityCurve
                  curve={backtest.data.equity_curve}
                  monteCarlo={backtest.data.monte_carlo ?? null}
                  showDrawdown={showDrawdown}
                  height={170}
                />
                {backtest.data.report && (
                  <div className="mt-2 flex flex-wrap gap-x-[18px] text-xs text-fg-muted tabular">
                    <span>Sharpe <span className="font-bold">{backtest.data.report.sharpe?.toFixed(2) ?? "—"}</span></span>
                    <span>Sortino <span className="font-bold">{backtest.data.report.sortino?.toFixed(2) ?? "—"}</span></span>
                    <span>max DD <span className="font-bold text-bear">{backtest.data.report.max_drawdown != null ? fmtPct(backtest.data.report.max_drawdown) : "—"}</span></span>
                    <span>PF <span className="font-bold">{backtest.data.report.profit_factor?.toFixed(2) ?? "—"}</span></span>
                  </div>
                )}
                <p className="mt-2 text-xs text-fg-subtle">
                  {backtest.data.executed}/{backtest.data.decisions} decisions
                  executed · rejections{" "}
                  {Object.entries(backtest.data.rejections ?? {})
                    .map(([stage, count]) => `${stage}:${count}`)
                    .join(", ") || "none"}
                </p>
              </>
            ) : (
              <EmptyState
                kind="empty"
                title="No backtest yet"
                detail="Run a deterministic replay: the real pipeline over real bars with a scripted no-cost model — it exercises gates, sizing and exits, not model skill."
                action={
                  <Button
                    size="sm"
                    disabled={btRunning}
                    onClick={() => void runReplay()}
                    data-testid="run-backtest"
                  >
                    {btRunning ? "Replaying…" : "Run replay (free)"}
                  </Button>
                }
              />
            )}
          </CardContent>
        </Card>

        <div className="content-start space-y-2.5">
          <div className="grid grid-cols-2 gap-2.5">
            <StatCard
              elevated
              label="Live paper P&L"
              value={fmtPnl(j?.total_pnl)}
              tone={j && j.total_pnl >= 0 ? "bull" : "bear"}
              n={j?.n_trades}
            />
            <StatCard
              elevated
              label="Win rate"
              value={j?.win_rate != null ? fmtPct(j.win_rate, 0) : "—"}
              n={j?.n_trades}
            />
            <StatCard
              elevated
              label="Expectancy / trade"
              value={perf && perf.n_trades > 0 ? fmtPnl(perf.expectancy) : "—"}
              n={perf?.n_trades}
            />
            <StatCard
              elevated
              label="Profit factor"
              value={
                perf?.profit_factor != null ? perf.profit_factor.toFixed(2) : "—"
              }
              n={perf?.n_trades}
            />
            <StatCard
              elevated
              label="Max drawdown"
              value={
                perf && perf.n_trades > 0 ? fmtPct(perf.max_drawdown) : "—"
              }
              tone="bear"
              n={perf?.n_trades}
            />
            <StatCard
              elevated
              label="Day loss budget"
              value={
                budgetUsedPct != null ? `${budgetUsedPct.toFixed(0)}%` : "—"
              }
              tone={
                budgetUsedPct != null && budgetUsedPct >= 67
                  ? "bear"
                  : budgetUsedPct != null && budgetUsedPct >= 33
                    ? "neutral"
                    : undefined
              }
              sub={
                budget.data?.daily_loss_limit_usd != null
                  ? `${fmtPnl(budget.data.daily_pnl)} today · limit ${fmtPrice(
                      budget.data.daily_loss_limit_usd,
                      0,
                    )}`
                  : undefined
              }
            />
          </div>
          {perf && perf.n_trades >= 2 && (
            <div
              className="rounded-[14px] bg-surface-2 px-3.5 py-2.5"
              data-testid="live-equity-spark"
            >
              <div className="mb-1 flex items-center justify-between">
                <span className="text-[9.5px] font-bold uppercase tracking-[0.09em] text-fg-subtle">
                  Closed-trade equity
                </span>
                <span
                  className={cn(
                    "font-mono text-xs font-bold tabular",
                    perf.total_return >= 0 ? "text-bull" : "text-bear",
                  )}
                >
                  {fmtPct(perf.total_return)}
                </span>
              </div>
              <Sparkline
                values={perf.equity_curve}
                width={260}
                height={36}
                ariaLabel="closed-trade equity curve"
              />
            </div>
          )}
        </div>
      </div>

      <Card data-testid="open-risk">
        <CardHeader>
          <CardTitle>Open risk</CardTitle>
        </CardHeader>
        <CardContent>
          {(status.data?.open_positions?.length ?? 0) === 0 ? (
            <EmptyState kind="empty" title="No open positions"
                        detail="Open risk appears here the moment the book is non-flat." />
          ) : (
            <div className="space-y-2">
              {exposure && exposure.n_priced > 0 && (
                <div
                  className="flex flex-wrap gap-x-[18px] gap-y-1 rounded-[12px] bg-surface-2 px-3.5 py-2 text-xs text-fg-muted tabular"
                  data-testid="exposure-summary"
                >
                  <span>gross <span className="font-bold text-fg">{exposure.gross_exposure_pct?.toFixed(1)}%</span></span>
                  <span>net <span className={cn("font-bold", (exposure.net_exposure_pct ?? 0) >= 0 ? "text-bull" : "text-bear")}>{exposure.net_exposure_pct?.toFixed(1)}%</span></span>
                  <span>long <span className="font-bold text-bull">{exposure.long_exposure_pct?.toFixed(1)}%</span></span>
                  <span>short <span className="font-bold text-bear">{exposure.short_exposure_pct?.toFixed(1)}%</span></span>
                  <span>largest <span className="font-bold text-fg">{exposure.largest_position_pct?.toFixed(1)}%</span></span>
                  <span>slots <span className="font-bold text-fg">{exposure.n_positions}/{exposure.max_open_positions}</span></span>
                </div>
              )}
              <table className="w-full text-sm tabular">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-fg-subtle">
                    <th className="py-1 font-medium">symbol</th>
                    <th className="py-1 text-right font-medium">qty</th>
                    <th className="py-1 text-right font-medium">entry</th>
                    <th className="py-1 text-right font-medium">mark</th>
                    <th className="py-1 text-right font-medium">unrealized</th>
                    <th className="py-1 text-right font-medium">exposure</th>
                  </tr>
                </thead>
                <tbody>
                  {status.data!.open_positions!.map((p) => (
                    <tr key={p.symbol}>
                      <td className="py-1 font-mono">{p.symbol}</td>
                      <td className="py-1 text-right">
                        {p.quantity > 0 ? "+" : ""}{p.quantity}
                      </td>
                      <td className="py-1 text-right font-mono">{fmtPrice(p.entry_price)}</td>
                      <td className="py-1 text-right font-mono">
                        {fmtPrice(p.mark_price)}
                        {p.mark_source && p.mark_source !== "live" && (
                          <span className="ml-1 text-[10px] uppercase text-stale">
                            {p.mark_source}
                          </span>
                        )}
                      </td>
                      <td className={cn(
                        "py-1 text-right font-mono",
                        p.unrealized_pnl != null &&
                          (p.unrealized_pnl >= 0 ? "text-bull" : "text-bear"),
                      )}>
                        {fmtPnl(p.unrealized_pnl)}
                      </td>
                      <td className="py-1 text-right">
                        {p.exposure_pct != null ? `${p.exposure_pct.toFixed(1)}%` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {(status.data as { unrealized_total?: number | null }).unrealized_total != null && (
                <p className="text-xs text-fg-muted">
                  total unrealized{" "}
                  <span className={cn(
                    "font-mono font-semibold tabular",
                    (status.data as { unrealized_total?: number }).unrealized_total! >= 0
                      ? "text-bull" : "text-bear",
                  )}>
                    {fmtPnl((status.data as { unrealized_total?: number }).unrealized_total)}
                  </span>
                  {" "}· marks labeled EOD/entry when no live tick is available
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Trades</CardTitle>
          <div className="flex flex-wrap items-center gap-2 no-print">
            <select
              value={symbolFilter}
              onChange={(event) => setSymbolFilter(event.target.value)}
              aria-label="Filter by symbol"
              className="h-[30px] rounded-[10px] border border-border-strong bg-surface-2 px-2.5 text-xs"
            >
              <option value="all">all symbols</option>
              {symbolsInJournal.map((sym) => (
                <option key={sym} value={sym}>{sym}</option>
              ))}
            </select>
            <select
              value={outcomeFilter}
              onChange={(event) => setOutcomeFilter(event.target.value)}
              aria-label="Filter by outcome"
              className="h-[30px] rounded-[10px] border border-border-strong bg-surface-2 px-2.5 text-xs"
            >
              <option value="all">all outcomes</option>
              <option value="won">wins</option>
              <option value="lost">losses</option>
            </select>
            <a href="/api/export/journal.csv" download>
              <Button size="sm" variant="outline">
                <Download size={13} /> CSV
              </Button>
            </a>
            <Link to="/report">
              <Button size="sm">
                Report (PDF)
              </Button>
            </Link>
          </div>
        </CardHeader>
        <CardContent>
          {j?.by_mode &&
            Object.keys(j.by_mode).some((m) => m !== "paper") && (
              <div
                className="mb-3 flex flex-wrap gap-2 text-xs"
                data-testid="journal-by-mode"
              >
                {Object.entries(j.by_mode).map(([mode, s]) => (
                  <span
                    key={mode}
                    className="rounded-full border border-border-strong px-2.5 py-0.5"
                  >
                    <span className="font-semibold uppercase">{mode}</span>{" "}
                    {s.n_trades} trades ·{" "}
                    {s.win_rate != null ? fmtPct(s.win_rate, 0) : "—"} win ·{" "}
                    {fmtPnl(s.total_pnl)}
                  </span>
                ))}
              </div>
            )}
          {journal.isPending ? (
            <SkeletonCard lines={4} />
          ) : (j?.entries.length ?? 0) === 0 ? (
            <EmptyState
              kind="empty"
              title="No closed trades yet"
              detail="Every closed trade will appear here, linked to the run that reasoned it into existence."
            />
          ) : (
            <div className="max-h-96 overflow-y-auto">
              <table className="w-full text-[13px]" data-testid="trades-table">
                <thead className="sticky top-0 bg-surface-solid">
                  <tr className="border-b border-border text-left text-[11px] text-fg-subtle">
                    <th className="py-1.5 pr-2 font-semibold">symbol</th>
                    <th className="py-1.5 pr-2 font-semibold">action</th>
                    <th className="py-1.5 pr-2 font-semibold">regime</th>
                    <th className="py-1.5 pr-2 text-right font-semibold">P&L</th>
                    <th className="py-1.5 pr-2 font-semibold">closed</th>
                    <th className="py-1.5 font-semibold">why</th>
                  </tr>
                </thead>
                <tbody className="tabular">
                  {filteredEntries.map((entry, i) => {
                    // best-effort run linkage: the run whose start precedes close
                    const run = [...(runs.data ?? [])]
                      .reverse()
                      .find(
                        (r) =>
                          r.symbol === entry.symbol &&
                          new Date(r.started_at) <= new Date(entry.closed_at),
                      );
                    return (
                      <tr key={i} className="border-b border-border">
                        <td className="py-[7px] pr-2 font-mono font-semibold">{entry.symbol}</td>
                        <td className="py-[7px] pr-2">
                          <span
                            className={
                              "inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-bold " +
                              (entry.action === "SELL"
                                ? "bg-bear-muted"
                                : entry.action === "BUY"
                                  ? "bg-bull-muted"
                                  : "bg-neutral-muted")
                            }
                          >
                            <DirectionBadge value={entry.action} />
                          </span>
                        </td>
                        <td className="py-[7px] pr-2 text-fg-subtle">{entry.regime ?? "—"}</td>
                        <td
                          className={`py-[7px] pr-2 text-right font-mono font-bold ${entry.pnl >= 0 ? "text-bull" : "text-bear"}`}
                        >
                          {fmtPnl(entry.pnl)}
                        </td>
                        <td className="py-[7px] pr-2 text-[11px] text-fg-subtle">
                          {fmtDateTime(entry.closed_at)}
                        </td>
                        <td className="py-[7px]">
                          {run ? (
                            <Link
                              to={`/decisions/${run.run_id}`}
                              className="text-xs font-semibold text-accent hover:underline"
                            >
                              view reasoning →
                            </Link>
                          ) : (
                            <span className="text-xs text-fg-subtle">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-[14px] lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Journal — lessons the system wrote itself</CardTitle>
          </CardHeader>
          <CardContent>
            {memory.isPending ? (
              <SkeletonCard lines={4} />
            ) : (memory.data?.recent_lessons.length ?? 0) === 0 ? (
              <EmptyState kind="empty" title="No lessons recorded yet" />
            ) : (
              <ul className="space-y-2 text-[13px]">
                {memory.data!.recent_lessons.map((lesson, i) => (
                  <li key={i} className="flex gap-2.5">
                    <Badge
                      variant={lesson.kind === "mistake" ? "bear" : "bull"}
                      className="shrink-0 self-start"
                    >
                      {lesson.kind}
                    </Badge>
                    <span className="text-fg-muted">{lesson.text}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Integrity</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-[13px]">
            {status.data?.attached ? (
              <>
                <p>
                  kill switch:{" "}
                  {status.data.kill_switch?.engaged ? (
                    <span className="font-bold text-bear">ENGAGED — {status.data.kill_switch.reason}</span>
                  ) : (
                    <span className="font-bold text-bull">armed, not fired</span>
                  )}
                </p>
                <p>
                  circuit breaker:{" "}
                  {status.data.circuit_breaker?.tripped ? (
                    <span className="font-bold text-bear">
                      TRIPPED — {status.data.circuit_breaker.reason}
                    </span>
                  ) : (
                    <span className="font-bold text-bull">clear</span>
                  )}
                </p>
                <p className="text-fg-subtle">
                  Audit log is hash-chained on disk; verify with
                  <code className="ml-1 rounded-[6px] bg-surface-2 px-1.5 py-px font-mono text-xs">AuditLog(path).verify()</code>.
                </p>
              </>
            ) : (
              <EmptyState
                kind="empty"
                title="Monitor mode"
                detail="No execution router attached — integrity panel activates with the paper loop."
              />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
