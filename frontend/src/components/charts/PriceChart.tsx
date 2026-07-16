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

import { chartColors, useLightweightChart, hexToRgba } from "./useLightweightChart";
import { loadPaneFactors, savePaneFactors } from "./paneLayout";
import { toHeikinAshi } from "./transform";
import { useChartSync } from "./ChartSync";
import { DrawingsPrimitive } from "./drawings/primitive";
import {
  POINTS_REQUIRED,
  type DrawingKind,
  type DrawingPoint,
  type ToolMode,
} from "./drawings/types";
import { VolumeProfilePrimitive } from "./volumeProfilePrimitive";
import type { Bar, IndicatorSeries, Recommendation, VolumeProfile } from "@/lib/api/types";
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

/** overlays share the price pane; oscillators get their own. Prefix-based
 * so parameterized ids (EMA_21, RSI_9) classify like their family (G7). */
function isOverlayIndicator(name: string): boolean {
  return (
    name.startsWith("EMA_") || name.startsWith("SMA_") ||
    name === "BOLL" || name === "VWAP" || name === "SUPERTREND"
  );
}

/** theme-resolved per-line colors (review finding: hardcoded dark-theme
 * hexes washed out on light backgrounds) */
function indicatorLineColors(colors: ReturnType<typeof chartColors>) {
  return {
    value: colors.accent,
    macd: colors.accent,
    signal: colors.neutral,
    middle: colors.muted,
    upper: colors.muted,
    lower: colors.muted,
  } as Record<string, string>;
}

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
  volumeProfile = null,
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
  /** server-computed fixed-range profile (review P2.4); null hides it */
  volumeProfile?: VolumeProfile | null;
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
  const profileRef = useRef<VolumeProfilePrimitive | null>(null);
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

  // (re)build all series when inputs change; torn down in the cleanup so
  // unmount leaves no stale refs behind
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

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
        topColor: hexToRgba(colors.accent, 0.25),
        bottomColor: hexToRgba(colors.accent, 0.02),
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
      const volumeBear = hexToRgba(colors.bear, 0.55);
      const volumeBull = hexToRgba(colors.bull, 0.55);
      volume.setData(
        data.map((b, i) => ({
          time: b.time as UTCTimestamp,
          value: b.volume,
          color: i > 0 && b.close < data[i - 1]!.close ? volumeBear : volumeBull,
        })),
      );
      extraSeriesRef.current.push(volume);
      nextPane += 1;
    }

    const lineColors = indicatorLineColors(colors);
    for (const [name, block] of Object.entries(indicators ?? {}).sort()) {
      const overlay = isOverlayIndicator(name);
      const paneIndex = overlay ? 0 : nextPane;
      if (!overlay) nextPane += 1;
      for (const [lineName, points] of Object.entries(block.series)) {
        const isHistogram = lineName === "histogram";
        const series = chart.addSeries(
          isHistogram ? HistogramSeries : LineSeries,
          isHistogram
            ? { color: hexToRgba(colors.accent, 0.4) }
            : {
                color: lineColors[lineName] ?? colors.neutral,
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
    if (seriesRef.current) {
      const profilePrimitive = new VolumeProfilePrimitive();
      seriesRef.current.attachPrimitive(profilePrimitive);
      profileRef.current = profilePrimitive;
    }

    // pane proportions (review P2.3): the price pane must stay dominant
    // when oscillators join. Saved factors (user drags, keyed by pane
    // count) win; otherwise price=3, volume=0.8, each oscillator=1.
    const panes = chart.panes();
    if (panes.length > 1) {
      const saved = loadPaneFactors(panes.length);
      panes.forEach((pane, i) => {
        const fallback = i === 0 ? 3 : showVolume && i === 1 ? 0.8 : 1;
        pane.setStretchFactor(saved?.[i] ?? fallback);
      });
    }
    // persist proportions when a separator drag ends
    const container = containerRef.current;
    const persistFactors = () => {
      if (chartRef.current !== chart) return;
      const current = chart.panes();
      if (current.length > 1)
        savePaneFactors(current.length, current.map((p) => p.getStretchFactor()));
    };
    container?.addEventListener("pointerup", persistFactors);

    chart.timeScale().fitContent();

    return () => {
      container?.removeEventListener("pointerup", persistFactors);
      // on unmount the hook cleanup has already run (chart disposed,
      // chartRef nulled) — touching the chart then throws; just drop refs.
      // Reading the ref at cleanup time is the point: it detects disposal.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      if (chartRef.current === chart) {
        markersRef.current?.detach();
        if (seriesRef.current) chart.removeSeries(seriesRef.current);
        extraSeriesRef.current.forEach((series) => chart.removeSeries(series));
      }
      markersRef.current = null;
      seriesRef.current = null;
      extraSeriesRef.current = [];
      primitiveRef.current = null;
      profileRef.current = null;
    };
  }, [bars, style, indicators, showVolume, drawingsSymbol, theme, chartRef, containerRef]);

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
          axisLabelTextColor: colors.onSolid,
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
            axisLabelTextColor: colors.onSolid,
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
            axisLabelTextColor: colors.onSolid,
            lineWidth: 1,
            lineStyle: 2,
            title: `TP${i + 1} · ${Math.round(tp.size_fraction * 100)}%`,
          }),
        );
      });
    }
    return () => {
      // the rebuild cleanup runs first and may have removed the series
      // (shared deps) — its price lines died with it
      if (seriesRef.current !== series) return;
      lines.forEach((line) => series.removePriceLine(line));
    };
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
      // skip detach when the rebuild cleanup already removed the series
      if (seriesRef.current === series) markersRef.current?.detach();
      markersRef.current = null;
    };
  }, [markers, bars, style, indicators, showVolume]);

  // push the server-computed profile + theme colors into its primitive
  useEffect(() => {
    const colors = chartColors();
    profileRef.current?.setProfile(volumeProfile, {
      bar: hexToRgba(colors.muted, 0.16),
      valueArea: hexToRgba(colors.accent, 0.22),
      poc: colors.bear,
    });
  }, [volumeProfile, theme, bars, style, indicators, showVolume]);

  // push drawings + theme colors into the primitive
  useEffect(() => {
    const colors = chartColors();
    primitiveRef.current?.setDrawings(drawings, {
      line: colors.accent,
      fib: colors.neutral,
      fibFill: hexToRgba(colors.neutral, 0.08),
      label: colors.muted,
      bull: colors.bull,
      bear: colors.bear,
      bullFill: hexToRgba(colors.bull, 0.1),
      bearFill: hexToRgba(colors.bear, 0.1),
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

    const onClick = (param: {
      point?: { x: number; y: number };
      time?: unknown;
      paneIndex?: number;
    }) => {
      const mode = toolModeRef.current;
      const primitive = primitiveRef.current;
      const series = seriesRef.current;
      if (!param.point || !primitive || !series) return;
      // drawings live on the PRICE pane only. param.point.y is pane-LOCAL
      // in LWC v5: a click on the volume/oscillator pane fed into the main
      // series' coordinateToPrice stores a garbage anchor (observed: 6297
      // persisted on a ~4300-max chart — off-pane, unerasable). Ignore it.
      if ((param.paneIndex ?? 0) !== 0) return;
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
        // text notes ask for their content on placement (v1: native
        // prompt — an inline editor needs focus plumbing the chart's
        // event capture fights; empty/cancelled input places nothing)
        let text: string | undefined;
        if (mode === "text") {
          text = window.prompt("Note text:")?.trim() || undefined;
          if (!text) {
            cancel();
            return;
          }
        }
        useDrawingsStore.getState().add(drawingsSymbol, {
          id: crypto.randomUUID(),
          kind: mode as DrawingKind,
          points: placed,
          ...(text ? { text } : {}),
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

    const onMove = (param: {
      point?: { x: number; y: number };
      time?: unknown;
      paneIndex?: number;
    }) => {
      if (placedRef.current.length === 0 || !param.point) return;
      if ((param.paneIndex ?? 0) !== 0) return; // price pane only (see onClick)
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
      window.removeEventListener("keydown", onKey);
      // on unmount the chart is already disposed (hook cleanup runs
      // first) and took its subscriptions with it. Reading the ref at
      // cleanup time is the point: it detects disposal.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      if (chartRef.current !== chart) return;
      chart.unsubscribeClick(onClick);
      chart.unsubscribeDblClick(onClick);
      chart.unsubscribeCrosshairMove(onMove);
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
