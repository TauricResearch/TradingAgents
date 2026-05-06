"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Watchlist } from "@/lib/api";
import { priceStreamUrl } from "@/lib/ws";
import type { PriceTick, WatchlistEntry } from "@/lib/types";

type LiveQuote = {
  price: number;
  change: number | null;
  change_pct: number | null;
  polled_at?: number;
};

export default function WatchlistPage() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["watchlist"], queryFn: () => Watchlist.list() });
  const [quotes, setQuotes] = useState<Record<string, LiveQuote>>({});
  const wsRef = useRef<Map<string, WebSocket>>(new Map());
  const [newTicker, setNewTicker] = useState("");
  const [newNotes, setNewNotes] = useState("");

  // Open one WebSocket per watched ticker. Close on unmount or when the
  // ticker leaves the watchlist.
  useEffect(() => {
    const tickers = (list.data ?? []).map((e) => e.ticker);
    const sockets = wsRef.current;

    // Close stale.
    for (const [t, ws] of sockets) {
      if (!tickers.includes(t)) {
        ws.close();
        sockets.delete(t);
      }
    }
    // Open new.
    for (const t of tickers) {
      if (sockets.has(t)) continue;
      const ws = new WebSocket(priceStreamUrl(t));
      ws.onmessage = (e) => {
        try {
          const ev = JSON.parse(e.data) as PriceTick;
          setQuotes((q) => ({
            ...q,
            [ev.ticker]: {
              price: ev.price,
              change: ev.change,
              change_pct: ev.change_pct,
              polled_at: ev.polled_at,
            },
          }));
        } catch { /* ignore */ }
      };
      sockets.set(t, ws);
    }
    return () => {
      for (const ws of sockets.values()) ws.close();
      sockets.clear();
    };
  }, [list.data]);

  const add = useMutation({
    mutationFn: () => Watchlist.add({ ticker: newTicker.trim(), notes: newNotes.trim() || undefined }),
    onSuccess: () => {
      setNewTicker(""); setNewNotes("");
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });
  const remove = useMutation({
    mutationFn: (t: string) => Watchlist.remove(t),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-bold">Watchlist</h1>
        <p className="text-muted text-sm">
          Tickers you care about, with live prices polled every ~30s. Each row
          opens a dedicated WebSocket to the API.
        </p>
      </header>

      <form
        className="card flex flex-wrap gap-3 items-end"
        onSubmit={(e) => {
          e.preventDefault();
          if (newTicker.trim()) add.mutate();
        }}
      >
        <div className="flex-1 min-w-[180px]">
          <label className="label">Ticker</label>
          <input
            className="input w-full"
            value={newTicker}
            onChange={(e) => setNewTicker(e.target.value.toUpperCase())}
            placeholder="NVDA"
          />
        </div>
        <div className="flex-[2] min-w-[240px]">
          <label className="label">Notes (optional)</label>
          <input
            className="input w-full"
            value={newNotes}
            onChange={(e) => setNewNotes(e.target.value)}
            placeholder="Why are you watching this?"
          />
        </div>
        <button className="btn btn-primary" type="submit" disabled={add.isPending || !newTicker.trim()}>
          {add.isPending ? "Adding…" : "Add"}
        </button>
      </form>

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs uppercase text-muted">
              <th className="text-left py-2 px-3 font-medium">Ticker</th>
              <th className="text-right py-2 px-3 font-medium">Price</th>
              <th className="text-right py-2 px-3 font-medium">Change</th>
              <th className="text-right py-2 px-3 font-medium">% Change</th>
              <th className="text-left py-2 px-3 font-medium">Notes</th>
              <th className="text-left py-2 px-3 font-medium">Added</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {list.isLoading && (
              <tr><td colSpan={7} className="py-6 text-center text-muted">Loading…</td></tr>
            )}
            {!list.isLoading && (list.data?.length ?? 0) === 0 && (
              <tr><td colSpan={7} className="py-6 text-center text-muted">
                Empty. Add a ticker above to get started.
              </td></tr>
            )}
            {(list.data ?? []).map((e) => {
              const q = quotes[e.ticker];
              const sign = (q?.change ?? 0) >= 0;
              return (
                <tr key={e.id} className="border-t border-border">
                  <td className="py-2 px-3">
                    <Link href={`/run?ticker=${e.ticker}`} className="font-semibold hover:text-accent">
                      {e.ticker}
                    </Link>
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums">
                    {q ? `$${q.price.toFixed(2)}` : <span className="text-muted">…</span>}
                  </td>
                  <td className={`py-2 px-3 text-right tabular-nums ${q?.change == null ? "" : sign ? "text-success" : "text-danger"}`}>
                    {q?.change != null ? `${sign ? "+" : ""}${q.change.toFixed(2)}` : "—"}
                  </td>
                  <td className={`py-2 px-3 text-right tabular-nums ${q?.change_pct == null ? "" : sign ? "text-success" : "text-danger"}`}>
                    {q?.change_pct != null ? `${sign ? "+" : ""}${q.change_pct.toFixed(2)}%` : "—"}
                  </td>
                  <td className="py-2 px-3 text-muted">{e.notes || ""}</td>
                  <td className="py-2 px-3 text-muted">{e.added_at}</td>
                  <td className="py-2 px-3 text-right">
                    <button
                      className="btn btn-danger text-xs"
                      onClick={() => { if (confirm(`Remove ${e.ticker}?`)) remove.mutate(e.ticker); }}
                    >
                      Remove
                    </button>
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
