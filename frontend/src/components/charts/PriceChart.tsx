/** Price chart: candles / heikin-ashi / OHLC bars / line / area,
 * recommendation levels as price lines, trade markers, live last-price
 * updates, optional volume pane, and indicator series from the
 * deterministic engine (/api/bars/indicators) — overlays on the price
 * pane, oscillators in sub-panes. The chart renders numbers; it never
 * computes them (Heikin-Ashi is a labeled presentation redraw). */
import {
  AreaSeries,
  BarSeries,
  BaselineSeries,
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
import { useEffect, useMemo, useRef } from "react";

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
import { snapToBar } from "./annotationSnap";
import { macdCrossLabel, oscillatorLevels } from "./oscillators";
import { snapPriceToOHLC } from "./drawings/geometry";
import {
  AnnotationsPrimitive,
  type SnappedAnnotation,
} from "./annotationsPrimitive";
import { VolumeProfilePrimitive } from "./volumeProfilePrimitive";
import type {
  Bar,
  ChartAnnotations,
  IndicatorSeries,
  Recommendation,
  VolumeProfile,
} from "@/lib/api/types";
import { directionOf } from "@/lib/format";
import { useDrawingsStore } from "@/stores/drawings";
import { useTickerStore } from "@/stores/ticker";
import { useUiStore } from "@/stores/ui";

const NO_DRAWINGS: never[] = [];

export type SeriesStyle =
  | "candles"
  | "hollow"
  | "heikin-ashi"
  | "bars"
  | "line"
  | "area"
  | "baseline";

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

// The price pane is the hero at its full `height`; volume + each oscillator
// add SHORT panes BELOW it (mockup: price ~400px, panes ~90px) rather than
// dividing a fixed total. Pane stretch factors are set to these px so LWC
// renders each pane at ~its target within the grown container.
const VOLUME_PANE_PX = 78;
const OSCILLATOR_PANE_PX = 104;

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
  onCreateAlert,
  height = 420,
  fill = false,
  volumeProfile = null,
  annotations = null,
  onExplainRun,
  openPosition = null,
  logScale = false,
  magnet = false,
  legend = false,
  onLoadOlder,
  showAnnotations = true,
  showPlan = true,
  onContextMenu,
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
  /** A2: click-to-alert callback; receives the clicked price */
  onCreateAlert?: (price: number) => void;
  /** price-pane height in px. In `fill` mode this is only the floor. */
  height?: number;
  /** grow to fill the parent's height (chart-only Trade page) instead of
   * sitting at a fixed height. `height` (+ panes) becomes a min-height so
   * an oscillator stack still expands past the viewport rather than
   * squishing. The parent must be a flex column with a definite height. */
  fill?: boolean;
  /** server-computed fixed-range profile (review P2.4); null hides it */
  volumeProfile?: VolumeProfile | null;
  /** AI decision history painted on price (chart Phase 1); null hides it */
  annotations?: ChartAnnotations | null;
  /** select-mode click on a decision zone/marker/ribbon segment */
  onExplainRun?: (runId: string, point: { x: number; y: number }) => void;
  /** open position for this symbol: server-computed entry + stop line */
  openPosition?: {
    entry_price?: number | null;
    quantity: number;
    stop_price?: number | null;
  } | null;
  /** logarithmic price scale (long-horizon gold/BTC reads honestly in log) */
  logScale?: boolean;
  /** magnet mode: drawing anchors snap to the clicked bar's O/H/L/C */
  magnet?: boolean;
  /** crosshair-follow OHLCV readout (top-left) */
  legend?: boolean;
  /** fired when the user scrolls near the earliest loaded bar (PB.1) */
  onLoadOlder?: () => void;
  /** show/hide the AI decision layer (zones + ribbon + markers) */
  showAnnotations?: boolean;
  /** show/hide the AI's active plan lines (recommendation + position) */
  showPlan?: boolean;
  /** right-click on the price pane → menu payload (PC.2) */
  onContextMenu?: (p: {
    x: number;
    y: number;
    price: number | null;
    runId: string | null;
  }) => void;
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
  const onCreateAlertRef = useRef(onCreateAlert);
  onCreateAlertRef.current = onCreateAlert;
  const annotationsRef = useRef<AnnotationsPrimitive | null>(null);
  const onExplainRunRef = useRef(onExplainRun);
  onExplainRunRef.current = onExplainRun;
  const magnetRef = useRef(magnet);
  magnetRef.current = magnet;
  const measureStartRef = useRef<DrawingPoint | null>(null);
  // history paging (PB.1): the last user-visible logical range, tracked
  // continuously so a prepend of older bars can restore the viewport
  // (shifted) instead of fitContent() snapping the whole history in.
  const visibleRangeRef = useRef<{ from: number; to: number } | null>(null);
  const prevBarsMetaRef = useRef<{ lastTime: number; len: number } | null>(null);
  const barsByTimeRef = useRef<Map<number, Bar>>(new Map());
  barsByTimeRef.current = useMemo(
    () => new Map(bars.map((b) => [b.time, b])),
    [bars],
  );
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

    if (style === "candles" || style === "heikin-ashi" || style === "hollow") {
      const series = chart.addSeries(CandlestickSeries, {
        // hollow: up candles keep only their border (classic hollow style)
        upColor: style === "hollow" ? "rgba(0,0,0,0)" : colors.bull,
        downColor: colors.bear,
        borderUpColor: colors.bull,
        borderDownColor: colors.bear,
        wickUpColor: colors.bull,
        wickDownColor: colors.bear,
      });
      series.setData(ohlc);
      seriesRef.current = series;
    } else if (style === "baseline") {
      // anchored at the window's first close: green above where the
      // window started, red below — a "since here" read, and labeled so
      const base = data[0]?.close ?? 0;
      const series = chart.addSeries(BaselineSeries, {
        baseValue: { type: "price", price: base },
        topLineColor: colors.bull,
        topFillColor1: hexToRgba(colors.bull, 0.2),
        topFillColor2: hexToRgba(colors.bull, 0.02),
        bottomLineColor: colors.bear,
        bottomFillColor1: hexToRgba(colors.bear, 0.02),
        bottomFillColor2: hexToRgba(colors.bear, 0.2),
        lineWidth: 2,
      });
      series.setData(closes);
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
      let primary: ISeriesApi<SeriesType> | null = null;
      for (const [lineName, points] of Object.entries(block.series)) {
        const isHistogram = lineName === "histogram";
        const series = chart.addSeries(
          isHistogram ? HistogramSeries : LineSeries,
          isHistogram
            ? { priceLineVisible: false }
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
          points.map((p) => ({
            time: p.time as UTCTimestamp,
            value: p.value,
            // MACD histogram: per-bar bull/bear by sign (rendering the sign
            // of a served value, not computing an indicator — Constraint 2)
            ...(isHistogram
              ? {
                  color: hexToRgba(
                    p.value >= 0 ? colors.bull : colors.bear,
                    0.5,
                  ),
                }
              : {}),
          })),
        );
        if (!overlay && primary == null && !isHistogram) primary = series;
        extraSeriesRef.current.push(series);
      }
      // conventional reference levels on the oscillator's own pane
      if (!overlay && primary) {
        for (const lvl of oscillatorLevels(name)) {
          primary.createPriceLine({
            price: lvl.price,
            color: hexToRgba(colors.muted, lvl.mid ? 0.25 : 0.45),
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: true,
            title: String(lvl.price),
          });
        }
      }
      // MACD line/signal cross state → surface on the macd line title
      if (name === "MACD" && primary) {
        const macd = block.series["macd"] ?? [];
        const signal = block.series["signal"] ?? [];
        const cross = macdCrossLabel(macd, signal);
        if (cross) primary.applyOptions({ title: `MACD · ${cross}` });
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
      const annotationsPrimitive = new AnnotationsPrimitive();
      seriesRef.current.attachPrimitive(annotationsPrimitive);
      annotationsRef.current = annotationsPrimitive;
    }

    // pane proportions (review P2.3): the price pane must stay dominant
    // when oscillators join. Saved factors (user drags, keyed by pane
    // count) win; otherwise price=3, volume=0.8, each oscillator=1.
    const panes = chart.panes();
    if (panes.length > 1) {
      const saved = loadPaneFactors(panes.length);
      panes.forEach((pane, i) => {
        // px-scaled factors: price = full height, volume/oscillators = their
        // short target px. With the container grown to the sum (below), LWC
        // renders each pane at ~its px. Saved user drags still win.
        const fallback =
          i === 0
            ? height
            : showVolume && i === 1
              ? VOLUME_PANE_PX
              : OSCILLATOR_PANE_PX;
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

    // PB.1: preserve the viewport when older bars are prepended (same
    // last bar, longer array). Otherwise (symbol/timeframe change, live
    // append) fit the content as before.
    const meta = prevBarsMetaRef.current;
    const lastTime = bars.length ? bars[bars.length - 1]!.time : 0;
    const prepended =
      meta != null &&
      meta.lastTime === lastTime &&
      bars.length > meta.len &&
      visibleRangeRef.current != null;
    if (prepended) {
      const delta = bars.length - meta!.len;
      const r = visibleRangeRef.current!;
      chart.timeScale().setVisibleLogicalRange({
        from: r.from + delta,
        to: r.to + delta,
      });
    } else {
      chart.timeScale().fitContent();
    }
    prevBarsMetaRef.current = { lastTime, len: bars.length };

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
      annotationsRef.current = null;
    };
  }, [bars, style, indicators, showVolume, drawingsSymbol, theme, height, chartRef, containerRef]);

  // recommendation levels as price lines (the AI's active plan)
  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    const colors = chartColors();
    const lines: ReturnType<typeof series.createPriceLine>[] = [];
    if (showPlan && recommendation && !recommendation.status && recommendation.entry_price) {
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
  }, [recommendation, showPlan, bars, style, indicators, showVolume]);

  // annotation times snapped to this chart's exact bar times (LWC v5:
  // any other time renders nothing). Off-range annotations drop out and
  // return when older bars are paged in.
  // container grows with the panes so the price pane keeps its full height
  // and oscillators add short panes below (mockup layout), instead of
  // dividing a fixed total and cramping price.
  const oscillatorCount = useMemo(
    () =>
      Object.keys(indicators ?? {}).filter((n) => !isOverlayIndicator(n)).length,
    [indicators],
  );
  const chartHeight =
    height +
    (showVolume ? VOLUME_PANE_PX : 0) +
    oscillatorCount * OSCILLATOR_PANE_PX;

  const barTimes = useMemo(() => bars.map((b) => b.time), [bars]);
  const snappedAnnotations = useMemo<SnappedAnnotation[]>(() => {
    if (!annotations) return [];
    const out: SnappedAnnotation[] = [];
    for (const run of annotations.runs) {
      if (run.time == null) continue;
      const time = snapToBar(barTimes, run.time);
      if (time == null) continue;
      const span = run.span?.from != null
        ? {
            from: snapToBar(barTimes, run.span.from) ?? time,
            to: run.span.to == null
              ? null
              : snapToBar(barTimes, run.span.to),
          }
        : null;
      out.push({
        runId: run.run_id,
        time,
        action: (run.action as SnappedAnnotation["action"]) ?? null,
        rejectedAt: run.rejected_at,
        confidence: run.confidence,
        regime: run.market_regime,
        geometry: run.geometry
          ? {
              entry: run.geometry.entry,
              stop: run.geometry.stop,
              invalidation: run.geometry.invalidation,
              takeProfits: run.geometry.take_profits.map((tp) => ({
                price: tp.price,
                sizeFraction: tp.size_fraction,
              })),
              direction: run.geometry.direction,
            }
          : null,
        span,
      });
    }
    return out;
  }, [annotations, barTimes]);

  // fills painted from the AI record (G3): carry link provenance so
  // inferred matches are labeled honestly. Snapped to bar times.
  const snappedFills = useMemo(() => {
    if (!annotations) return [];
    return annotations.fills
      .map((f) => {
        if (f.closed_time == null) return null;
        const time = snapToBar(barTimes, f.closed_time);
        if (time == null) return null;
        return {
          time,
          won: f.won,
          pnl: f.pnl,
          inferred: f.link === "inferred",
        };
      })
      .filter((f): f is NonNullable<typeof f> => f != null);
  }, [annotations, barTimes]);

  // trade / run markers (journal fills via the markers prop + AI decisions
  // from annotations — merged into the ONE plugin instance per series)
  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    const colors = chartColors();
    markersRef.current?.detach();
    // when the AI layer is on, its fills[] (run-linked, provenance-aware)
    // supersede the journal markers for the same closed trades — avoids
    // double markers and lets inferred fills be labeled
    const fillMarkers = (showAnnotations ? snappedFills : []).map((f) => ({
      time: f.time as UTCTimestamp,
      position: (f.won ? "belowBar" : "aboveBar") as "belowBar" | "aboveBar",
      color: f.won ? colors.bull : colors.bear,
      shape: "circle" as const,
      text:
        (f.inferred ? "~" : "") +
        (f.pnl >= 0 ? "+" : "") +
        f.pnl.toFixed(0),
    }));
    const journalMarkers = (showAnnotations ? [] : markers)
      .filter((m) => m.time > 0)
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
      });
    // decision badges (▲/▼/✕) are drawn as circular badges by the
    // AnnotationsPrimitive — not LWC markers — so they match the mockup.
    markersRef.current = createSeriesMarkers(
      series,
      [...journalMarkers, ...fillMarkers].sort((a, b) =>
        Number(a.time) - Number(b.time)),
    );
    return () => {
      // skip detach when the rebuild cleanup already removed the series
      if (seriesRef.current === series) markersRef.current?.detach();
      markersRef.current = null;
    };
  }, [markers, snappedAnnotations, snappedFills, showAnnotations, bars, style, indicators, showVolume]);

  // push snapped annotations + theme colors into the AI layer primitive
  useEffect(() => {
    const colors = chartColors();
    annotationsRef.current?.setAnnotations(snappedAnnotations, barTimes, {
      bull: colors.bull,
      bear: colors.bear,
      neutral: colors.neutral,
      label: colors.muted,
      bullFill: hexToRgba(colors.bull, 0.08),
      bearFill: hexToRgba(colors.bear, 0.08),
      bg: colors.bg,
    });
    annotationsRef.current?.setVisible(showAnnotations);
  }, [snappedAnnotations, barTimes, annotations, theme, showAnnotations, bars, style, indicators, showVolume]);

  // log/linear price scale (LWC PriceScaleMode: 0 normal, 1 logarithmic).
  // Applied as an option, not a rebuild — pan/zoom state survives the flip.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !seriesRef.current) return;
    chart.priceScale("right").applyOptions({ mode: logScale ? 1 : 0 });
  }, [logScale, chartRef, bars, style, indicators, showVolume]);

  // open-position entry line: server-computed book truth (Constraint 2 —
  // the P&L number itself renders in the workspace badge, not here)
  useEffect(() => {
    const series = seriesRef.current;
    if (!series || !showPlan || !openPosition?.entry_price) return;
    // guard against a stale/mismatched position price (e.g. an old trade on
    // a different price scale) dragging LWC's autoscale off the bars and
    // making the chart unusable — a real open position sits near price.
    const ref = bars.length ? bars[bars.length - 1]!.close : null;
    if (ref != null && (openPosition.entry_price > ref * 3 ||
                        openPosition.entry_price < ref / 3)) {
      return;
    }
    const colors = chartColors();
    const lines = [
      series.createPriceLine({
        price: openPosition.entry_price,
        color: colors.accent,
        axisLabelTextColor: colors.onSolid,
        lineWidth: 2,
        lineStyle: 0,
        title: `POSITION · ${openPosition.quantity}`,
      }),
    ];
    // PC.1: the stop the position was opened with (not a trailing level —
    // the system doesn't trail; it's the honest thesis-death line)
    if (openPosition.stop_price != null) {
      lines.push(
        series.createPriceLine({
          price: openPosition.stop_price,
          color: colors.bear,
          axisLabelTextColor: colors.onSolid,
          lineWidth: 1,
          lineStyle: 1,
          title: "POSITION STOP",
        }),
      );
    }
    return () => {
      if (seriesRef.current !== series) return;
      lines.forEach((l) => series.removePriceLine(l));
    };
  }, [openPosition, showPlan, bars, style, indicators, showVolume]);

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
      measureStartRef.current = null;
      primitiveRef.current?.setPreview(null);
      primitiveRef.current?.setMeasure(null);
      onToolModeChangeRef.current?.("select");
    };

    // measure ruler label: presentation arithmetic over two anchors
    const measureLabel = (a: DrawingPoint, b: DrawingPoint) => {
      const dp = b.price - a.price;
      const pct = a.price !== 0 ? (dp / a.price) * 100 : 0;
      const times = [...barsByTimeRef.current.keys()];
      const ia = times.indexOf(a.time);
      const ib = times.indexOf(b.time);
      const dBars = ia >= 0 && ib >= 0 ? Math.abs(ib - ia) : null;
      return (
        `${dp >= 0 ? "+" : ""}${dp.toFixed(2)} (${pct >= 0 ? "+" : ""}` +
        `${pct.toFixed(2)}%)${dBars != null ? ` · ${dBars} bars` : ""}`
      );
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
      // A2: one click sets a price alert at that level, then drops back to
      // select — an interaction, not a persisted drawing.
      if (mode === "alert") {
        const price = series.coordinateToPrice(param.point.y);
        if (price != null) onCreateAlertRef.current?.(price);
        onToolModeChangeRef.current?.("select");
        return;
      }
      if (mode === "select") {
        // chart Phase 1: a plain click on a decision zone / marker bar /
        // ribbon segment asks "explain this decision"
        const runId = annotationsRef.current?.findNearestRun(param.point);
        if (runId) onExplainRunRef.current?.(runId, param.point);
        return;
      }
      // chart Phase 2: two-click ephemeral ruler; the second click pins
      // the readout until Esc / mode change
      if (mode === "measure") {
        const price = series.coordinateToPrice(param.point.y);
        if (price == null || param.time == null) return;
        const point: DrawingPoint = { time: Number(param.time), price };
        if (measureStartRef.current == null) {
          measureStartRef.current = point;
        } else {
          primitive.setMeasure({
            a: measureStartRef.current,
            b: point,
            label: measureLabel(measureStartRef.current, point),
          });
          measureStartRef.current = null;
        }
        return;
      }
      let price = series.coordinateToPrice(param.point.y);
      if (price == null || param.time == null) return;
      if (magnetRef.current) {
        // magnet: the trader means the wick/close they clicked near
        const bar = barsByTimeRef.current.get(Number(param.time));
        if (bar) price = snapPriceToOHLC(bar, price) as typeof price;
      }
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
      if (!param.point) return;
      if ((param.paneIndex ?? 0) !== 0) return; // price pane only (see onClick)
      // live ruler while the second measure point is unplaced
      if (measureStartRef.current != null && param.time != null) {
        const p = seriesRef.current?.coordinateToPrice(param.point.y);
        if (p != null) {
          const cursor: DrawingPoint = { time: Number(param.time), price: p };
          primitiveRef.current?.setMeasure({
            a: measureStartRef.current,
            b: cursor,
            label: measureLabel(measureStartRef.current, cursor),
          });
        }
        return;
      }
      if (placedRef.current.length === 0) return;
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

  // per-indicator time→value maps for the hover legend (G2): pick one
  // representative line per indicator; read served values, never compute.
  const indicatorLegend = useMemo(() => {
    const out: { label: string; at: Map<number, number> }[] = [];
    for (const [name, block] of Object.entries(indicators ?? {}).sort()) {
      const lines = block.series;
      const key =
        "value" in lines ? "value"
        : "macd" in lines ? "macd"
        : "middle" in lines ? "middle"
        : "k" in lines ? "k"
        : Object.keys(lines)[0];
      if (!key || !lines[key]) continue;
      out.push({
        label: name.replace(/_/g, ""),
        at: new Map(lines[key]!.map((p) => [p.time, p.value])),
      });
    }
    return out;
  }, [indicators]);

  // OHLCV legend: written imperatively — routing mousemove through React
  // state disrupts the chart's own click/tap tracking (documented above)
  const legendRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !legend) return;
    const write = (bar: Bar | undefined, time: number | null) => {
      const el = legendRef.current;
      if (!el) return;
      if (!bar) {
        el.textContent = "";
        return;
      }
      const change = bar.open !== 0
        ? ((bar.close - bar.open) / bar.open) * 100
        : 0;
      const t = time ?? bar.time;
      // append each active indicator's value at the hovered bar (G2)
      const ind = indicatorLegend
        .map(({ label, at }) => {
          const v = at.get(t);
          return v == null ? null : `${label} ${v.toFixed(2)}`;
        })
        .filter(Boolean)
        .join("  ");
      el.textContent =
        `O ${bar.open.toFixed(2)}  H ${bar.high.toFixed(2)}  ` +
        `L ${bar.low.toFixed(2)}  C ${bar.close.toFixed(2)}  ` +
        `${change >= 0 ? "+" : ""}${change.toFixed(2)}%` +
        (bar.volume ? `  V ${Intl.NumberFormat("en", { notation: "compact" }).format(bar.volume)}` : "") +
        (ind ? `   ${ind}` : "");
    };
    const last = bars[bars.length - 1];
    write(last, last?.time ?? null);
    const onLegendMove = (param: { time?: unknown }) => {
      const t = param.time != null ? Number(param.time) : null;
      const bar = t != null ? barsByTimeRef.current.get(t) : undefined;
      write(bar ?? last, bar ? t : (last?.time ?? null));
    };
    chart.subscribeCrosshairMove(onLegendMove);
    return () => {
      // eslint-disable-next-line react-hooks/exhaustive-deps
      if (chartRef.current !== chart) return; // disposed (see above)
      chart.unsubscribeCrosshairMove(onLegendMove);
    };
  }, [legend, bars, indicatorLegend, chartRef]);

  // track the user's visible logical range + fire load-older at the left
  // edge (PB.1). Subscribed once per chart instance so it survives the
  // series rebuilds that a prepend triggers.
  const onLoadOlderRef = useRef(onLoadOlder);
  onLoadOlderRef.current = onLoadOlder;
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const onRange = (range: { from: number; to: number } | null) => {
      if (!range) return;
      visibleRangeRef.current = { from: range.from, to: range.to };
      // only when the user scrolls PAST the first bar into the pre-history
      // whitespace (negative logical index) — fitContent sits at from≈0, so
      // a positive threshold would auto-page on mount and churn the chart.
      if (range.from < -5) onLoadOlderRef.current?.();
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(onRange);
    return () => {
      // eslint-disable-next-line react-hooks/exhaustive-deps
      if (chartRef.current !== chart) return; // disposed
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(onRange);
    };
  }, [chartRef]);

  // right-click context menu (PC.2): resolve the clicked price + nearest
  // AI decision from raw DOM coords (no LWC click param on contextmenu)
  const onContextMenuRef = useRef(onContextMenu);
  onContextMenuRef.current = onContextMenu;
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const handler = (e: MouseEvent) => {
      const cb = onContextMenuRef.current;
      const series = seriesRef.current;
      if (!cb || !series) return;
      e.preventDefault();
      const rect = container.getBoundingClientRect();
      const point = { x: e.clientX - rect.left, y: e.clientY - rect.top };
      const price = series.coordinateToPrice(point.y);
      const runId = annotationsRef.current?.findNearestRun(point) ?? null;
      cb({ x: point.x, y: point.y, price: price ?? null, runId });
    };
    container.addEventListener("contextmenu", handler);
    return () => container.removeEventListener("contextmenu", handler);
  }, [containerRef]);

  // live last-price via series.update (never setData on tick)
  const lastBar = bars[bars.length - 1];
  useEffect(() => {
    if (!liveSymbol || !lastBar) return;
    return useTickerStore.subscribe((state) => {
      const tick = state.ticks[liveSymbol];
      const series = seriesRef.current;
      if (!tick || !series) return;
      if (styleRef.current === "candles" || styleRef.current === "bars" ||
          styleRef.current === "hollow") {
        (series as ISeriesApi<"Candlestick">).update({
          time: lastBar.time as UTCTimestamp,
          open: lastBar.open,
          high: Math.max(lastBar.high, tick.last),
          low: Math.min(lastBar.low, tick.last),
          close: tick.last,
        });
      } else if (styleRef.current === "line" || styleRef.current === "area" ||
                 styleRef.current === "baseline") {
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
      className={fill ? "relative min-h-0 flex-1" : "relative"}
      style={{
        // fill mode: grow to the parent, floored at the pane-sum so
        // oscillator stacks expand instead of squishing. fixed mode: the
        // exact pane-sum (grid cells, other embeds).
        ...(fill ? { minHeight: chartHeight } : { height: chartHeight }),
        cursor: toolMode !== "select" ? "crosshair" : undefined,
      }}
      role="img"
      aria-label="price chart"
      data-testid="price-chart"
      data-drawings={drawingsSymbol ? drawings.length : undefined}
      data-annotations={annotations ? snappedAnnotations.length : undefined}
    >
      {legend && (
        <div
          ref={legendRef}
          data-testid="chart-legend"
          className="pointer-events-none absolute left-1.5 top-1.5 z-10 rounded bg-surface/80 px-1.5 py-0.5 font-mono text-[10px] text-fg-muted"
        />
      )}
    </div>
  );
}
