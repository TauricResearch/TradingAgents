"use client";

import { Bar, CartesianGrid, Cell, ComposedChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { InfoTip } from "./InfoTip";
import { StateBlock } from "./StateBlock";

const RANGES = ["1D", "5D", "1M", "3M", "6M", "1Y", "5Y"];

export function PriceChart({ symbol }: { symbol: string }) {
  const [range, setRange] = useState("6M");
  const query = useQuery({
    queryKey: ["history", symbol, range],
    queryFn: () => api.history(symbol, range),
  });

  return (
    <section className="rounded-xl border border-line bg-ink-800 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-medium">
          Price
          <InfoTip text="Yahoo Finance candles for the selected NSE/BSE symbol. Markers are added only when an AI run provided real levels." />
        </h3>
        <div className="flex gap-1">
          {RANGES.map((item) => (
            <button
              key={item}
              onClick={() => setRange(item)}
              className={`rounded px-2 py-1 text-xs ${range === item ? "bg-ink-600 text-white" : "text-mist"}`}
            >
              {item}
            </button>
          ))}
        </div>
      </div>
      {query.isLoading && <p className="text-sm text-mist">Loading chart…</p>}
      {query.isError && (
        <StateBlock title="Unable to retrieve market data." message={(query.error as Error).message} onRetry={() => query.refetch()} />
      )}
      {query.data && query.data.length === 0 && (
        <StateBlock title="No candles" message="The data vendor returned no rows for this range." onRetry={() => query.refetch()} />
      )}
      {query.data && query.data.length > 0 && (
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={query.data}>
              <CartesianGrid stroke="#1d2a38" vertical={false} />
              <XAxis dataKey="time" hide />
              <YAxis domain={["auto", "auto"]} stroke="#9bb0c3" tick={{ fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: "#101820", border: "1px solid #243140" }}
                labelFormatter={(label) => String(label).slice(0, 16)}
              />
              <Bar dataKey="close" fill="#c8a15a" maxBarSize={6}>
                {query.data.map((row, i) => (
                  <Cell key={i} fill={row.close >= row.open ? "#3dd68c" : "#ef6b6b"} />
                ))}
              </Bar>
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
