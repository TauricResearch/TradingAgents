import { useMemo } from "react";
import {
  LineChart, Line, BarChart, Bar as BarRect, Cell, Customized,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceArea, ReferenceLine, ReferenceDot, ResponsiveContainer,
} from "recharts";
import type { Bar, RunLike, Verdict } from "../verdicts";
import { actionColor, actionTint } from "../verdicts";
import { fmtPrice, fmtTime, fmtVolume } from "../lib/format";
import type { CandleResolution } from "../lib/resolution";

export interface HistoryChartProps {
  bars: Bar[];
  runs: RunLike[];
  verdicts: Map<string, Verdict>;
  deltaMs: number;
  holdThresholdPct: number;
  nowIso: string;
  selectedRunId: string | null;
  resolution: Exclude<CandleResolution, "auto">;
  rangeStartIso: string;
  rangeEndIso: string;
}

interface ChartRow { t: number; o: number; h: number; l: number; c: number; v: number; avg: number; std: number; }

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

const CANDLE_WIDTH = 6;
const UP_COLOR = "#16a34a";   // green-600
const DOWN_COLOR = "#dc2626"; // red-600

/**
 * Custom recharts renderer that draws one OHLC candle per data point.
 * Recharts has no built-in candlestick primitive, so we read the chart's
 * x/y scales (passed in by <Customized>) and emit a wick line + a body
 * rect per row. The body colour follows the close-vs-open direction by
 * default; an optional `colors` array overrides per-bar (used for
 * run-context tinting, mirroring the volume bars).
 */
function CandleRenderer(props: {
  data?: ChartRow[];
  xAxisMap?: Record<string, { scale: (v: number) => number }>;
  yAxisMap?: Record<string, { scale: (v: number) => number }>;
  colors?: Array<{ action: string | null; wick: string; body: string } | null>;
}) {
  const { data, xAxisMap, yAxisMap, colors } = props;
  if (!data || !xAxisMap || !yAxisMap) return null;
  const xAxis = Object.values(xAxisMap)[0];
  const yAxis = Object.values(yAxisMap)[0];
  if (!xAxis?.scale || !yAxis?.scale) return null;

  // Body width: 6px at sparse densities, scaled down to (avgGap * 0.7)
  // when candles get dense. The 0.7 factor leaves a 30% gap between
  // adjacent bodies so they never overlap into a solid block.
  let bodyWidth = CANDLE_WIDTH;
  if (data.length > 1) {
    let totalGap = 0;
    let count = 0;
    for (let i = 0; i < data.length - 1; i++) {
      const t1 = data[i].t;
      const t2 = data[i + 1].t;
      if (typeof t1 === "number" && typeof t2 === "number") {
        totalGap += Math.abs(xAxis.scale(t2) - xAxis.scale(t1));
        count++;
      }
    }
    if (count > 0) {
      const avgGap = totalGap / count;
      bodyWidth = Math.max(1, Math.min(CANDLE_WIDTH, avgGap * 0.7));
    }
  }

  return (
    <g>
      {data.map((row, i) => {
        const x = xAxis.scale(row.t);
        const yHigh = yAxis.scale(row.h);
        const yLow = yAxis.scale(row.l);
        const yOpen = yAxis.scale(row.o);
        const yClose = yAxis.scale(row.c);
        const override = colors?.[i] ?? null;
        const isUp = row.c >= row.o;
        const wickColor = override ? override.wick : (isUp ? UP_COLOR : DOWN_COLOR);

        // Body fill/stroke: under a run context, hollow-out the body when
        // the day's direction is the opposite of what the run expected
        // (BUY expects up → down day = hollow; SELL expects down → up
        // day = hollow). HOLD has no expectation, always solid. Outside
        // any run, keep the standard up/down solid green/red.
        let bodyFill: string;
        let bodyStroke: string | undefined;
        let bodyStrokeWidth: number | undefined;
        if (override) {
          const c = override.body;
          if (override.action === "HOLD" || !override.action) {
            bodyFill = c;
          } else {
            const expectedUp = override.action === "BUY";
            if (isUp === expectedUp) {
              bodyFill = c;
            } else {
              bodyFill = "none";
              bodyStroke = c;
              bodyStrokeWidth = 1;
            }
          }
        } else {
          bodyFill = isUp ? UP_COLOR : DOWN_COLOR;
        }

        return (
          <g key={i}>
            <line
              x1={x} x2={x}
              y1={yHigh} y2={yLow}
              stroke={wickColor} strokeWidth={1}
            />
            <rect
              x={x - bodyWidth / 2}
              y={Math.min(yOpen, yClose)}
              width={bodyWidth}
              height={Math.max(1, Math.abs(yClose - yOpen))}
              fill={bodyFill}
              stroke={bodyStroke}
              strokeWidth={bodyStrokeWidth}
            />
          </g>
        );
      })}
    </g>
  );
}

