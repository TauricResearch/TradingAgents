"use client";

import { useMemo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import Panel from "./ui/Panel";

function generatePriceData() {
  const data = [];
  let price = 870;
  for (let i = 0; i < 60; i++) {
    price += (Math.random() - 0.47) * 8;
    data.push({
      time: `${Math.floor(i / 4) + 9}:${String((i % 4) * 15).padStart(2, "0")}`,
      price: Math.round(price * 100) / 100,
    });
  }
  return data;
}

const stats = [
  { label: "Current Price", value: "$892.45", type: "up" as const },
  { label: "Day Change", value: "+$27.83 (+3.21%)", type: "up" as const },
  { label: "Volume", value: "48.2M", type: "neutral" as const },
  { label: "RSI (14)", value: "67.4", type: "neutral" as const },
  { label: "MACD Signal", value: "Bullish Cross", type: "up" as const },
  { label: "50 SMA", value: "$842.10", type: "up" as const },
  { label: "200 SMA", value: "$756.30", type: "up" as const },
  { label: "ATR (14)", value: "$18.92", type: "neutral" as const },
  { label: "Bollinger", value: "Upper Band", type: "down" as const },
];

const typeColors = {
  up: "text-green border-l-green",
  down: "text-red border-l-red",
  neutral: "text-cyan border-l-cyan",
};

export default function MarketOverview() {
  const data = useMemo(() => generatePriceData(), []);

  return (
    <Panel
      title="Market Overview"
      badge="Live"
      badgeVariant="live"
      className="col-span-2"
      delay={0.15}
    >
      <div className="grid grid-cols-[1fr_280px] gap-4">
        <div className="h-[200px] bg-bg-elevated rounded-lg overflow-hidden">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={data}
              margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
            >
              <defs>
                <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#4ecdc4" stopOpacity={0.2} />
                  <stop offset="100%" stopColor="#4ecdc4" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="time"
                tick={{ fill: "#5a5853", fontSize: 10 }}
                axisLine={{ stroke: "rgba(255,255,255,0.04)" }}
                tickLine={false}
                interval={9}
              />
              <YAxis
                domain={["dataMin - 5", "dataMax + 5"]}
                tick={{ fill: "#5a5853", fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v: number) => `$${v.toFixed(0)}`}
                width={48}
              />
              <Tooltip
                contentStyle={{
                  background: "#14161d",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 8,
                  fontSize: 11,
                  color: "#e8e6e1",
                }}
                labelStyle={{ color: "#8a8780" }}
                formatter={(value) => [`$${Number(value).toFixed(2)}`, "Price"]}
              />
              <Area
                type="monotone"
                dataKey="price"
                stroke="#4ecdc4"
                strokeWidth={1.5}
                fill="url(#priceGrad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="flex flex-col gap-2 overflow-y-auto max-h-[200px]">
          {stats.map((s) => (
            <div
              key={s.label}
              className={`flex justify-between items-center px-3 py-2 bg-bg-elevated rounded border-l-2 ${typeColors[s.type]}`}
            >
              <span className="text-[10px] text-text-tertiary uppercase tracking-[1px]">
                {s.label}
              </span>
              <span className={`font-display font-semibold text-[13px] ${typeColors[s.type].split(" ")[0]}`}>
                {s.value}
              </span>
            </div>
          ))}
        </div>
      </div>
    </Panel>
  );
}
