/** Print-ready report over /api/export/report.json: the browser's
 * print-to-PDF produces the artifact (zero heavy PDF deps, honest
 * fidelity). The @media print stylesheet strips the chrome. */
import { useQuery } from "@tanstack/react-query";
import { Printer } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { SkeletonCard } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api/client";
import { fmtDateTime, fmtPnl, fmtPct } from "@/lib/format";

interface Report {
  generated_at: string;
  app_version: string;
  overview: Record<string, unknown>;
  recommendation: Record<string, unknown>;
  status: Record<string, unknown>;
  journal: {
    entries: { symbol: string; action: string | null; pnl: number; closed_at: string }[];
    total_pnl: number;
    n_trades: number;
    win_rate: number | null;
  };
  backtest: Record<string, unknown>;
  agents: Record<string, { votes: number; hit_rate: number | null; scored: number }>;
  alerts: { alerts: { severity: string; text: string; time: string }[] };
}

export default function ReportPage() {
  const report = useQuery({
    queryKey: ["export-report"],
    queryFn: () => apiFetch<Report>("/api/export/report.json"),
    staleTime: 0,
  });

  if (report.isPending) return <SkeletonCard lines={10} />;
  if (report.isError || !report.data)
    return <EmptyState kind="error" title="Report unavailable" detail={String(report.error)} />;

  const r = report.data;
  return (
    <article className="mx-auto max-w-[760px] space-y-6 rounded-[20px] border border-border bg-surface-solid px-10 py-9 shadow-(--shadow-1) print:rounded-none print:border-0 print:bg-white print:p-0 print:shadow-none">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold">TradingAgents Pro — Operations Report</h1>
          <p className="text-sm text-fg-muted">
            generated {fmtDateTime(r.generated_at)} · version {r.app_version}
          </p>
        </div>
        <Button className="no-print" onClick={() => window.print()}>
          <Printer size={14} /> Print / Save PDF
        </Button>
      </header>

      <section>
        <h2 className="mb-2 border-b border-border pb-1 font-semibold">Trading summary</h2>
        <p className="text-sm">
          {r.journal.n_trades} closed trades, net {fmtPnl(r.journal.total_pnl)}
          {r.journal.win_rate != null && <> · win rate {fmtPct(r.journal.win_rate, 0)}</>}
        </p>
        <table className="mt-2 w-full text-sm tabular">
          <thead>
            <tr className="border-b border-border text-left text-xs">
              <th className="py-1 font-medium">symbol</th>
              <th className="py-1 font-medium">action</th>
              <th className="py-1 text-right font-medium">P&L</th>
              <th className="py-1 pl-8 font-medium">closed</th>
            </tr>
          </thead>
          <tbody>
            {r.journal.entries.map((entry, i) => (
              <tr key={i} className="border-b border-border/40">
                <td className="py-1 font-mono">{entry.symbol}</td>
                <td className="py-1">{entry.action ?? "—"}</td>
                <td className="py-1 text-right">{fmtPnl(entry.pnl)}</td>
                <td className="py-1 pl-8 text-xs">{fmtDateTime(entry.closed_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2 className="mb-2 border-b border-border pb-1 font-semibold">Agent accuracy</h2>
        {Object.values(r.agents).every((a) => a.scored === 0) ? (
          <p className="text-sm text-fg-muted">
            No scored outcomes yet — agents score once the trades they voted
            on close.
          </p>
        ) : (
        <table className="w-full text-sm tabular">
          <thead>
            <tr className="border-b border-border text-left text-xs">
              <th className="py-1 font-medium">agent</th>
              <th className="py-1 text-right font-medium">votes</th>
              <th className="py-1 text-right font-medium">hit rate</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(r.agents)
              .filter(([, a]) => a.scored > 0)
              .sort((a, b) => (b[1].hit_rate ?? 0) - (a[1].hit_rate ?? 0))
              .map(([agent, a]) => (
                <tr key={agent} className="border-b border-border/40">
                  <td className="py-1 font-mono">{agent}</td>
                  <td className="py-1 text-right">{a.votes}</td>
                  <td className="py-1 text-right">
                    {a.hit_rate != null
                      ? `${Math.round(a.hit_rate * 100)}% (n=${a.scored})`
                      : "—"}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
        )}
      </section>

      <section>
        <h2 className="mb-2 border-b border-border pb-1 font-semibold">Alerts</h2>
        {r.alerts.alerts.length === 0 ? (
          <p className="text-sm text-fg-muted">No alerts in the recorded window.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {r.alerts.alerts.map((alert, i) => (
              <li key={i}>
                <span className="uppercase">{alert.severity}</span> — {alert.text}{" "}
                <span className="text-xs text-fg-subtle">{fmtDateTime(alert.time)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <footer className="border-t border-border pt-2 text-xs text-fg-subtle">
        Paper trading only. Not investment advice. All numbers computed by the
        deterministic pipeline; LLMs never calculate financial quantities.
      </footer>
    </article>
  );
}
