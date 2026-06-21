import { useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import type { AccuracyPoint } from "../verdicts";
import { fmtDelta } from "../lib/format";

interface SuccessFailurePlotProps {
  data: AccuracyPoint[];
  xDomain?: [number, number];
}

interface ChartPoint {
  delta: number;
  success: number;
  failure: number;
  label: string;
}

export function SuccessFailurePlot({ data, xDomain }: SuccessFailurePlotProps) {
  const chartData: ChartPoint[] = useMemo(
    () => data.map((p) => ({ delta: p.delta, success: p.right, failure: p.wrong, label: fmtDelta(p.delta) })),
    [data],
  );

  if (chartData.length === 0) {
    return (
      <div className="h-40 flex items-center justify-center text-xs text-slate-400">
        No scored data for any delta.
      </div>
    );
  }

  return (
    <div className="h-32 md:h-40 border-b border-slate-800" data-testid="success-failure-plot">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
          <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
          <XAxis
            dataKey="delta"
            type="number"
            scale="log"
            domain={xDomain ?? (data.length > 0
              ? [Math.min(...data.map(p => p.delta)), Math.max(...data.map(p => p.delta))]
              : [0, 1])}
            tickFormatter={fmtDelta}
            tick={{ fontSize: 10, fill: "#64748b" }}
            stroke="#334155"
            minTickGap={24}
          />
          <YAxis
            domain={[0, "auto"]}
            width={28}
            tick={{ fontSize: 10, fill: "#64748b" }}
            stroke="#334155"
            allowDecimals={false}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const p = payload[0].payload as ChartPoint;
              return (
                <div className="glass-panel px-3 py-2 text-xs">
                  <div className="font-medium text-slate-100 mb-1">Δ {fmtDelta(p.delta)}</div>
                  <div className="text-emerald-400">{p.success} succeeded</div>
                  <div className="text-red-400">{p.failure} failed</div>
                </div>
              );
            }}
          />
          <Legend
            wrapperStyle={{ fontSize: 10, color: "#94a3b8" }}
            iconType="plainline"
          />
          <Line
            type="monotone"
            dataKey="success"
            stroke="#10b981"
            strokeWidth={2}
            dot={{ r: 3, fill: "#10b981", strokeWidth: 0 }}
            isAnimationActive={false}
            name="Successes"
          />
          <Line
            type="monotone"
            dataKey="failure"
            stroke="#ef4444"
            strokeWidth={2}
            dot={{ r: 3, fill: "#ef4444", strokeWidth: 0 }}
            isAnimationActive={false}
            name="Failures"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
