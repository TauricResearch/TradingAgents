import { useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import type { AccuracyPoint } from "../verdicts";
import { fmtDelta } from "../lib/format";

interface SuccessFailurePlotProps {
  data: AccuracyPoint[];
}

interface ChartPoint {
  delta: number;
  success: number;
  failure: number;
  label: string;
}

export function SuccessFailurePlot({ data }: SuccessFailurePlotProps) {
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
    <div className="h-40 border-b border-slate-200" data-testid="success-failure-plot">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
          <CartesianGrid stroke="#e2e8f0" strokeDasharray="2 2" />
          <XAxis
            dataKey="delta"
            type="number"
            scale="log"
            domain={[Math.min(...data.map(p => p.delta)), Math.max(...data.map(p => p.delta))]}
            tickFormatter={fmtDelta}
            tick={{ fontSize: 10, fill: "#64748b" }}
            stroke="#cbd5e1"
            minTickGap={24}
          />
          <YAxis
            domain={[0, "auto"]}
            width={28}
            tick={{ fontSize: 10, fill: "#64748b" }}
            stroke="#cbd5e1"
            allowDecimals={false}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const p = payload[0].payload as ChartPoint;
              return (
                <div className="bg-white border border-slate-200 rounded shadow-sm px-2 py-1 text-xs">
                  <div className="font-medium text-slate-900">Δ {fmtDelta(p.delta)}</div>
                  <div className="text-green-600">{p.success} succeeded</div>
                  <div className="text-red-600">{p.failure} failed</div>
                </div>
              );
            }}
          />
          <Legend
            wrapperStyle={{ fontSize: 10, color: "#64748b" }}
            iconType="plainline"
          />
          <Line
            type="monotone"
            dataKey="success"
            stroke="#16a34a"
            strokeWidth={2}
            dot={{ r: 3, fill: "#16a34a", strokeWidth: 0 }}
            isAnimationActive={false}
            name="Successes"
          />
          <Line
            type="monotone"
            dataKey="failure"
            stroke="#dc2626"
            strokeWidth={2}
            dot={{ r: 3, fill: "#dc2626", strokeWidth: 0 }}
            isAnimationActive={false}
            name="Failures"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
