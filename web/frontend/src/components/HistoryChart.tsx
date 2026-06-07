import { useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  ReferenceArea, ReferenceLine, ReferenceDot, ResponsiveContainer,
} from "recharts";
import type { Bar, RunLike, Verdict } from "../verdicts";
import { actionColor, actionTint } from "../verdicts";
import { fmtPrice, fmtTime } from "../lib/format";

export interface HistoryChartProps {
  bars: Bar[];
  runs: RunLike[];
  verdicts: Map<string, Verdict>;
  deltaMs: number;
  holdThresholdPct: number;
  nowIso: string;
  selectedRunId: string | null;
  resolution: "1m" | "1h" | "1d";
  rangeStartIso: string;
  rangeEndIso: string;
}

interface ChartRow { t: number; c: number; }

/** Downsample bars to ~3000 rows when the input is large. */
function downsample(bars: Bar[], target = 3000): Bar[] {
  if (bars.length <= target) return bars;
  const stride = Math.ceil(bars.length / target);
  const out: Bar[] = [];
  for (let i = 0; i < bars.length; i += stride) {
    const chunk = bars.slice(i, i + stride);
    const first = chunk[0];
    const last = chunk[chunk.length - 1];
    out.push({
      t: first.t,
      o: first.o,
      h: chunk.reduce((m, b) => Math.max(m, b.h), -Infinity),
      l: chunk.reduce((m, b) => Math.min(m, b.l), Infinity),
      c: last.c,
      v: chunk.reduce((s, b) => s + b.v, 0),
    });
  }
  return out;
}

function isoToMs(iso: string): number {
  return new Date(iso).getTime();
}

export function HistoryChart(props: HistoryChartProps) {
  const { bars, runs, deltaMs, nowIso, selectedRunId, resolution, rangeStartIso, rangeEndIso } = props;
  const scale: "m" | "h" | "d" = resolution === "1m" ? "m" : resolution === "1h" ? "h" : "d";

  const chartData: ChartRow[] = useMemo(
    () => downsample(bars).map((b) => ({ t: isoToMs(b.t), c: b.c })),
    [bars],
  );

  const rangeStartMs = isoToMs(rangeStartIso);
  const rangeEndMs = isoToMs(rangeEndIso);
  const nowMs = isoToMs(nowIso);

  return (
    <div className="w-full h-72" data-testid="history-chart">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
          <CartesianGrid stroke="#e2e8f0" strokeDasharray="2 2" />
          <XAxis
            dataKey="t"
            type="number"
            domain={[rangeStartMs, rangeEndMs]}
            scale="time"
            tickFormatter={(v) => fmtTime(v, scale)}
            tick={{ fontSize: 10, fill: "#64748b" }}
            stroke="#cbd5e1"
          />
          <YAxis
            domain={["auto", "auto"]}
            tickFormatter={fmtPrice}
            width={50}
            tick={{ fontSize: 10, fill: "#64748b" }}
            stroke="#cbd5e1"
          />
          <Line dataKey="c" dot={false} stroke="#475569" strokeWidth={1.5} isAnimationActive={false} />
          {runs.map((run) => {
            const startMs = isoToMs(run.startedAt);
            const endMs = Math.min(startMs + deltaMs, nowMs);
            const isSelected = run.id === selectedRunId;
            return (
              <ReferenceArea
                key={`band-${run.id}`}
                x1={startMs} x2={endMs}
                fill={actionTint(run.decisionAction)}
                fillOpacity={isSelected ? 0.25 : 0.08}
                stroke="none"
                ifOverflow="visible"
              />
            );
          })}
          {runs.map((run) => {
            if (run.decisionTarget == null) return null;
            if (run.decisionAction === "HOLD") return null;
            const startMs = isoToMs(run.startedAt);
            const isSelected = run.id === selectedRunId;
            return (
              <ReferenceLine
                key={`target-${run.id}`}
                y={run.decisionTarget}
                x1={startMs} x2={startMs + deltaMs}
                stroke={actionColor(run.decisionAction)}
                strokeWidth={isSelected ? 3 : 1.5}
                strokeDasharray={isSelected ? undefined : "4 2"}
                ifOverflow="visible"
              />
            );
          })}
          {runs.map((run) => {
            if (run.startPrice == null) return null;
            const startMs = isoToMs(run.startedAt);
            const isSelected = run.id === selectedRunId;
            return (
              <ReferenceDot
                key={`dot-${run.id}`}
                x={startMs} y={run.startPrice}
                r={isSelected ? 8 : 5}
                fill={actionColor(run.decisionAction)}
                stroke="#fff" strokeWidth={1}
                ifOverflow="extendDomain"
              />
            );
          })}
          <ReferenceLine
            x={nowMs}
            stroke="#94a3b8"
            strokeDasharray="3 3"
            label={{ value: "now", position: "insideTopRight", fill: "#94a3b8", fontSize: 10 }}
            ifOverflow="extendDomain"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
