"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Runs } from "@/lib/api";
import { decisionColor, fmtDate, fmtTokens, statusColor } from "@/lib/format";

export default function HistoryPage() {
  const q = useQuery({ queryKey: ["runs"], queryFn: () => Runs.list() });
  const [tickerFilter, setTickerFilter] = useState("");
  const [decisionFilter, setDecisionFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const filtered = useMemo(() => {
    let rows = q.data ?? [];
    if (tickerFilter) {
      const f = tickerFilter.toUpperCase();
      rows = rows.filter((r) => r.ticker.includes(f));
    }
    if (decisionFilter) {
      rows = rows.filter((r) => (r.decision ?? "").toUpperCase().includes(decisionFilter.toUpperCase()));
    }
    if (statusFilter) {
      rows = rows.filter((r) => r.status === statusFilter);
    }
    return rows;
  }, [q.data, tickerFilter, decisionFilter, statusFilter]);

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-bold">Run history</h1>
        <p className="text-muted text-sm">
          Every analysis run, indexed and browsable. Click a row for the full transcript, brief, chart, exports, and chat.
        </p>
      </header>

      <div className="flex flex-wrap gap-3">
        <div>
          <label className="label">Ticker</label>
          <input
            className="input"
            placeholder="filter…"
            value={tickerFilter}
            onChange={(e) => setTickerFilter(e.target.value)}
          />
        </div>
        <div>
          <label className="label">Decision</label>
          <input
            className="input"
            placeholder="BUY / HOLD / SELL"
            value={decisionFilter}
            onChange={(e) => setDecisionFilter(e.target.value)}
          />
        </div>
        <div>
          <label className="label">Status</label>
          <select
            className="input"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All</option>
            <option value="done">done</option>
            <option value="running">running</option>
            <option value="error">error</option>
          </select>
        </div>
        <div className="flex items-end pb-1.5 ml-auto text-sm text-muted">
          {filtered.length} of {q.data?.length ?? 0} runs
        </div>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs uppercase text-muted">
              <th className="text-left py-2 px-3 font-medium">Ticker</th>
              <th className="text-left py-2 px-3 font-medium">Trade date</th>
              <th className="text-left py-2 px-3 font-medium">Decision</th>
              <th className="text-left py-2 px-3 font-medium">Provider/Model</th>
              <th className="text-right py-2 px-3 font-medium">Tokens</th>
              <th className="text-left py-2 px-3 font-medium">Status</th>
              <th className="text-left py-2 px-3 font-medium">Started</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {q.isLoading && (
              <tr>
                <td colSpan={8} className="py-6 text-center text-muted">
                  Loading runs…
                </td>
              </tr>
            )}
            {!q.isLoading && filtered.length === 0 && (
              <tr>
                <td colSpan={8} className="py-6 text-center text-muted">
                  No runs match these filters.
                </td>
              </tr>
            )}
            {filtered.map((r) => (
              <tr key={r.run_id} className="border-t border-border hover:bg-bg/40">
                <td className="py-2 px-3 font-semibold">{r.ticker}</td>
                <td className="py-2 px-3">{r.trade_date}</td>
                <td className={`py-2 px-3 font-semibold ${decisionColor(r.decision)}`}>
                  {r.decision ?? "—"}
                </td>
                <td className="py-2 px-3 text-muted">
                  {r.provider ?? "—"} / {r.deep_model ?? "—"}
                </td>
                <td className="py-2 px-3 text-right text-muted">
                  {fmtTokens(r.tokens_in)}↑ / {fmtTokens(r.tokens_out)}↓
                </td>
                <td className="py-2 px-3">
                  <span className={`pill ${statusColor(r.status)}`}>{r.status}</span>
                </td>
                <td className="py-2 px-3 text-muted">{fmtDate(r.started_at)}</td>
                <td className="py-2 px-3 text-right">
                  <Link className="text-accent hover:underline" href={`/history/${r.run_id}`}>
                    Open →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
