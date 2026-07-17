/** The record, in one place (B2): "trust the process" becomes "here's the
 * record." Consolidates the live closed-trade performance, the retro-graded
 * calibration curve, and per-agent hit rates — honestly labeled live vs
 * retro, with the definition of "proven" stated BEFORE the numbers so the
 * page can't be accused of moving the goalposts. */
import { AgentLeaderboard } from "@/components/AgentLeaderboard";
import { CalibrationChart } from "@/components/CalibrationChart";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonCard } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAgents, useJournal, usePortfolioStats } from "@/lib/api/queries";
import { fmtPct, fmtPnl } from "@/lib/format";

const PROVEN_N = 100;

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "bull" | "bear";
}) {
  return (
    <div className="rounded-xl border border-border px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-fg-subtle">
        {label}
      </div>
      <div
        className={
          "mt-0.5 font-mono text-lg tabular " +
          (tone === "bull" ? "text-bull" : tone === "bear" ? "text-bear" : "text-fg")
        }
      >
        {value}
      </div>
    </div>
  );
}

export default function TrackRecordPage() {
  const stats = usePortfolioStats();
  const journal = useJournal();
  const agents = useAgents();

  const n = stats.data?.n_trades ?? 0;
  const scored = agents.data
    ? Math.max(0, ...Object.values(agents.data).map((a) => a.scored ?? 0))
    : 0;

  return (
    <div className="space-y-4">
      {/* the honesty banner — stated before any number */}
      <Card>
        <CardContent className="space-y-1 py-3 text-sm">
          <p className="text-fg">
            This is the system's own record — no backtest curve-fit, no cherry
            picking.
          </p>
          <p className="text-xs text-fg-subtle">
            "Proven" means ≥{PROVEN_N} closed trades with the calibration
            curve within ±10 points of the diagonal and profit factor &gt; 1
            net of costs. Live closed trades: <b>{n}</b>. Retro-graded
            decisions feeding calibration:{" "}
            <b>{scored}</b>. Retro grades price real past recommendations
            against what happened next; they fuel calibration but never enter
            the live blotter.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Live closed-trade record</CardTitle>
        </CardHeader>
        <CardContent>
          {stats.isPending ? (
            <SkeletonCard lines={3} />
          ) : n === 0 ? (
            <EmptyState
              kind="empty"
              title="No closed trades yet"
              detail="The record fills as the paper loop's positions resolve. Retro grades below already fuel calibration."
            />
          ) : (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
              <Stat label="closed" value={String(n)} />
              <Stat
                label="win rate"
                value={stats.data!.win_rate != null ? fmtPct(stats.data!.win_rate) : "—"}
              />
              <Stat
                label="net P&L"
                value={fmtPnl(stats.data!.total_pnl)}
                tone={stats.data!.total_pnl >= 0 ? "bull" : "bear"}
              />
              <Stat
                label="total return"
                value={fmtPct(stats.data!.total_return)}
                tone={stats.data!.total_return >= 0 ? "bull" : "bear"}
              />
              <Stat
                label="profit factor"
                value={stats.data!.profit_factor?.toFixed(2) ?? "—"}
              />
              <Stat label="expectancy" value={fmtPnl(stats.data!.expectancy)} />
              <Stat label="max drawdown" value={fmtPct(stats.data!.max_drawdown)} />
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Calibration (retro-graded)</CardTitle>
          </CardHeader>
          <CardContent>
            {agents.isPending ? (
              <SkeletonCard lines={4} />
            ) : agents.data ? (
              <CalibrationChart perf={agents.data} />
            ) : (
              <EmptyState kind="empty" title="No calibration data yet" />
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Agent hit rates</CardTitle>
          </CardHeader>
          <CardContent>
            {agents.isPending ? (
              <SkeletonCard lines={4} />
            ) : agents.data ? (
              <AgentLeaderboard perf={agents.data} />
            ) : (
              <EmptyState kind="empty" title="No agent record yet" />
            )}
          </CardContent>
        </Card>
      </div>

      <p className="text-center text-xs text-fg-subtle">
        {journal.data?.entries?.length ? (
          <>Full trade blotter and journal on the Portfolio page.</>
        ) : (
          <>Paper trading only — not investment advice.</>
        )}
      </p>
    </div>
  );
}
