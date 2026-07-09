/** Equity curve: area series colored by outcome, optional Monte Carlo
 * band annotations. The backtest curve is bar-indexed (no wall-clock
 * timestamps), so the x-axis is bar count, rendered honestly as such. */
import {
  AreaSeries,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect } from "react";

import { chartColors, useLightweightChart } from "./useLightweightChart";
import { useUiStore } from "@/stores/ui";
import { toDrawdown } from "./transform";
import { fmtPrice } from "@/lib/format";

export function EquityCurve({
  curve,
  monteCarlo,
  showDrawdown = false,
  height = 220,
}: {
  showDrawdown?: boolean;
  curve: number[];
  monteCarlo?: {
    final_equity_p5: number;
    final_equity_p50: number;
    final_equity_p95: number;
    prob_loss: number;
  } | null;
  height?: number;
}) {
  const { containerRef, chartRef } = useLightweightChart((chart) => {
    chart.applyOptions({
      timeScale: { visible: false },
      handleScroll: false,
      handleScale: false,
    });
  });
  const theme = useUiStore((s) => s.theme); // series colors re-resolve on flip

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || curve.length < 2) return;
    const colors = chartColors();
    const first = curve[0]!;
    const last = curve[curve.length - 1]!;
    const up = last >= first;
    const series = chart.addSeries(AreaSeries, {
      lineColor: up ? colors.bull : colors.bear,
      topColor: up ? "rgba(63,185,80,0.2)" : "rgba(248,81,73,0.2)",
      bottomColor: "rgba(0,0,0,0)",
      lineWidth: 2,
      priceLineVisible: false,
    });
    // bar-indexed: synthesize a daily spacing purely for rendering
    series.setData(
      curve.map((value, i) => ({
        time: (86400 * (i + 1)) as UTCTimestamp,
        value,
      })),
    );
    let drawdownSeries: ReturnType<typeof chart.addSeries> | null = null;
    if (showDrawdown) {
      drawdownSeries = chart.addSeries(
        AreaSeries,
        {
          lineColor: colors.bear,
          topColor: "rgba(0,0,0,0)",
          bottomColor: "rgba(248,81,73,0.25)",
          lineWidth: 1,
          priceLineVisible: false,
          priceFormat: { type: "percent" },
        },
        1, // own pane under the equity curve
      );
      drawdownSeries.setData(
        toDrawdown(curve).map((value, i) => ({
          time: (86400 * (i + 1)) as UTCTimestamp,
          value: value * 100,
        })),
      );
    }
    chart.timeScale().fitContent();
    return () => {
      chart.removeSeries(series);
      if (drawdownSeries) chart.removeSeries(drawdownSeries);
    };
  }, [curve, showDrawdown, theme, chartRef]);

  return (
    <div>
      <div
        ref={containerRef}
        style={{ height }}
        role="img"
        aria-label={`equity from ${fmtPrice(curve[0])} to ${fmtPrice(curve[curve.length - 1])} over ${curve.length} bars`}
        data-testid="equity-curve"
      />
      {monteCarlo && (
        <div className="mt-1 flex flex-wrap gap-x-4 text-xs text-fg-muted tabular">
          <span>
            MC p5 <span className="text-bear">{fmtPrice(monteCarlo.final_equity_p5, 0)}</span>
          </span>
          <span>p50 {fmtPrice(monteCarlo.final_equity_p50, 0)}</span>
          <span>
            p95 <span className="text-bull">{fmtPrice(monteCarlo.final_equity_p95, 0)}</span>
          </span>
          <span>P(loss) {(monteCarlo.prob_loss * 100).toFixed(1)}%</span>
        </div>
      )}
    </div>
  );
}
