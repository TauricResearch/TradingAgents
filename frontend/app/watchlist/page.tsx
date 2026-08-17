"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { DecisionBadge } from "@/components/DecisionBadge";
import { InfoTip } from "@/components/InfoTip";
import { StateBlock } from "@/components/StateBlock";
import { api } from "@/lib/api";
import { inr, pct, signedClass } from "@/lib/format";

export default function WatchlistPage() {
  const qc = useQueryClient();
  const [symbol, setSymbol] = useState("RELIANCE.NS");
  const list = useQuery({ queryKey: ["watchlist"], queryFn: api.watchlist });
  const add = useMutation({
    mutationFn: () => api.addWatch(symbol),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.removeWatch(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">
        Watchlist
        <InfoTip text="Local list stored in the terminal database. AI signal is the latest completed run for that symbol." />
      </h1>
      <div className="flex gap-2">
        <input value={symbol} onChange={(e) => setSymbol(e.target.value)} className="rounded-md border border-line bg-ink-800 px-3 py-2 text-sm" />
        <button onClick={() => add.mutate()} className="rounded-md bg-gold px-3 py-2 text-sm text-ink-950">
          Add
        </button>
      </div>
      {list.data?.items.length === 0 && <StateBlock title="Nothing pinned" message="Add RELIANCE.NS or any NSE ticker to start." />}
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full text-left text-sm">
          <thead className="bg-ink-800 text-mist">
            <tr>
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2">Price</th>
              <th className="px-3 py-2">Change</th>
              <th className="px-3 py-2">AI Signal</th>
              <th className="px-3 py-2">Confidence</th>
              <th className="px-3 py-2">Last Analysis</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {list.data?.items.map((item) => (
              <tr key={item.id} className="border-t border-line">
                <td className="px-3 py-2">
                  <Link className="text-gold" href={`/analyze/${item.symbol}`}>
                    {item.symbol}
                  </Link>
                </td>
                <td className="px-3 py-2 tabular">{inr(item.quote?.price ?? null)}</td>
                <td className={`px-3 py-2 tabular ${signedClass(item.quote?.change_percent)}`}>{pct(item.quote?.change_percent)}</td>
                <td className="px-3 py-2">
                  <DecisionBadge action={item.last_analysis?.final_decision} size="sm" />
                </td>
                <td className="px-3 py-2 tabular">
                  {item.last_analysis?.confidence != null ? `${Math.round(item.last_analysis.confidence)}%` : "—"}
                </td>
                <td className="px-3 py-2 text-mist">{item.last_analysis?.analysis_date || "—"}</td>
                <td className="px-3 py-2">
                  <div className="flex gap-2">
                    <Link href={`/analyze/${item.symbol}`} className="text-gold">
                      Analyze
                    </Link>
                    <button className="text-loss" onClick={() => remove.mutate(item.id)}>
                      Remove
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
