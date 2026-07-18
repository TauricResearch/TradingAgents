/** AI decision history painted on price (chart Phase 1): time-bounded
 * entry/stop/target zones per decision run, a regime+confidence ribbon,
 * and hit-testing so a click can ask "explain this decision."
 *
 * All numbers come from the backend record (Constraint 2) — this layer
 * only converts them to pixels. Times must be pre-snapped to exact bar
 * times (LWC v5); x-coordinates go through logicalToCoordinate on the
 * bar index so spans clamp cleanly instead of vanishing when an edge
 * scrolls out of the visible range. */
import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type {
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from "lightweight-charts";

export interface SnappedAnnotation {
  runId: string;
  /** snapped bar time of the run */
  time: number;
  action: "BUY" | "SELL" | "HOLD" | null;
  rejectedAt: string | null;
  confidence: number | null;
  regime: string | null;
  geometry: {
    entry: number;
    stop: number | null;
    invalidation: number | null;
    takeProfits: { price: number; sizeFraction: number }[];
    direction: "long" | "short";
  } | null;
  /** snapped span; to=null extends to the last bar */
  span: { from: number; to: number | null } | null;
}

export interface AnnotationColors {
  bull: string;
  bear: string;
  neutral: string;
  label: string;
  bullFill: string;
  bearFill: string;
}

const RIBBON_HEIGHT = 6;
const RIBBON_HIT = 12;

/** regime -> which theme color keys the ribbon segment. */
function regimeColorKey(regime: string | null): keyof AnnotationColors {
  if (!regime) return "label";
  if (regime.includes("trend") || regime.includes("bull")) return "bull";
  if (regime.includes("volatil") || regime.includes("bear")) return "bear";
  return "neutral";
}

export class AnnotationsPrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null;
  private series: ISeriesApi<SeriesType> | null = null;
  private requestUpdateFn: (() => void) | null = null;
  private annotations: SnappedAnnotation[] = [];
  private barTimes: number[] = [];
  private cadenceLabel = "";
  private visible = true;
  // above this many zones in view, older ones collapse to an entry tick so
  // dense clusters stay readable (V4: "zones overlap into visual mud")
  private static readonly DENSITY_LIMIT = 8;
  private static readonly FULL_WHEN_DENSE = 4;
  // fallbacks only — PriceChart pushes theme tokens before first draw
  private colors: AnnotationColors = {
    bull: "#16824a",
    bear: "#c03434",
    neutral: "#8b610d",
    label: "#646f84",
    bullFill: "rgba(22,130,74,0.08)",
    bearFill: "rgba(192,52,52,0.08)",
  };
  private paneView: IPrimitivePaneView;

  constructor() {
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    const source = this;
    const renderer: IPrimitivePaneRenderer = {
      draw(target: CanvasRenderingTarget2D) {
        target.useBitmapCoordinateSpace((scope) => {
          source.drawAll(scope.context, scope.horizontalPixelRatio,
            scope.verticalPixelRatio);
        });
      },
    };
    this.paneView = { renderer: () => renderer };
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this.chart = param.chart;
    this.series = param.series;
    this.requestUpdateFn = param.requestUpdate;
  }

  detached(): void {
    this.chart = null;
    this.series = null;
    this.requestUpdateFn = null;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return [this.paneView];
  }

  setAnnotations(
    annotations: SnappedAnnotation[],
    barTimes: number[],
    colors?: Partial<AnnotationColors>,
    cadenceLabel?: string,
  ): void {
    this.annotations = annotations;
    this.barTimes = barTimes;
    if (colors) this.colors = { ...this.colors, ...colors };
    if (cadenceLabel != null) this.cadenceLabel = cadenceLabel;
    this.requestUpdateFn?.();
  }

  /** Toggle the whole AI layer (zones + ribbon) — the "collapse it" the
   * review asked for. Hit-testing also respects this. */
  setVisible(on: boolean): void {
    if (this.visible === on) return;
    this.visible = on;
    this.requestUpdateFn?.();
  }

  /** x of a snapped bar time via its logical index — defined (and
   * clampable) even when the bar is scrolled out of view. */
  private xOf(time: number): number | null {
    if (!this.chart) return null;
    const idx = this.barIndex(time);
    if (idx == null) return null;
    const x = this.chart.timeScale().logicalToCoordinate(idx as never);
    return x == null ? null : x;
  }

  private barIndex(time: number): number | null {
    const times = this.barTimes;
    let lo = 0;
    let hi = times.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (times[mid] === time) return mid;
      if (times[mid]! < time) lo = mid + 1;
      else hi = mid - 1;
    }
    return null;
  }

  private width(): number {
    return this.chart?.timeScale().width() ?? 0;
  }

  /** Span edges in media x, clamped to the pane; null if fully off-pane. */
  private spanX(span: { from: number; to: number | null }):
    { x1: number; x2: number } | null {
    const width = this.width();
    const rawX1 = this.xOf(span.from);
    const lastTime = this.barTimes[this.barTimes.length - 1];
    const rawX2 = span.to == null
      ? width
      : this.xOf(Math.min(span.to, lastTime ?? span.to));
    if (rawX1 == null || rawX2 == null) return null;
    const x1 = Math.max(0, Math.min(width, rawX1));
    const x2 = Math.max(0, Math.min(width, rawX2));
    if (x2 <= 0 || x1 >= width || x2 <= x1) return null;
    return { x1, x2 };
  }

  private drawAll(
    ctx: CanvasRenderingContext2D, hr: number, vr: number,
  ): void {
    if (!this.visible || !this.series || this.annotations.length === 0) return;
    ctx.save();
    ctx.font = `${Math.round(9 * vr)}px ui-monospace, monospace`;
    this.drawRibbon(ctx, hr, vr);
    // decision zones actually in view, oldest→newest
    const inView = this.annotations.filter(
      (a) => a.geometry && a.span && this.spanX(a.span),
    );
    // when dense, only the newest FULL_WHEN_DENSE keep full bands; older
    // ones collapse to an entry tick (still clickable via findNearestRun)
    const dense = inView.length > AnnotationsPrimitive.DENSITY_LIMIT;
    const fullFrom = dense
      ? inView.length - AnnotationsPrimitive.FULL_WHEN_DENSE
      : 0;
    inView.forEach((a, i) => {
      const xs = this.spanX(a.span!)!;
      if (dense && i < fullFrom) this.drawTick(ctx, hr, vr, a, xs.x1);
      else this.drawZone(ctx, hr, vr, a, xs.x1, xs.x2);
    });
    ctx.restore();
  }

  /** Collapsed representation for dense clusters: just the entry line +
   * short label at the decision bar. */
  private drawTick(
    ctx: CanvasRenderingContext2D, hr: number, vr: number,
    a: SnappedAnnotation, x1: number,
  ): void {
    const entryY = this.series!.priceToCoordinate(a.geometry!.entry);
    if (entryY == null) return;
    const color =
      a.geometry!.direction === "long" ? this.colors.bull : this.colors.bear;
    this.line(ctx, hr, vr, x1, x1 + 8, entryY, color, false);
    ctx.fillStyle = color;
    ctx.fillText(a.action ?? "", x1 * hr + 10 * hr, entryY * vr - 2 * vr);
  }

  private line(
    ctx: CanvasRenderingContext2D, hr: number, vr: number,
    x1: number, x2: number, y: number, color: string, dashed: boolean,
  ): void {
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1 * vr;
    ctx.setLineDash(dashed ? [3 * hr, 3 * hr] : []);
    ctx.moveTo(x1 * hr, y * vr);
    ctx.lineTo(x2 * hr, y * vr);
    ctx.stroke();
  }

  private drawZone(
    ctx: CanvasRenderingContext2D, hr: number, vr: number,
    a: SnappedAnnotation, x1: number, x2: number,
  ): void {
    const g = a.geometry!;
    const yOf = (price: number | null) =>
      price == null ? null : this.series!.priceToCoordinate(price);
    const entryY = yOf(g.entry);
    if (entryY == null) return;
    const sideColor = g.direction === "long" ? this.colors.bull : this.colors.bear;

    const stopY = yOf(g.stop);
    if (stopY != null) {
      ctx.fillStyle = this.colors.bearFill;
      ctx.fillRect(x1 * hr, Math.min(entryY, stopY) * vr,
        (x2 - x1) * hr, Math.abs(stopY - entryY) * vr);
      this.line(ctx, hr, vr, x1, x2, stopY, this.colors.bear, true);
    }
    const firstTp = g.takeProfits[0];
    const tp0Y = firstTp ? yOf(firstTp.price) : null;
    if (tp0Y != null) {
      ctx.fillStyle = this.colors.bullFill;
      ctx.fillRect(x1 * hr, Math.min(entryY, tp0Y) * vr,
        (x2 - x1) * hr, Math.abs(tp0Y - entryY) * vr);
    }
    for (const tp of g.takeProfits) {
      const y = yOf(tp.price);
      if (y != null) this.line(ctx, hr, vr, x1, x2, y, this.colors.bull, true);
    }
    const invY = yOf(g.invalidation);
    if (invY != null) {
      this.line(ctx, hr, vr, x1, x2, invY, this.colors.label, true);
    }
    this.line(ctx, hr, vr, x1, x2, entryY, sideColor, false);
    ctx.fillStyle = sideColor;
    const label = `${a.action} ${g.entry.toFixed(2)}${
      a.confidence != null ? ` · ${a.confidence}%` : ""}`;
    ctx.fillText(label, x1 * hr + 3 * hr, entryY * vr - 3 * vr);
  }

  /** Regime + confidence ribbon pinned to the top of the price pane; the
   * cadence label states the honest granularity of the segments. */
  private drawRibbon(
    ctx: CanvasRenderingContext2D, hr: number, vr: number,
  ): void {
    const width = this.width();
    let drewAny = false;
    for (let i = 0; i < this.annotations.length; i++) {
      const a = this.annotations[i]!;
      const x1 = this.xOf(a.time);
      if (x1 == null) continue;
      const next = this.annotations[i + 1];
      const x2 = next ? (this.xOf(next.time) ?? width) : width;
      const left = Math.max(0, Math.min(width, x1));
      const right = Math.max(0, Math.min(width, x2));
      if (right <= left) continue;
      const alpha = a.rejectedAt
        ? 0.12
        : 0.15 + 0.5 * ((a.confidence ?? 40) / 100);
      ctx.globalAlpha = alpha;
      ctx.fillStyle = this.colors[regimeColorKey(a.regime)];
      ctx.fillRect(left * hr, 0, (right - left) * hr, RIBBON_HEIGHT * vr);
      ctx.globalAlpha = 1;
      drewAny = true;
    }
    if (drewAny && this.cadenceLabel) {
      ctx.fillStyle = this.colors.label;
      ctx.fillText(this.cadenceLabel, 4 * hr, (RIBBON_HEIGHT + 9) * vr);
    }
  }

  /** Run whose zone, entry-bar vicinity, or ribbon segment contains the
   * point. (Named like DrawingsPrimitive.findNearest — LWC has its own
   * optional hitTest.) */
  findNearestRun(point: { x: number; y: number }, radius = 6): string | null {
    if (!this.visible || !this.series) return null;
    // ribbon: any annotation whose x-segment contains the point
    if (point.y <= RIBBON_HIT) {
      const width = this.width();
      for (let i = this.annotations.length - 1; i >= 0; i--) {
        const a = this.annotations[i]!;
        const x1 = this.xOf(a.time);
        if (x1 == null) continue;
        const next = this.annotations[i + 1];
        const x2 = next ? (this.xOf(next.time) ?? width) : width;
        if (point.x >= x1 && point.x <= x2) return a.runId;
      }
    }
    // entry-bar vicinity (covers the BUY/SELL/rejected markers LWC draws)
    for (let i = this.annotations.length - 1; i >= 0; i--) {
      const a = this.annotations[i]!;
      const x = this.xOf(a.time);
      if (x != null && Math.abs(point.x - x) <= radius) return a.runId;
    }
    // zone containment: newest first so overlapping spans prefer recency
    for (let i = this.annotations.length - 1; i >= 0; i--) {
      const a = this.annotations[i]!;
      if (!a.geometry || !a.span) continue;
      const xs = this.spanX(a.span);
      if (!xs || point.x < xs.x1 || point.x > xs.x2) continue;
      const ys: number[] = [];
      for (const price of [
        a.geometry.entry, a.geometry.stop,
        ...a.geometry.takeProfits.map((tp) => tp.price),
      ]) {
        if (price == null) continue;
        const y = this.series.priceToCoordinate(price);
        if (y != null) ys.push(y);
      }
      if (ys.length < 2) continue;
      const top = Math.min(...ys);
      const bottom = Math.max(...ys);
      if (point.y >= top - radius && point.y <= bottom + radius) {
        return a.runId;
      }
    }
    return null;
  }
}
