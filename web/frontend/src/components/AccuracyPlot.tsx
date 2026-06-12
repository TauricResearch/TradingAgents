import { useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import type { AccuracyPoint } from "../verdicts";
import { fmtDelta, fmtPct } from "../lib/format";

interface AccuracyPlotProps {
  data: AccuracyPoint[];
  xDomain?: [number, number];
}

interface ChartPoint {
  delta: number;
  rightPct: number;
  label: string;
}

export function AccuracyPlot({ data, xDomain }: AccuracyPlotProps) {
  const chartData: ChartPoint[] = useMemo(
    () => data.map((p) => ({ delta: p.delta, rightPct: p.rightPct ?? 0, label: fmtDelta(p.delta) })),
    [data],
  );

  if (chartData.length === 0) {
    return (
      <div className="h-48 flex items-center justify-center text-xs text-slate-400">
        No scored data for any delta.
      </div>
    );
  }

  return (
    <div className="h-48 border-b border-slate-200" data-testid="accuracy-plot">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
          <CartesianGrid stroke="#e2e8f0" strokeDasharray="2 2" />
          <XAxis
            dataKey="delta"
            type="number"
            scale="log"
            domain={xDomain ?? [Math.min(...data.map(p => p.delta)), Math.max(...data.map(p => p.delta))]}
            tickFormatter={fmtDelta}
            tick={{ fontSize: 10, fill: "#64748b" }}
            stroke="#cbd5e1"
            minTickGap={24}
          />
          <YAxis
            domain={[0, 1]}
            tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
            width={36}
            tick={{ fontSize: 10, fill: "#64748b" }}
            stroke="#cbd5e1"
          />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const p = payload[0].payload as ChartPoint;
              const orig = data.find(d => d.delta === p.delta);
              if (!orig) return null;
              return (
                <div className="bg-white border border-slate-200 rounded shadow-sm px-2 py-1 text-xs">
                  <div className="font-medium text-slate-900">Δ {fmtDelta(orig.delta)}</div>
                  <div className="text-slate-700">Accuracy {fmtPct(orig.rightPct! * 100)}</div>
                  <div className="text-slate-500">{orig.right} right · {orig.wrong} wrong · {orig.unknown} unknown</div>
                </div>
              );
            }}
          />
          <Line
            type="monotone"
            dataKey="rightPct"
            stroke="#2563eb"
            strokeWidth={2}
            dot={{ r: 3, fill: "#2563eb", strokeWidth: 0 }}
            isAnimationActive={false}
            name="Accuracy"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
