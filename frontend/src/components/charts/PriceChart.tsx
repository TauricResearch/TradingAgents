/** Price chart: candles / heikin-ashi / OHLC bars / line / area,
 * recommendation levels as price lines, trade markers, live last-price
 * updates, optional volume pane, and indicator series from the
 * deterministic engine (/api/bars/indicators) — overlays on the price
 * pane, oscillators in sub-panes. The chart renders numbers; it never
 * computes them (Heikin-Ashi is a labeled presentation redraw). */
import {
  AreaSeries,
  BarSeries,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createSeriesMarkers,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesType,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

import { chartColors, useLightweightChart } from "./useLightweightChart";
import { toHeikinAshi } from "./transform";
import { useChartSync } from "./ChartSync";
import { DrawingsPrimitive } from "./drawings/primitive";
import {
  POINTS_REQUIRED,
  type DrawingKind,
  type DrawingPoint,
  type ToolMode,
} from "./drawings/types";
import type { Bar, IndicatorSeries, Recommendation } from "@/lib/api/types";
import { directionOf } from "@/lib/format";
import { useDrawingsStore } from "@/stores/drawings";
import { useTickerStore } from "@/stores/ticker";
import { useUiStore } from "@/stores/ui";

const NO_DRAWINGS: never[] = [];

export type SeriesStyle = "candles" | "heikin-ashi" | "bars" | "line" | "area";

export interface TradeMarker {
  time: number;
  direction: string | null;
  label: string;
}

/** overlays share the price pane; oscillators get their own */
const OVERLAY_INDICATORS = new Set(["EMA_10", "SMA_50", "SMA_200", "BOLL"]);

const INDICATOR_LINE_COLORS: Record<string, string> = {
  value: "#79c0ff",
  macd: "#79c0ff",
  signal: "#d29922",
  middle: "#9ca7b3",
  upper: "#6e7681",
  lower: "#6e7681",
};

export function PriceChart({
  bars,
  style = "candles",
  recommendation,
  markers = [],
  liveSymbol,
  indicators,
  showVolume = false,
  syncId,
  drawingsSymbol,
  toolMode = "select",
  onToolModeChange,
  height = 420,
}: {
  bars: Bar[];
  style?: SeriesStyle;
  recommendation?: Recommendation | null;
  markers?: TradeMarker[];
  /** ticker-store symbol for live last-price updates; omit during replay */
  liveSymbol?: string;
  /** deterministic indicator series keyed by name (RSI_14, MACD, …) */
  indicators?: IndicatorSeries;
  showVolume?: boolean;
  /** register with a ChartSyncProvider group for crosshair sync */
  syncId?: string;
  /** enable user drawings, persisted under this symbol */
  drawingsSymbol?: string;
  toolMode?: ToolMode;
  onToolModeChange?: (mode: ToolMode) => void;
  height?: number;
}) {
  const seriesRef = useRef<ISeriesApi<SeriesType> | null>(null);
  const extraSeriesRef = useRef<ISeriesApi<SeriesType>[]>([]);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const styleRef = useRef(style);
  styleRef.current = style;

  const { containerRef, chartRef } = useLightweightChart(() => undefined);
  useChartSync(syncId, chartRef);

  // --- user drawings (annotations; pure geometry) ------------------------------
  const primitiveRef = useRef<DrawingsPrimitive | null>(null);
  const placedRef = useRef<DrawingPoint[]>([]);
  // click + dblclick both route to placement (LWC suppresses the second
  // click of a fast pair); dedupe identical events at the window boundary
  const lastEventRef = useRef<{ time: number; price: number; at: number } | null>(null);
  const toolModeRef = useRef<ToolMode>(toolMode);
  toolModeRef.current = toolMode;
  const onToolModeChangeRef = useRef(onToolModeChange);
  onToolModeChangeRef.current = onToolModeChange;
  const theme = useUiStore((s) => s.theme);
  const drawings = useDrawingsStore((state) =>
    drawingsSymbol ? (state.bySymbol[drawingsSymbol] ?? NO_DRAWINGS) : NO_DRAWINGS,
  );

  // (re)build all series when inputs change
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    markersRef.current?.detach();
    markersRef.current = null;
    if (seriesRef.current) chart.removeSeries(seriesRef.current);
    extraSeriesRef.current.forEach((series) => chart.removeSeries(series));
    seriesRef.current = null;
    extraSeriesRef.current = [];

    const colors = chartColors();
    const data = style === "heikin-ashi" ? toHeikinAshi(bars) : bars;
    const ohlc = data.map((b) => ({
      time: b.time as UTCTimestamp,
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
    }));
    const closes = data.map((b) => ({
      time: b.time as UTCTimestamp,
      value: b.close,
    }));

    if (style === "candles" || style === "heikin-ashi") {
      const series = chart.addSeries(CandlestickSeries, {
        upColor: colors.bull,
        downColor: colors.bear,
        borderUpColor: colors.bull,
        borderDownColor: colors.bear,
        wickUpColor: colors.bull,
        wickDownColor: colors.bear,
      });
      series.setData(ohlc);
      seriesRef.current = series;
    } else if (style === "bars") {
      const series = chart.addSeries(BarSeries, {
        upColor: colors.bull,
        downColor: colors.bear,
        thinBars: false,
      });
      series.setData(ohlc);
      seriesRef.current = series;
    } else if (style === "line") {
      const series = chart.addSeries(LineSeries, {
        color: colors.accent,
        lineWidth: 2,
      });
      series.setData(closes);
      seriesRef.current = series;
    } else {
      const series = chart.addSeries(AreaSeries, {
        lineColor: colors.accent,
        topColor: "rgba(121,192,255,0.25)",
        bottomColor: "rgba(121,192,255,0.02)",
        lineWidth: 2,
      });
      series.setData(closes);
      seriesRef.current = series;
    }

    // pane layout: 0 = price (+overlays); volume next; then one pane per
    // oscillator, in stable name order
    let nextPane = 1;

    if (showVolume) {
      const volume = chart.addSeries(
        HistogramSeries,
        { priceFormat: { type: "volume" }, priceScaleId: "volume" },
        nextPane,
      );
      volume.setData(
        data.map((b, i) => ({
          time: b.time as UTCTimestamp,
          value: b.volume,
          color:
            i > 0 && b.close < data[i - 1]!.close
              ? "rgba(248,81,73,0.5)"
              : "rgba(63,185,80,0.5)",
        })),
      );
      extraSeriesRef.current.push(volume);
      nextPane += 1;
    }

    for (const [name, block] of Object.entries(indicators ?? {}).sort()) {
      const overlay = OVERLAY_INDICATORS.has(name);
      const paneIndex = overlay ? 0 : nextPane;
      if (!overlay) nextPane += 1;
      for (const [lineName, points] of Object.entries(block.series)) {
        const isHistogram = lineName === "histogram";
        const series = chart.addSeries(
          isHistogram ? HistogramSeries : LineSeries,
          isHistogram
            ? { color: "rgba(121,192,255,0.4)" }
            : {
                color: INDICATOR_LINE_COLORS[lineName] ?? colors.neutral,
                lineWidth: 1,
                priceLineVisible: false,
                lastValueVisible: !overlay,
                title: overlay ? name : `${name} ${lineName}`,
              },
          paneIndex,
        );
        series.setData(
          points.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })),
        );
        extraSeriesRef.current.push(series);
      }
    }

    if (drawingsSymbol && seriesRef.current) {
      const primitive = new DrawingsPrimitive();
      seriesRef.current.attachPrimitive(primitive);
      primitiveRef.current = primitive;
    }

    chart.timeScale().fitContent();
  }, [bars, style, indicators, showVolume, drawingsSymbol, chartRef]);

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
  }, [recommendation, bars, style, indicators, showVolume]);

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
  }, [markers, bars, style, indicators, showVolume]);

  // push drawings + theme colors into the primitive
  useEffect(() => {
    const colors = chartColors();
    primitiveRef.current?.setDrawings(drawings, {
      line: colors.accent,
      fib: colors.neutral,
      label: colors.muted,
    });
  }, [drawings, theme, bars, style, indicators, showVolume]);

  // click-to-place, crosshair preview, erase, Esc cancel
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !drawingsSymbol) return;

    const cancel = () => {
      placedRef.current = [];
      lastEventRef.current = null; // dedupe only spans one tap gesture
      primitiveRef.current?.setPreview(null);
      onToolModeChangeRef.current?.("select");
    };

    const onClick = (param: { point?: { x: number; y: number }; time?: unknown }) => {
      const mode = toolModeRef.current;
      const primitive = primitiveRef.current;
      const series = seriesRef.current;
      if (!param.point || !primitive || !series) return;
      if (mode === "erase") {
        const id = primitive.findNearest(param.point);
        if (id) useDrawingsStore.getState().remove(drawingsSymbol, id);
        return;
      }
      if (mode === "select") return;
      const price = series.coordinateToPrice(param.point.y);
      if (price == null || param.time == null) return;
      const point: DrawingPoint = { time: Number(param.time), price };
      const last = lastEventRef.current;
      if (last && Date.now() - last.at < 300 &&
          last.time === point.time && last.price === point.price) {
        return; // click + dblclick delivered for the same tap
      }
      lastEventRef.current = { ...point, at: Date.now() };
      const placed = [...placedRef.current, point];
      if (placed.length >= POINTS_REQUIRED[mode as DrawingKind]) {
        useDrawingsStore.getState().add(drawingsSymbol, {
          id: crypto.randomUUID(),
          kind: mode as DrawingKind,
          points: placed,
        });
        cancel();
      } else {
        placedRef.current = placed;
        primitiveRef.current?.setPreview({
          kind: mode as DrawingKind,
          placed,
          cursor: null,
        });
      }
    };

    const onMove = (param: { point?: { x: number; y: number }; time?: unknown }) => {
      if (placedRef.current.length === 0 || !param.point) return;
      const price = seriesRef.current?.coordinateToPrice(param.point.y);
      if (price == null || param.time == null) return;
      primitiveRef.current?.setPreview({
        kind: toolModeRef.current as DrawingKind,
        placed: placedRef.current,
        cursor: { time: Number(param.time), price },
      });
    };

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") cancel();
    };

    // LWC suppresses the second click of a <500ms pair (double-click
    // detection) — subscribe both so rapid two-click placement works
    chart.subscribeClick(onClick);
    chart.subscribeDblClick(onClick);
    chart.subscribeCrosshairMove(onMove);
    window.addEventListener("keydown", onKey);
    return () => {
      chart.unsubscribeClick(onClick);
      chart.unsubscribeDblClick(onClick);
      chart.unsubscribeCrosshairMove(onMove);
      window.removeEventListener("keydown", onKey);
    };
  }, [drawingsSymbol, chartRef]);

  // live last-price via series.update (never setData on tick)
  const lastBar = bars[bars.length - 1];
  useEffect(() => {
    if (!liveSymbol || !lastBar) return;
    return useTickerStore.subscribe((state) => {
      const tick = state.ticks[liveSymbol];
      const series = seriesRef.current;
      if (!tick || !series) return;
      if (styleRef.current === "candles" || styleRef.current === "bars") {
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
      style={{ height, cursor: toolMode !== "select" ? "crosshair" : undefined }}
      role="img"
      aria-label="price chart"
      data-testid="price-chart"
      data-drawings={drawingsSymbol ? drawings.length : undefined}
    />
  );
}
