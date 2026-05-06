"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Portfolio } from "@/lib/api";
import { priceStreamUrl } from "@/lib/ws";
import type { PortfolioSummary, PriceTick } from "@/lib/types";

export default function PortfolioPage() {
  const qc = useQueryClient();
  const summary = useQuery<PortfolioSummary>({
    queryKey: ["portfolio-summary"],
    queryFn: () => Portfolio.summary(),
    // Refetch summary every 30s to capture new live prices.
    refetchInterval: 30_000,
  });

  // Open price websockets for each held ticker so the page updates in
  // between polls.
  const tickers = (summary.data?.open_positions ?? []).map((p) => p.ticker);
  const wsRef = useRef<Map<string, WebSocket>>(new Map());
  useEffect(() => {
    const sockets = wsRef.current;
    for (const [t, ws] of sockets) if (!tickers.includes(t)) { ws.close(); sockets.delete(t); }
    for (const t of tickers) {
      if (sockets.has(t)) continue;
      const ws = new WebSocket(priceStreamUrl(t));
      ws.onmessage = () => qc.invalidateQueries({ queryKey: ["portfolio-summary"] });
      sockets.set(t, ws);
    }
    return () => {
      for (const ws of sockets.values()) ws.close();
      sockets.clear();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tickers.join(",")]);

  const [showForm, setShowForm] = useState(false);

  return (
    <div className="space-y-4">
      <header className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Portfolio</h1>
          <p className="text-muted text-sm">
            Track open positions with live valuation. Closed positions
            contribute to realised P&amp;L.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowForm((s) => !s)}>
          {showForm ? "Cancel" : "+ Open position"}
        </button>
      </header>

      {showForm && <NewPositionForm onDone={() => { setShowForm(false); qc.invalidateQueries({ queryKey: ["portfolio-summary"] }); }} />}

      <SummaryCards summary={summary.data} />

      <div className="card overflow-x-auto">
        <h2 className="font-semibold mb-2">Open positions</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs uppercase text-muted">
              <th className="text-left py-2 px-3 font-medium">Ticker</th>
              <th className="text-right py-2 px-3 font-medium">Shares</th>
              <th className="text-right py-2 px-3 font-medium">Cost basis</th>
              <th className="text-right py-2 px-3 font-medium">Cost</th>
              <th className="text-right py-2 px-3 font-medium">Live</th>
              <th className="text-right py-2 px-3 font-medium">Value</th>
              <th className="text-right py-2 px-3 font-medium">Unrealised</th>
              <th className="text-left py-2 px-3 font-medium">Account</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {summary.isLoading && <tr><td colSpan={9} className="py-6 text-center text-muted">Loading…</td></tr>}
            {!summary.isLoading && (summary.data?.open_positions.length ?? 0) === 0 && (
              <tr><td colSpan={9} className="py-6 text-center text-muted">
                No open positions. Click "+ Open position" above to add one.
              </td></tr>
            )}
            {(summary.data?.open_positions ?? []).map((p) => {
              const sign = (p.unrealized ?? 0) >= 0;
              return (
                <tr key={p.id} className="border-t border-border">
                  <td className="py-2 px-3 font-semibold">{p.ticker}</td>
                  <td className="py-2 px-3 text-right tabular-nums">{p.shares}</td>
                  <td className="py-2 px-3 text-right tabular-nums">${p.cost_basis_per_share.toFixed(2)}</td>
                  <td className="py-2 px-3 text-right tabular-nums">${p.cost.toFixed(2)}</td>
                  <td className="py-2 px-3 text-right tabular-nums">{p.live_price ? `$${p.live_price.toFixed(2)}` : "—"}</td>
                  <td className="py-2 px-3 text-right tabular-nums">{p.value ? `$${p.value.toFixed(2)}` : "—"}</td>
                  <td className={`py-2 px-3 text-right tabular-nums ${p.unrealized == null ? "" : sign ? "text-success" : "text-danger"}`}>
                    {p.unrealized != null ? `${sign ? "+" : ""}$${p.unrealized.toFixed(2)} (${p.unrealized_pct?.toFixed(2)}%)` : "—"}
                  </td>
                  <td className="py-2 px-3 text-muted">{p.account ?? ""}</td>
                  <td className="py-2 px-3 text-right">
                    <PositionActions p={p} onChanged={() => qc.invalidateQueries({ queryKey: ["portfolio-summary"] })} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SummaryCards({ summary }: { summary?: PortfolioSummary }) {
  if (!summary) return null;
  const sign = (summary.unrealized_pnl ?? 0) >= 0;
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <Stat label="Open positions" value={String(summary.open_count)} />
      <Stat label="Total cost" value={`$${summary.total_cost.toFixed(2)}`} />
      <Stat label="Current value" value={summary.total_value ? `$${summary.total_value.toFixed(2)}` : "—"} />
      <Stat
        label="Unrealised P&L"
        value={
          summary.unrealized_pnl != null
            ? `${sign ? "+" : ""}$${summary.unrealized_pnl.toFixed(2)} (${summary.unrealized_pnl_pct?.toFixed(2)}%)`
            : "—"
        }
        accent={sign ? "success" : "danger"}
      />
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: "success" | "danger" }) {
  return (
    <div className="card">
      <div className="text-xs text-muted">{label}</div>
      <div className={`text-xl font-semibold mt-1 ${accent === "success" ? "text-success" : accent === "danger" ? "text-danger" : ""}`}>
        {value}
      </div>
    </div>
  );
}

function NewPositionForm({ onDone }: { onDone: () => void }) {
  const [ticker, setTicker] = useState("");
  const [shares, setShares] = useState("");
  const [costBasis, setCostBasis] = useState("");
  const [account, setAccount] = useState("");
  const [notes, setNotes] = useState("");

  const create = useMutation({
    mutationFn: () => Portfolio.addPosition({
      ticker: ticker.trim().toUpperCase(),
      shares: parseFloat(shares),
      cost_basis_per_share: parseFloat(costBasis),
      account: account.trim() || undefined,
      notes: notes.trim() || undefined,
    }),
    onSuccess: onDone,
  });

  return (
    <form
      className="card grid grid-cols-2 md:grid-cols-3 gap-3"
      onSubmit={(e) => { e.preventDefault(); create.mutate(); }}
    >
      <div>
        <label className="label">Ticker</label>
        <input className="input w-full" value={ticker} onChange={(e) => setTicker(e.target.value)} required />
      </div>
      <div>
        <label className="label">Shares</label>
        <input className="input w-full" type="number" step="any" value={shares} onChange={(e) => setShares(e.target.value)} required />
      </div>
      <div>
        <label className="label">Cost / share</label>
        <input className="input w-full" type="number" step="any" value={costBasis} onChange={(e) => setCostBasis(e.target.value)} required />
      </div>
      <div className="col-span-2">
        <label className="label">Account (optional)</label>
        <input className="input w-full" value={account} onChange={(e) => setAccount(e.target.value)} placeholder="Brokerage / IRA / 401k" />
      </div>
      <div className="col-span-3">
        <label className="label">Notes</label>
        <input className="input w-full" value={notes} onChange={(e) => setNotes(e.target.value)} />
      </div>
      <div className="col-span-3 flex justify-end">
        <button className="btn btn-primary" type="submit" disabled={create.isPending}>
          {create.isPending ? "Saving…" : "Open position"}
        </button>
      </div>
    </form>
  );
}

function PositionActions({ p, onChanged }: { p: { id: number; ticker: string; live_price: number | null }; onChanged: () => void }) {
  const close = useMutation({
    mutationFn: (price: number) => Portfolio.closePosition(p.id, { closing_price: price }),
    onSuccess: onChanged,
  });
  const del = useMutation({
    mutationFn: () => Portfolio.deletePosition(p.id),
    onSuccess: onChanged,
  });

  return (
    <div className="flex gap-1 justify-end">
      <button
        className="btn text-xs"
        onClick={() => {
          const def = p.live_price?.toFixed(2) ?? "";
          const v = prompt(`Close ${p.ticker} at price?`, def);
          if (v) close.mutate(parseFloat(v));
        }}
        disabled={close.isPending}
      >
        Close
      </button>
      <button
        className="btn btn-danger text-xs"
        onClick={() => { if (confirm(`Delete this position outright (no realised P&L recorded)?`)) del.mutate(); }}
      >
        ✕
      </button>
    </div>
  );
}
