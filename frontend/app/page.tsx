"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { DecisionBadge } from "@/components/DecisionBadge";
import { InfoTip } from "@/components/InfoTip";
import { StateBlock } from "@/components/StateBlock";
import { num, pct, signedClass } from "@/lib/format";

export default function DashboardPage() {
  const market = useQuery({ queryKey: ["market"], queryFn: api.market, refetchInterval: 60_000 });
  const watch = useQuery({ queryKey: ["watchlist"], queryFn: api.watchlist });
  const history = useQuery({ queryKey: ["history"], queryFn: () => api.listAnalysis() });

  return (
    <div className="space-y-6">
      <section>
        <h2 className="mb-3 text-sm font-medium tracking-wide text-mist">
          MARKET OVERVIEW
          <InfoTip text="Live NSE index quotes from Yahoo Finance. Regime is a simple NIFTY day-change classifier, not a forecast." />
        </h2>
        {market.isError && (
          <StateBlock title="Unable to retrieve market data." message={(market.error as Error).message} onRetry={() => market.refetch()} />
        )}
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {(market.data?.indices || []).map((idx) => (
            <div key={idx.symbol} className="rounded-xl border border-line bg-ink-800 px-4 py-3">
              <p className="text-xs text-mist">{idx.name}</p>
              <p className="mt-1 font-mono text-2xl tabular">{num(idx.price, 2)}</p>
              <p className={`text-sm tabular ${signedClass(idx.change_percent)}`}>{pct(idx.change_percent)}</p>
            </div>
          ))}
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium tracking-wide text-mist">MY WATCHLIST</h2>
          <Link href="/watchlist" className="text-xs text-gold">
            Manage
          </Link>
        </div>
        {watch.data?.items.length === 0 && (
          <StateBlock title="Watchlist is empty" message="Search a NSE name and pin it. Latest AI decisions appear here after you run analysis." />
        )}
        <div className="grid gap-2">
          {watch.data?.items.map((item) => (
            <Link
              key={item.id}
              href={`/analyze/${item.symbol}`}
              className="grid grid-cols-[1fr_auto_auto] items-center gap-3 rounded-lg border border-line bg-ink-800 px-4 py-3"
            >
              <div>
                <p className="font-medium">{item.symbol.replace(".NS", "")}</p>
                <p className="text-xs text-mist">{item.quote?.name}</p>
              </div>
              <DecisionBadge action={item.last_analysis?.final_decision} size="sm" />
              <span className="text-sm text-mist tabular">
                {item.last_analysis?.confidence != null ? `${Math.round(item.last_analysis.confidence)}%` : "No run"}
              </span>
            </Link>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium tracking-wide text-mist">RECENT AI ANALYSIS</h2>
        <div className="overflow-x-auto rounded-xl border border-line">
          <table className="w-full text-left text-sm">
            <thead className="bg-ink-800 text-mist">
              <tr>
                <th className="px-3 py-2">Symbol</th>
                <th className="px-3 py-2">Decision</th>
                <th className="px-3 py-2">Confidence</th>
                <th className="px-3 py-2">Date</th>
              </tr>
            </thead>
            <tbody>
              {(history.data?.items || []).slice(0, 8).map((row) => (
                <tr key={row.analysis_id} className="border-t border-line">
                  <td className="px-3 py-2">
                    <Link href={`/runs/${row.analysis_id}`} className="text-gold">
                      {row.symbol}
                    </Link>
                  </td>
                  <td className="px-3 py-2">
                    <DecisionBadge action={row.final_decision} size="sm" />
                  </td>
                  <td className="px-3 py-2 tabular">{row.confidence != null ? `${Math.round(row.confidence)}%` : "—"}</td>
                  <td className="px-3 py-2 text-mist">{row.analysis_date}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
