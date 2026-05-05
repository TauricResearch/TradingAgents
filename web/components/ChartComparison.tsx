"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Charts } from "@/lib/api";

const SERIES_COLORS: Record<string, string> = {
  // Ticker is dynamic; benchmarks are fixed so they're stable across runs.
  SPY: "#888",
  QQQ: "#7c4dff",
};

function colorForSeries(name: string, fallback: string): string {
  return SERIES_COLORS[name] ?? fallback;
}

export function ChartComparison({
  ticker,
  tradeDate,
}: {
  ticker: string;
  tradeDate: string;
}) {
  const [daysBack, setDaysBack] = useState(90);
  const [daysForward, setDaysForward] = useState(180);
  const [includeQqq, setIncludeQqq] = useState(true);

  const benchmarks = ["SPY", ...(includeQqq ? ["QQQ"] : [])];

  const q = useQuery({
    queryKey: ["chart", ticker, tradeDate, daysBack, daysForward, benchmarks.join(",")],
    queryFn: () =>
      Charts.comparison({
        ticker,
        trade_date: tradeDate,
        days_back: daysBack,
        days_forward: daysForward,
        benchmarks,
      }),
    enabled: !!ticker && !!tradeDate,
  });

  const data =
    q.data?.points?.map((p) => ({ date: p.date, ...p.values })) ?? [];

  const seriesNames =
    data.length > 0
      ? Object.keys(data[0]).filter((k) => k !== "date")
      : [ticker, ...benchmarks];

  return (
    <div className="card">
      <div className="flex flex-wrap items-end gap-4 mb-3">
        <div>
          <label className="label">Look-back</label>
          <select
            className="input"
            value={daysBack}
            onChange={(e) => setDaysBack(Number(e.target.value))}
          >
            {[30, 60, 90, 180, 365].map((d) => (
              <option key={d} value={d}>
                {d}d
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Look-forward</label>
          <select
            className="input"
            value={daysForward}
            onChange={(e) => setDaysForward(Number(e.target.value))}
          >
            {[30, 60, 90, 180, 365].map((d) => (
              <option key={d} value={d}>
                {d}d
              </option>
            ))}
          </select>
        </div>
        <label className="flex items-center gap-2 text-sm pb-1.5">
          <input
            type="checkbox"
            checked={includeQqq}
            onChange={(e) => setIncludeQqq(e.target.checked)}
          />
          Include QQQ
        </label>
        <div className="text-xs text-muted ml-auto pb-1.5">
          Indexed to <strong>100</strong> at {tradeDate}
        </div>
      </div>

      <div className="h-72">
        {q.isLoading ? (
          <div className="text-sm text-muted">Loading prices…</div>
        ) : data.length === 0 ? (
          <div className="text-sm text-muted">No price data available.</div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="rgb(var(--border))" strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                stroke="rgb(var(--muted))"
                tick={{ fontSize: 11 }}
                minTickGap={32}
              />
              <YAxis stroke="rgb(var(--muted))" tick={{ fontSize: 11 }} domain={["auto", "auto"]} />
              <Tooltip
                contentStyle={{
                  background: "rgb(var(--surface))",
                  border: "1px solid rgb(var(--border))",
                  borderRadius: 6,
                  fontSize: 12,
                }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <ReferenceLine
                x={tradeDate}
                stroke="rgb(var(--accent))"
                strokeDasharray="4 4"
                label={{ value: "trade date", fontSize: 10, fill: "rgb(var(--muted))", position: "top" }}
              />
              {seriesNames.map((s, i) => (
                <Line
                  key={s}
                  type="monotone"
                  dataKey={s}
                  stroke={colorForSeries(
                    s,
                    s === ticker ? "rgb(var(--accent))" : `hsl(${i * 67}, 70%, 55%)`,
                  )}
                  dot={false}
                  strokeWidth={s === ticker ? 2 : 1.25}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {q.data?.realised_returns && q.data.realised_returns.length > 0 && (
        <div className="mt-4">
          <div className="font-semibold text-sm mb-2">
            Realised return windows (vs SPY, post trade-date)
          </div>
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-muted">
              <tr>
                {Object.keys(q.data.realised_returns[0]).map((k) => (
                  <th key={k} className="text-left py-1 pr-3 font-medium">
                    {k}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {q.data.realised_returns.map((r, i) => (
                <tr key={i} className="border-t border-border">
                  {Object.values(r).map((v, j) => (
                    <td key={j} className="py-1 pr-3">
                      {v as string}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
