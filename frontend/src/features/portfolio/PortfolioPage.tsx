/** Portfolio: interactive equity curve + Monte Carlo, stats with sample
 * sizes, trades table (every P&L row links to its run — the killer
 * feature), memory-driven journal, integrity panel, exports. */
import { Download } from "lucide-react";
import { Link } from "react-router-dom";

import { EquityCurve } from "@/components/charts/EquityCurve";
import { DirectionBadge } from "@/components/DirectionBadge";
import { EmptyState } from "@/components/EmptyState";
import { StatCard } from "@/components/StatCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SkeletonCard } from "@/components/ui/skeleton";
import {
  useBacktest,
  useJournal,
  useMemoryInsights,
  useRuns,
  useStatus,
} from "@/lib/api/queries";
import { fmtDateTime, fmtPct, fmtPnl } from "@/lib/format";

export default function PortfolioPage() {
  const journal = useJournal();
  const backtest = useBacktest();
  const status = useStatus();
  const memory = useMemoryInsights();
  const runs = useRuns();

  const report = backtest.data?.report ?? {};
  const j = journal.data;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
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
                <EquityCurve
                  curve={backtest.data.equity_curve}
                  monteCarlo={backtest.data.monte_carlo ?? null}
                />
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
                detail="Run scripts/pro_real_replay.py to populate this panel with a real-data replay."
              />
            )}
          </CardContent>
        </Card>

        <div className="grid content-start gap-2">
          <StatCard
            label="Live paper P&L"
            value={fmtPnl(j?.total_pnl)}
            tone={j && j.total_pnl >= 0 ? "bull" : "bear"}
            n={j?.n_trades}
          />
          <StatCard
            label="Win rate"
            value={j?.win_rate != null ? fmtPct(j.win_rate, 0) : "—"}
            n={j?.n_trades}
          />
          <StatCard
            label="Backtest Sharpe"
            value={report.sharpe != null ? report.sharpe.toFixed(2) : "—"}
          />
          <StatCard
            label="Backtest max DD"
            value={report.max_drawdown != null ? fmtPct(report.max_drawdown) : "—"}
            tone="bear"
          />
          <StatCard
            label="Profit factor"
            value={report.profit_factor != null ? report.profit_factor.toFixed(2) : "—"}
          />
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Trades</CardTitle>
          <div className="flex gap-2 no-print">
            <a href="/api/export/journal.csv" download>
              <Button size="sm" variant="outline">
                <Download size={13} /> CSV
              </Button>
            </a>
            <Link to="/report">
              <Button size="sm" variant="outline">
                Report (PDF)
              </Button>
            </Link>
          </div>
        </CardHeader>
        <CardContent>
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
              <table className="w-full text-sm" data-testid="trades-table">
                <thead className="sticky top-0 bg-surface">
                  <tr className="border-b border-border text-left text-xs text-fg-subtle">
                    <th className="py-1 pr-2 font-medium">symbol</th>
                    <th className="py-1 pr-2 font-medium">action</th>
                    <th className="py-1 pr-2 font-medium">regime</th>
                    <th className="py-1 pr-2 text-right font-medium">P&L</th>
                    <th className="py-1 pr-2 font-medium">closed</th>
                    <th className="py-1 font-medium">why</th>
                  </tr>
                </thead>
                <tbody className="tabular">
                  {j!.entries.map((entry, i) => {
                    // best-effort run linkage: the run whose start precedes close
                    const run = [...(runs.data ?? [])]
                      .reverse()
                      .find(
                        (r) =>
                          r.symbol === entry.symbol &&
                          new Date(r.started_at) <= new Date(entry.closed_at),
                      );
                    return (
                      <tr key={i} className="border-b border-border/50">
                        <td className="py-1 pr-2 font-mono">{entry.symbol}</td>
                        <td className="py-1 pr-2">
                          <DirectionBadge value={entry.action} />
                        </td>
                        <td className="py-1 pr-2 text-fg-subtle">{entry.regime ?? "—"}</td>
                        <td
                          className={`py-1 pr-2 text-right ${entry.pnl >= 0 ? "text-bull" : "text-bear"}`}
                        >
                          {fmtPnl(entry.pnl)}
                        </td>
                        <td className="py-1 pr-2 text-xs text-fg-subtle">
                          {fmtDateTime(entry.closed_at)}
                        </td>
                        <td className="py-1">
                          {run ? (
                            <Link
                              to={`/decisions/${run.run_id}`}
                              className="text-xs text-accent hover:underline"
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

      <div className="grid gap-4 lg:grid-cols-2">
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
              <ul className="space-y-1.5 text-sm">
                {memory.data!.recent_lessons.map((lesson, i) => (
                  <li key={i} className="flex gap-2">
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
          <CardContent className="space-y-2 text-sm">
            {status.data?.attached ? (
              <>
                <p>
                  kill switch:{" "}
                  {status.data.kill_switch?.engaged ? (
                    <span className="text-bear">ENGAGED — {status.data.kill_switch.reason}</span>
                  ) : (
                    <span className="text-bull">armed, not fired</span>
                  )}
                </p>
                <p>
                  circuit breaker:{" "}
                  {status.data.circuit_breaker?.tripped ? (
                    <span className="text-bear">
                      TRIPPED — {status.data.circuit_breaker.reason}
                    </span>
                  ) : (
                    <span className="text-bull">clear</span>
                  )}
                </p>
                <p className="text-fg-subtle">
                  Audit log is hash-chained on disk; verify with
                  <code className="ml-1 font-mono text-xs">AuditLog(path).verify()</code>.
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
