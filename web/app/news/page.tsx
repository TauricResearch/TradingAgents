"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { News } from "@/lib/api";

function fmtTime(iso?: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return String(iso);
  }
}

export default function NewsPage() {
  const [tickerFilter, setTickerFilter] = useState("");
  const tickers = tickerFilter
    .split(",")
    .map((t) => t.trim().toUpperCase())
    .filter(Boolean);

  const q = useQuery({
    queryKey: ["news-feed", tickers.join(",")],
    queryFn: () => News.feed({ tickers: tickers.length ? tickers : undefined, limit: 100 }),
    refetchInterval: 5 * 60_000, // 5 min, matches server-side cache TTL
  });

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-bold">News</h1>
        <p className="text-muted text-sm">
          Aggregated headlines for your watchlist (or a custom list). Cached
          for 5 minutes per ticker on the server side.
        </p>
      </header>

      <div className="card flex gap-3 items-end">
        <div className="flex-1">
          <label className="label">Filter by ticker (comma-separated; empty = watchlist)</label>
          <input
            className="input w-full"
            value={tickerFilter}
            onChange={(e) => setTickerFilter(e.target.value)}
            placeholder="NVDA, AAPL, MSFT"
          />
        </div>
        <button className="btn" onClick={() => q.refetch()} disabled={q.isFetching}>
          {q.isFetching ? "Refreshing…" : "↻ Refresh"}
        </button>
      </div>

      <div className="space-y-2">
        {q.isLoading && <div className="text-muted text-sm">Loading…</div>}
        {!q.isLoading && (q.data?.length ?? 0) === 0 && (
          <div className="card text-sm text-muted">
            No articles yet. Add tickers to your watchlist first, or specify
            tickers above.
          </div>
        )}
        {(q.data ?? []).map((n, i) => (
          <article key={i} className="card hover:border-accent transition-colors">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 text-xs text-muted">
                  <span className="pill bg-accent/15 text-accent">{n.ticker}</span>
                  <span>{n.publisher}</span>
                  <span>· {fmtTime(n.published_at)}</span>
                </div>
                <h3 className="font-semibold mt-1">
                  {n.link ? (
                    <a href={n.link} target="_blank" rel="noopener noreferrer" className="hover:text-accent">
                      {n.title}
                    </a>
                  ) : n.title}
                </h3>
                {n.summary && <p className="text-sm text-muted mt-1 line-clamp-3">{n.summary}</p>}
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
