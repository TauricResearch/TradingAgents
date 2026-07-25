/**
 * Read-only OHLCV/event visualisation for a workbench run.
 *
 * All pixels are drawn on one Canvas from GET /market-view projections of
 * persisted artifacts. The fixed-cell index below is a compact spatial index:
 * a pointer only inspects targets in its cell, never every candle or event.
 * Brushing changes local attribution state only; it cannot fetch market data.
 */
import { useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import { getMarketEventLayer2, getMarketView } from "../../api/client";
import type {
  MarketBarDTO,
  MarketEventDTO,
  MarketEventLayer2DTO,
  MarketViewDTO,
} from "../../api/contracts";

const WIDTH = 760;
const HEIGHT = 310;
const PLOT = { left: 50, right: 18, top: 20, bottom: 70 };
const PLOT_WIDTH = WIDTH - PLOT.left - PLOT.right;
const PLOT_HEIGHT = HEIGHT - PLOT.top - PLOT.bottom;
const BRUSH = { top: HEIGHT - 36, height: 15 };
const HIT_CELL = 32;

type Range = readonly [number, number] | null;
type Tone = "bull" | "bear" | "neutral";

interface HoveredDatum {
  bar?: MarketBarDTO;
  event?: MarketEventDTO;
}

interface Rect {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

interface SpatialItem<T> extends Rect {
  value: T;
}

export type ChartHit =
  | { kind: "bar"; bar: MarketBarDTO; index: number }
  | { kind: "event"; event: MarketEventDTO; x: number; y: number };

/**
 * Fixed-size cells are the compact equivalent of a quadtree for this bounded
 * chart. Insertion distributes an item only to its overlapping cells and a
 * point lookup reads one bucket, rather than linearly scanning all marks.
 */
export class CanvasSpatialIndex<T> {
  private readonly cells = new Map<string, SpatialItem<T>[]>();

  constructor(private readonly cellSize = HIT_CELL) {}

  insert(item: SpatialItem<T>): void {
    const startX = Math.floor(item.x0 / this.cellSize);
    const endX = Math.floor(item.x1 / this.cellSize);
    const startY = Math.floor(item.y0 / this.cellSize);
    const endY = Math.floor(item.y1 / this.cellSize);
    for (let x = startX; x <= endX; x += 1) {
      for (let y = startY; y <= endY; y += 1) {
        const key = `${x}:${y}`;
        const bucket = this.cells.get(key) ?? [];
        bucket.push(item);
        this.cells.set(key, bucket);
      }
    }
  }

  queryPoint(x: number, y: number): T[] {
    const bucket = this.cells.get(`${Math.floor(x / this.cellSize)}:${Math.floor(y / this.cellSize)}`) ?? [];
    return bucket
      .filter((item) => x >= item.x0 && x <= item.x1 && y >= item.y0 && y <= item.y1)
      .map((item) => item.value);
  }
}

export interface MarketAttribution {
  bar_count: number;
  event_count: number;
  bullish_count: number;
  bearish_count: number;
  neutral_count: number;
}

export function deriveAttribution(events: MarketEventDTO[], bars: MarketBarDTO[]): MarketAttribution {
  const counts = { bullish_count: 0, bearish_count: 0, neutral_count: 0 };
  for (const event of events) {
    const sentiment = event.sentiment?.toLowerCase() ?? "";
    if (sentiment.includes("bull") || sentiment.includes("positive")) counts.bullish_count += 1;
    else if (sentiment.includes("bear") || sentiment.includes("negative")) counts.bearish_count += 1;
    else counts.neutral_count += 1;
  }
  return { bar_count: bars.length, event_count: events.length, ...counts };
}

/** Sorted brush positions make nearest-candle selection O(log n). */
export function nearestIndexForX(xs: number[], target: number): number | null {
  if (xs.length === 0) return null;
  let low = 0;
  let high = xs.length - 1;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (xs[middle] < target) low = middle + 1;
    else high = middle;
  }
  if (low === 0) return 0;
  return Math.abs(xs[low] - target) < Math.abs(xs[low - 1] - target) ? low : low - 1;
}

export function rangeForIndex(index: number, anchor: number): Range {
  return index === anchor ? null : ([Math.min(index, anchor), Math.max(index, anchor)] as const);
}

function timestampNumber(value: string): number | null {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatDate(value: string): string {
  const parsed = timestampNumber(value);
  return parsed === null
    ? value
    : new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric" }).format(parsed);
}

function formatPrice(value: number): string {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(value);
}

function eventTone(event: MarketEventDTO): Tone {
  const sentiment = event.sentiment?.toLowerCase() ?? "";
  if (sentiment.includes("bull") || sentiment.includes("positive")) return "bull";
  if (sentiment.includes("bear") || sentiment.includes("negative")) return "bear";
  return "neutral";
}

export function nearestBarForEvent(
  event: MarketEventDTO,
  bars: MarketBarDTO[],
): MarketBarDTO | null {
  const eventTime = timestampNumber(event.timestamp);
  if (eventTime === null || bars.length === 0) return null;
  let nearest = bars[0];
  let nearestDist = Math.abs(
    (timestampNumber(nearest.timestamp) ?? eventTime) - eventTime,
  );
  for (const bar of bars) {
    const barTime = timestampNumber(bar.timestamp);
    if (barTime === null) continue;
    const dist = Math.abs(barTime - eventTime);
    if (dist < nearestDist) {
      nearest = bar;
      nearestDist = dist;
    }
  }
  return nearest;
}

export function eventRadius(bar: MarketBarDTO | null): number {
  // Encode the nearest bar's return magnitude as the particle radius so a
  // large move on the event day draws a larger mark.  A 10% move maps to the
  // maximum; larger moves clamp.  No relevance alpha is fabricated:
  // MarketEventDTO carries no relevance field, so alpha stays fixed and only
  // colour (sentiment) and radius (realised move) encode information.
  const baseline = 4;
  const maxRadius = 10;
  if (bar === null || !bar.open) return baseline;
  const magnitude = Math.abs((bar.close - bar.open) / bar.open);
  return baseline + Math.min(magnitude / 0.1, 1) * (maxRadius - baseline);
}

function xForIndex(index: number, count: number): number {
  if (count <= 1) return PLOT.left + PLOT_WIDTH / 2;
  return PLOT.left + (index / (count - 1)) * PLOT_WIDTH;
}

function withinBars(event: MarketEventDTO, bars: MarketBarDTO[]): boolean {
  const eventTime = timestampNumber(event.timestamp);
  const first = bars[0] ? timestampNumber(bars[0].timestamp) : null;
  const last = bars.at(-1) ? timestampNumber(bars.at(-1)!.timestamp) : null;
  return eventTime !== null && first !== null && last !== null && eventTime >= first && eventTime <= last;
}

function cssColor(variable: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(variable).trim() || fallback;
}

export interface MarketChartProps {
  run_id: string;
  latest_sequence: number;
  artifact_count: number;
}

export function MarketChart({ run_id, latest_sequence, artifact_count }: MarketChartProps): JSX.Element {
  const [view, setView] = useState<MarketViewDTO | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<Range>(null);
  const [brushAnchor, setBrushAnchor] = useState<number | null>(null);
  const [hovered, setHovered] = useState<HoveredDatum | null>(null);
  const [layer2Event, setLayer2Event] = useState<MarketEventDTO | null>(null);
  const [layer2Result, setLayer2Result] = useState<MarketEventLayer2DTO | null>(null);
  const [layer2Loading, setLayer2Loading] = useState(false);
  const [layer2Error, setLayer2Error] = useState<string | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const pendingClickRef = useRef<{ x: number; y: number; event: MarketEventDTO | null } | null>(null);

  useEffect(() => {
    if (artifact_count === 0) {
      setView({ bars: [], events: [], coverage: { bar_source_artifact_ids: [], event_source_artifact_ids: [], skipped_artifact_count: 0, as_of_sequence: latest_sequence } });
      setLoading(false);
      setError(null);
      return;
    }
    let active = true;
    setLoading(true);
    setError(null);
    void getMarketView(run_id, latest_sequence)
      .then((next) => {
        if (!active) return;
        setView(next);
        setRange(null);
        setLayer2Event(null);
        setLayer2Result(null);
        setLayer2Error(null);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : String(reason));
        setView(null);
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [run_id, artifact_count, latest_sequence]);

  const allBars = view?.bars ?? [];
  const selectedBars = useMemo(() => range === null ? allBars : allBars.slice(range[0], range[1] + 1), [allBars, range]);
  const selectedEvents = useMemo(() => (view?.events ?? []).filter((event) => withinBars(event, selectedBars)), [selectedBars, view?.events]);
  const attribution = useMemo(() => deriveAttribution(selectedEvents, selectedBars), [selectedEvents, selectedBars]);
  const bounds = useMemo(() => {
    if (selectedBars.length === 0) return null;
    const values = selectedBars.flatMap((bar) => [bar.high, bar.low]);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const padding = Math.max((max - min) * 0.08, max * 0.002, 0.01);
    return { min: min - padding, max: max + padding };
  }, [selectedBars]);

  const scene = useMemo(() => {
    if (!bounds) return null;
    const yForPrice = (price: number): number => PLOT.top + ((bounds.max - price) / (bounds.max - bounds.min)) * PLOT_HEIGHT;
    const index = new CanvasSpatialIndex<ChartHit>();
    const candleWidth = Math.max(2, Math.min(10, PLOT_WIDTH / selectedBars.length * 0.62));
    const bars = selectedBars.map((bar, indexValue) => {
      const x = xForIndex(indexValue, selectedBars.length);
      const hit: ChartHit = { kind: "bar", bar, index: indexValue };
      index.insert({ x0: x - Math.max(8, candleWidth), x1: x + Math.max(8, candleWidth), y0: PLOT.top, y1: PLOT.top + PLOT_HEIGHT, value: hit });
      return { bar, x, yOpen: yForPrice(bar.open), yClose: yForPrice(bar.close), yHigh: yForPrice(bar.high), yLow: yForPrice(bar.low) };
    });
    const first = timestampNumber(selectedBars[0].timestamp)!;
    const last = timestampNumber(selectedBars.at(-1)!.timestamp)!;
    const events = selectedEvents.map((event) => {
      const eventTime = timestampNumber(event.timestamp)!;
      const x = last === first ? PLOT.left + PLOT_WIDTH / 2 : PLOT.left + ((eventTime - first) / (last - first)) * PLOT_WIDTH;
      const y = PLOT.top + 6;
      const hit: ChartHit = { kind: "event", event, x, y };
      index.insert({ x0: x - 10, x1: x + 10, y0: y - 10, y1: y + 10, value: hit });
      return { event, x, y, tone: eventTone(event), radius: eventRadius(nearestBarForEvent(event, selectedBars)) };
    });
    return { index, yForPrice, candleWidth, bars, events };
  }, [bounds, selectedBars, selectedEvents]);

  const brushXs = useMemo(() => allBars.map((_bar, index) => xForIndex(index, allBars.length)), [allBars]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !scene || !bounds) return;
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.round(WIDTH * ratio);
    canvas.height = Math.round(HEIGHT * ratio);
    const context = canvas.getContext("2d");
    if (!context) return;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, WIDTH, HEIGHT);
    const line = cssColor("--line", "#3c4654");
    const faint = cssColor("--faint", "#7e8b9c");
    const panel2 = cssColor("--panel-2", "#1b2430");
    const accent = cssColor("--accent", "#92a8c7");
    const green = cssColor("--green", "#56b68b");
    const red = cssColor("--red", "#de746d");
    const amber = cssColor("--amber", "#d3a949");

    context.font = "10px var(--font-mono, monospace)";
    context.textBaseline = "middle";
    for (const ratioValue of [0, 0.5, 1]) {
      const y = PLOT.top + PLOT_HEIGHT * ratioValue;
      const price = bounds.max - (bounds.max - bounds.min) * ratioValue;
      context.strokeStyle = line;
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(PLOT.left, y);
      context.lineTo(WIDTH - PLOT.right, y);
      context.stroke();
      context.fillStyle = faint;
      context.fillText(formatPrice(price), 3, y);
    }
    for (const item of scene.bars) {
      const rising = item.bar.close >= item.bar.open;
      context.strokeStyle = rising ? green : red;
      context.fillStyle = rising ? green : red;
      context.lineWidth = 1.25;
      context.beginPath();
      context.moveTo(item.x, item.yHigh);
      context.lineTo(item.x, item.yLow);
      context.stroke();
      context.fillRect(item.x - scene.candleWidth / 2, Math.min(item.yOpen, item.yClose), scene.candleWidth, Math.max(1.5, Math.abs(item.yClose - item.yOpen)));
    }
    for (const item of scene.events) {
      const color = item.tone === "bull" ? green : item.tone === "bear" ? red : amber;
      context.strokeStyle = color;
      context.fillStyle = color;
      context.setLineDash([2, 2]);
      context.beginPath();
      context.moveTo(item.x, PLOT.top);
      context.lineTo(item.x, PLOT.top + 16);
      context.stroke();
      context.setLineDash([]);
      context.beginPath();
      context.arc(item.x, item.y, item.radius, 0, Math.PI * 2);
      context.fill();
    }
    if (hovered?.bar) {
      const bar = scene.bars.find((item) => item.bar === hovered.bar);
      if (bar) {
        context.strokeStyle = accent;
        context.globalAlpha = 0.65;
        context.setLineDash([3, 3]);
        context.beginPath();
        context.moveTo(bar.x, PLOT.top);
        context.lineTo(bar.x, PLOT.top + PLOT_HEIGHT);
        context.stroke();
        context.setLineDash([]);
        context.globalAlpha = 1;
      }
    }
    const start = range?.[0] ?? 0;
    const end = range?.[1] ?? Math.max(0, allBars.length - 1);
    const left = allBars.length > 0 ? xForIndex(start, allBars.length) : PLOT.left;
    const right = allBars.length > 0 ? xForIndex(end, allBars.length) : PLOT.left;
    context.fillStyle = panel2;
    context.fillRect(PLOT.left, BRUSH.top, PLOT_WIDTH, BRUSH.height);
    context.fillStyle = accent;
    context.globalAlpha = 0.42;
    context.fillRect(left, BRUSH.top, Math.max(4, right - left), BRUSH.height);
    context.globalAlpha = 1;
    context.fillStyle = faint;
    context.textBaseline = "alphabetic";
    context.fillText(formatDate(allBars[0].timestamp), PLOT.left, HEIGHT - 7);
    const endLabel = formatDate(allBars.at(-1)!.timestamp);
    context.fillText(endLabel, WIDTH - PLOT.right - context.measureText(endLabel).width, HEIGHT - 7);
  }, [allBars, bounds, hovered, range, scene]);

  function pointForPointer(event: PointerEvent<HTMLCanvasElement>): { x: number; y: number } | null {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return null;
    return { x: ((event.clientX - rect.left) / rect.width) * WIDTH, y: ((event.clientY - rect.top) / rect.height) * HEIGHT };
  }

  function brushIndex(x: number): number | null {
    return nearestIndexForX(brushXs, x);
  }

  function requestLayer2(event: MarketEventDTO): void {
    // This is a public local-cache read only. It cannot start a provider or model request.
    setLayer2Event(event);
    setLayer2Result(null);
    setLayer2Error(null);
    setLayer2Loading(true);
    void getMarketEventLayer2(run_id, event)
      .then((result) => setLayer2Result(result))
      .catch((reason: unknown) => setLayer2Error(reason instanceof Error ? reason.message : String(reason)))
      .finally(() => setLayer2Loading(false));
  }

  function handlePointerDown(event: PointerEvent<HTMLCanvasElement>): void {
    const point = pointForPointer(event);
    if (!point) return;
    if (point.y >= BRUSH.top - 8 && point.y <= BRUSH.top + BRUSH.height + 8) {
      const index = brushIndex(point.x);
      if (index === null) return;
      event.currentTarget.setPointerCapture(event.pointerId);
      setBrushAnchor(index);
      setRange(null);
      return;
    }
    const eventHit = scene?.index.queryPoint(point.x, point.y).find((hit): hit is Extract<ChartHit, { kind: "event" }> => hit.kind === "event");
    pendingClickRef.current = { ...point, event: eventHit?.event ?? null };
  }

  function handlePointerMove(event: PointerEvent<HTMLCanvasElement>): void {
    const point = pointForPointer(event);
    if (!point) return;
    if (brushAnchor !== null) {
      const index = brushIndex(point.x);
      if (index !== null) setRange(rangeForIndex(index, brushAnchor));
      return;
    }
    const hits = scene?.index.queryPoint(point.x, point.y) ?? [];
    const eventHit = hits.find((hit): hit is Extract<ChartHit, { kind: "event" }> => hit.kind === "event");
    const barHit = hits.find((hit): hit is Extract<ChartHit, { kind: "bar" }> => hit.kind === "bar");
    setHovered(eventHit ? { bar: barHit?.bar, event: eventHit.event } : barHit ? { bar: barHit.bar } : null);
  }

  function handlePointerUp(event: PointerEvent<HTMLCanvasElement>): void {
    const point = pointForPointer(event);
    if (brushAnchor !== null) {
      if (point) {
        const index = brushIndex(point.x);
        if (index !== null) setRange(rangeForIndex(index, brushAnchor));
      }
      setBrushAnchor(null);
      return;
    }
    const pending = pendingClickRef.current;
    pendingClickRef.current = null;
    if (point && pending?.event && Math.hypot(point.x - pending.x, point.y - pending.y) <= 5) requestLayer2(pending.event);
  }

  return (
    <section className="market-chart" aria-label="行情与事件对照">
      <div className="market-chart-head">
        <div><span className="eyebrow">Captured market data</span><h3>行情与事件对照</h3></div>
        {view && <span className="market-chart-source">{view.coverage.bar_source_artifact_ids.length} 条行情来源 · {view.coverage.event_source_artifact_ids.length} 条事件来源</span>}
      </div>
      {loading && <div className="placeholder">正在读取本次运行已捕获的数据</div>}
      {error && <div className="error-text">行情视图加载失败：{error}</div>}
      {!loading && !error && view && allBars.length === 0 && <div className="market-chart-empty">本次运行尚未捕获可绘制的 OHLCV 记录；不会为界面额外请求行情。{view.events.length > 0 && ` 已捕获 ${view.events.length} 条带日期的事件记录。`}</div>}
      {!loading && !error && bounds && scene && (
        <>
          <div className="market-canvas-shell">
            <canvas ref={canvasRef} className="market-chart-canvas" role="img" aria-label={`已捕获 ${selectedBars.length} 根K线和 ${selectedEvents.length} 条事件；拖动底部区间条筛选本地归因`} onPointerDown={handlePointerDown} onPointerMove={handlePointerMove} onPointerUp={handlePointerUp} onPointerCancel={handlePointerUp} onPointerLeave={() => { if (brushAnchor === null) setHovered(null); }} />
            {scene.events.map((item) => <button key={`${item.event.timestamp}-${item.event.title}`} type="button" className="market-event-hit-target" style={{ left: `${(item.x / WIDTH) * 100}%`, top: `${(item.y / HEIGHT) * 100}%` }} aria-label={`读取 ${item.event.title} 的已缓存深度审阅`} onClick={() => requestLayer2(item.event)} />)}
          </div>
          <div className="market-attribution" aria-live="polite">
            <span>区间 {formatDate(selectedBars[0].timestamp)}–{formatDate(selectedBars.at(-1)!.timestamp)}</span><strong>{attribution.bar_count} 根K线 · {attribution.event_count} 条事件</strong><span className="sentiment-bull">偏多 {attribution.bullish_count}</span><span className="sentiment-bear">偏空 {attribution.bearish_count}</span><span>未标注 {attribution.neutral_count}</span>{range !== null && <button type="button" className="market-reset" onClick={() => setRange(null)}>重置区间</button>}
          </div>
          {hovered && <div className="market-tooltip" role="status">{hovered.bar && <span>{formatDate(hovered.bar.timestamp)} O {formatPrice(hovered.bar.open)} H {formatPrice(hovered.bar.high)} L {formatPrice(hovered.bar.low)} C {formatPrice(hovered.bar.close)}</span>}{hovered.event && <strong>{hovered.event.title}</strong>}</div>}
          {layer2Event && <div className="market-layer2" aria-live="polite"><div className="market-layer2-head"><span className="eyebrow">Layer 2 cache</span><strong>{layer2Event.title}</strong></div>{layer2Loading && <span className="placeholder">正在检查本地已缓存的公开深度审阅；不会请求供应商或模型。</span>}{layer2Error && <span className="error-text">深度审阅缓存读取失败：{layer2Error}</span>}{!layer2Loading && !layer2Error && layer2Result?.status === "not_available" && <span className="placeholder">当前事件没有可用的 Layer 2 缓存；不会为界面发起供应商或深度模型请求。</span>}{!layer2Loading && !layer2Error && layer2Result?.status === "cached" && layer2Result.conclusion && <div className="market-layer2-conclusion">{layer2Result.conclusion.conclusion ? <p>{layer2Result.conclusion.conclusion}</p> : <span className="placeholder">已命中缓存，但其中没有可显示的公开结论。</span>}{layer2Result.conclusion.evidence_gaps.length > 0 && <p><span>证据缺口：</span>{layer2Result.conclusion.evidence_gaps.join("；")}</p>}{layer2Result.conclusion.material_risks.length > 0 && <p><span>关键风险：</span>{layer2Result.conclusion.material_risks.join("；")}</p>}</div>}</div>}
        </>
      )}
    </section>
  );
}
