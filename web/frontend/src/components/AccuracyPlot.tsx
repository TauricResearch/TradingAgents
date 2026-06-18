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
    <div className="h-36 md:h-48 border-b border-slate-800" data-testid="accuracy-plot">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
          <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
          <XAxis
            dataKey="delta"
            type="number"
            scale="log"
            domain={xDomain ?? [Math.min(...data.map(p => p.delta)), Math.max(...data.map(p => p.delta))]}
            tickFormatter={fmtDelta}
            tick={{ fontSize: 10, fill: "#64748b" }}
            stroke="#334155"
            minTickGap={24}
          />
          <YAxis
            domain={[0, 1]}
            tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
            width={36}
            tick={{ fontSize: 10, fill: "#64748b" }}
            stroke="#334155"
          />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const p = payload[0].payload as ChartPoint;
              const orig = data.find(d => d.delta === p.delta);
              if (!orig) return null;
              return (
                <div className="glass-panel px-3 py-2 text-xs">
                  <div className="font-medium text-slate-100 mb-1">Δ {fmtDelta(orig.delta)}</div>
                  <div className="text-emerald-400">Accuracy {fmtPct(orig.rightPct! * 100)}</div>
                  <div className="text-slate-500 mt-0.5">{orig.right} right · {orig.wrong} wrong · {orig.unknown} unknown</div>
                </div>
              );
            }}
          />
          <Line
            type="monotone"
            dataKey="rightPct"
            stroke="#38bdf8"
            strokeWidth={2}
            dot={{ r: 3, fill: "#38bdf8", strokeWidth: 0 }}
            isAnimationActive={false}
            name="Accuracy"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
