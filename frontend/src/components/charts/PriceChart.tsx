/** Price chart: candles / heikin-ashi / line / area, recommendation
 * levels as price lines (entry solid accent, stop dashed bear, TPs
 * dotted bull with size fractions), trade markers from the journal,
 * and a live last-price update from the ticker store. */
import {
  AreaSeries,
  CandlestickSeries,
  LineSeries,
  createSeriesMarkers,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

import { chartColors, useLightweightChart } from "./useLightweightChart";
import { toHeikinAshi } from "./transform";
import type { Bar, Recommendation } from "@/lib/api/types";
import { directionOf } from "@/lib/format";
import { useTickerStore } from "@/stores/ticker";

export type SeriesStyle = "candles" | "heikin-ashi" | "line" | "area";

export interface TradeMarker {
  time: number;
  direction: string | null;
  label: string;
}

export function PriceChart({
  bars,
  style = "candles",
  recommendation,
  markers = [],
  liveSymbol,
  height = 420,
}: {
  bars: Bar[];
  style?: SeriesStyle;
  recommendation?: Recommendation | null;
  markers?: TradeMarker[];
  /** ticker-store symbol for live last-price updates (e.g. "BTC-USD") */
  liveSymbol?: string;
  height?: number;
}) {
  const seriesRef = useRef<ISeriesApi<"Candlestick" | "Line" | "Area"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const styleRef = useRef(style);
  styleRef.current = style;

  const { containerRef, chartRef } = useLightweightChart(() => undefined);

  // (re)build the series when style changes; refill data when bars change
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    if (seriesRef.current) {
      markersRef.current?.detach();
      markersRef.current = null;
      chart.removeSeries(seriesRef.current);
      seriesRef.current = null;
    }
    const colors = chartColors();
    const data = style === "heikin-ashi" ? toHeikinAshi(bars) : bars;

    if (style === "candles" || style === "heikin-ashi") {
      const series = chart.addSeries(CandlestickSeries, {
        upColor: colors.bull,
        downColor: colors.bear,
        borderUpColor: colors.bull,
        borderDownColor: colors.bear,
        wickUpColor: colors.bull,
        wickDownColor: colors.bear,
      });
      series.setData(
        data.map((b) => ({
          time: b.time as UTCTimestamp,
          open: b.open,
          high: b.high,
          low: b.low,
          close: b.close,
        })),
      );
      seriesRef.current = series;
    } else if (style === "line") {
      const series = chart.addSeries(LineSeries, {
        color: colors.accent,
        lineWidth: 2,
      });
      series.setData(
        data.map((b) => ({ time: b.time as UTCTimestamp, value: b.close })),
      );
      seriesRef.current = series;
    } else {
      const series = chart.addSeries(AreaSeries, {
        lineColor: colors.accent,
        topColor: "rgba(121,192,255,0.25)",
        bottomColor: "rgba(121,192,255,0.02)",
        lineWidth: 2,
      });
      series.setData(
        data.map((b) => ({ time: b.time as UTCTimestamp, value: b.close })),
      );
      seriesRef.current = series;
    }
    chart.timeScale().fitContent();
  }, [bars, style, chartRef]);

  // recommendation levels as price lines
  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    const colors = chartColors();
    const lines: ReturnType<typeof series.createPriceLine>[] = [];
    if (recommendation && !recommendation.status && recommendation.entry_price) {
      lines.push(
        series.createPriceLine({
          price: recommendation.entry_price,
          color: colors.accent,
          lineWidth: 1,
          lineStyle: 0,
          title: "ENTRY",
        }),
      );
      if (recommendation.stop_loss) {
        lines.push(
          series.createPriceLine({
            price: recommendation.stop_loss,
            color: colors.bear,
            lineWidth: 1,
            lineStyle: 1,
            title: "STOP",
          }),
        );
      }
      (recommendation.take_profits ?? []).forEach((tp, i) => {
        lines.push(
          series.createPriceLine({
            price: tp.price,
            color: colors.bull,
            lineWidth: 1,
            lineStyle: 2,
            title: `TP${i + 1} · ${Math.round(tp.size_fraction * 100)}%`,
          }),
        );
      });
    }
    return () => lines.forEach((line) => series.removePriceLine(line));
  }, [recommendation, bars, style]);

  // trade / run markers
  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    const colors = chartColors();
    markersRef.current?.detach();
    markersRef.current = createSeriesMarkers(
      series,
      markers
        .filter((m) => m.time > 0)
        .sort((a, b) => a.time - b.time)
        .map((m) => {
          const dir = directionOf(m.direction);
          return {
            time: m.time as UTCTimestamp,
            position: dir === "bear" ? ("aboveBar" as const) : ("belowBar" as const),
            color:
              dir === "bull" ? colors.bull : dir === "bear" ? colors.bear : colors.neutral,
            shape:
              dir === "bull"
                ? ("arrowUp" as const)
                : dir === "bear"
                  ? ("arrowDown" as const)
                  : ("circle" as const),
            text: m.label,
          };
        }),
    );
    return () => {
      markersRef.current?.detach();
      markersRef.current = null;
    };
  }, [markers, bars, style]);

  // live last-price via series.update (never setData on tick)
  const lastBar = bars[bars.length - 1];
  useEffect(() => {
    if (!liveSymbol || !lastBar) return;
    return useTickerStore.subscribe((state) => {
      const tick = state.ticks[liveSymbol];
      const series = seriesRef.current;
      if (!tick || !series) return;
      if (styleRef.current === "candles") {
        (series as ISeriesApi<"Candlestick">).update({
          time: lastBar.time as UTCTimestamp,
          open: lastBar.open,
          high: Math.max(lastBar.high, tick.last),
          low: Math.min(lastBar.low, tick.last),
          close: tick.last,
        });
      } else if (styleRef.current === "line" || styleRef.current === "area") {
        (series as ISeriesApi<"Line">).update({
          time: lastBar.time as UTCTimestamp,
          value: tick.last,
        });
      }
      // heikin-ashi: derived bar — skip live morphing rather than fake it
    });
  }, [liveSymbol, lastBar]);

  return (
    <div
      ref={containerRef}
      style={{ height }}
      role="img"
      aria-label="price chart"
      data-testid="price-chart"
    />
  );
}