export function HistoryChart(props: HistoryChartProps) {
  const { bars, runs, deltaMs, nowIso, selectedRunId, resolution, rangeStartIso, rangeEndIso } = props;
  const scale: "m" | "h" | "d" =
    resolution === "1d" || resolution === "1w" ? "d"
    : (resolution === "1h" || resolution === "4h") ? "h"
    : "m";

  const chartData: ChartRow[] = useMemo(
    () =>
      downsample(bars).map((b) => {
        // Typical price + population stddev of the bar's OHLC quartet.
        // "The day or other delta time" the user asked for is exactly
        // what one bar already represents, so the per-bar OHLC summary
        // is the natural local-window stat.
        const avg = (b.o + b.h + b.l + b.c) / 4;
        const variance =
          ((b.o - avg) ** 2 + (b.h - avg) ** 2 + (b.l - avg) ** 2 + (b.c - avg) ** 2) / 4;
        const std = Math.sqrt(variance);
        return { t: isoToMs(b.t), o: b.o, h: b.h, l: b.l, c: b.c, v: b.v, avg, std };
      }),
    [bars],
  );

  // Auto-scale the price y-axis to the candle highs/lows (with a small
  // pad so edge candles aren't clipped). Recharts' `["auto","auto"]`
  // would do this, but with <Customized> rendering (no <Line>) the
  // built-in auto-scale has no dataKey to anchor to, so we drive it
  // explicitly here.
  const yDomain: [number, number] = useMemo(() => {
    if (chartData.length === 0) return [0, 1];
    let min = Infinity, max = -Infinity;
    for (const row of chartData) {
      if (row.l < min) min = row.l;
      if (row.h > max) max = row.h;
    }
    const pad = (max - min) * 0.05 || 1;
    return [min - pad, max + pad];
  }, [chartData]);

  const rangeStartMs = isoToMs(rangeStartIso);
  const rangeEndMs = isoToMs(rangeEndIso);
  const nowMs = isoToMs(nowIso);

  // Per-bar tint: color by the action of the most recently started run
  // whose [T, T+Δ] window contains this bar. Neutral slate otherwise.
  // Multiple overlapping runs → newest startedAt wins.
  const barColors = useMemo(
    () =>
      chartData.map((row) => {
        const t = row.t;
        let active: RunLike | null = null;
        for (const run of runs) {
          const startMs = isoToMs(run.startedAt);
          const endMs = Math.min(startMs + deltaMs, nowMs);
          if (t >= startMs && t <= endMs) {
            if (active == null || isoToMs(run.startedAt) > isoToMs(active.startedAt)) {
              active = run;
            }
          }
        }
        if (active) return { fill: actionColor(active.decisionAction), opacity: 0.7 };
        return { fill: "#94a3b8", opacity: 0.5 };
      }),
    [chartData, runs, deltaMs, nowMs],
  );

  // Same active-run lookup for the candle renderer: when a candle falls
  // inside a run's verdict window, override the wick + body fill with
  // that run's action colour. Outside any run the candle keeps its
  // standard up/down green/red.
  const candleColors = useMemo(
    () =>
      chartData.map((row) => {
        const t = row.t;
        let active: RunLike | null = null;
        for (const run of runs) {
          const startMs = isoToMs(run.startedAt);
          const endMs = Math.min(startMs + deltaMs, nowMs);
          if (t >= startMs && t <= endMs) {
            if (active == null || isoToMs(run.startedAt) > isoToMs(active.startedAt)) {
              active = run;
            }
          }
        }
        if (!active) return null;
        const c = actionColor(active.decisionAction);
        return { action: active.decisionAction, wick: c, body: c };
      }),
    [chartData, runs, deltaMs, nowMs],
  );

  // <Customized> only forwards recharts' own props to its component, so
  // we wrap CandleRenderer to inject our per-bar colour overrides.
  const BoundCandleRenderer = useMemo(
    () =>
      (props: {
        data?: ChartRow[];
        xAxisMap?: Record<string, { scale: (v: number) => number }>;
        yAxisMap?: Record<string, { scale: (v: number) => number }>;
      }) => <CandleRenderer {...props} colors={candleColors} />,
    [candleColors],
  );

  return (
    <div className="w-full h-72" data-testid="history-chart">
      <div className="flex flex-col h-full">
        <div className="flex-1 min-h-0">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
              <CartesianGrid stroke="#e2e8f0" strokeDasharray="2 2" />
              <XAxis
                dataKey="t"
                type="number"
                domain={[rangeStartMs, rangeEndMs]}
                scale="time"
                hide
              />
              <YAxis
                domain={yDomain}
                tickFormatter={fmtPrice}
                width={50}
                tick={{ fontSize: 10, fill: "#64748b" }}
                stroke="#cbd5e1"
              />
              <Customized component={BoundCandleRenderer} />
              {/* Hidden line — gives the <Tooltip> a real series to
                  source its payload from. <Customized> alone doesn't
                  register as a series, so without this the tooltip
                  would never fire on hover. */}
              <Line
                dataKey="c"
                stroke="none"
                strokeWidth={0}
                dot={false}
                isAnimationActive={false}
                legendType="none"
                name="price"
              />
              <Tooltip
                cursor={{ stroke: "#94a3b8", strokeDasharray: "3 3" }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const p = payload[0].payload as ChartRow;
                  return (
                    <div
                      className="bg-white border border-slate-200 rounded shadow-sm px-2 py-1 text-xs"
                      data-testid="history-tooltip"
                    >
                      <div className="text-slate-500">{fmtTime(p.t, scale)}</div>
                      <div className="font-medium text-slate-900">${fmtPrice(p.c)}</div>
                      <div className="text-slate-400 mt-0.5">
                        O {fmtPrice(p.o)} · H {fmtPrice(p.h)} · L {fmtPrice(p.l)}
                      </div>
                      <div className="text-slate-400">
                        Avg {fmtPrice(p.avg)} · σ {fmtPrice(p.std)}
                      </div>
                      <div className="text-slate-400">Vol {fmtVolume(p.v)}</div>
                    </div>
                  );
                }}
              />
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
        <div className="h-14 shrink-0 border-t border-slate-100">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 8, left: 8 }}>
              <CartesianGrid stroke="#e2e8f0" strokeDasharray="2 2" vertical={false} />
              <XAxis
                dataKey="t"
                type="number"
                domain={[rangeStartMs, rangeEndMs]}
                scale="time"
                tickFormatter={(v) => fmtTime(v, scale)}
                tick={{ fontSize: 10, fill: "#64748b" }}
                stroke="#cbd5e1"
                minTickGap={32}
              />
              <YAxis hide width={50} />
              <Tooltip
                cursor={{ fill: "#f1f5f9" }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const p = payload[0].payload as ChartRow;
                  return (
                    <div
                      className="bg-white border border-slate-200 rounded shadow-sm px-2 py-1 text-xs"
                      data-testid="volume-tooltip"
                    >
                      <div className="text-slate-500">{fmtTime(p.t, scale)}</div>
                      <div className="font-medium text-slate-900">Vol {fmtVolume(p.v)}</div>
                    </div>
                  );
                }}
              />
              <BarRect dataKey="v" isAnimationActive={false}>
                {chartData.map((_, i) => (
                  <Cell key={i} fill={barColors[i].fill} fillOpacity={barColors[i].opacity} />
                ))}
              </BarRect>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
