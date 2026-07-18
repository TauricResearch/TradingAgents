/** AI decision history painted on price (chart Phase 1): a clean, quiet
 * layer — one dashed entry-level line projected right from each decision
 * (the ▲/▼/✕ badges are LWC series markers), plus hit-testing so a click
 * can ask "explain this decision." The full plan (stop/targets) and regime
 * detail live behind the AI-Plan toggle and the explain card, not on the
 * chart.
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

export class AnnotationsPrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null;
  private series: ISeriesApi<SeriesType> | null = null;
  private requestUpdateFn: (() => void) | null = null;
  private annotations: SnappedAnnotation[] = [];
  private barTimes: number[] = [];
  private visible = true;
  // minimum on-pane length for an entry-level projection: a same-bar close
  // or a last-bar decision would otherwise collapse to zero width
  // (invisible + unclickable). Wide enough to see and to hit-test reliably.
  private static readonly MIN_PROJECTION_PX = 12;
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
  ): void {
    this.annotations = annotations;
    this.barTimes = barTimes;
    if (colors) this.colors = { ...this.colors, ...colors };
    this.requestUpdateFn?.();
  }

  /** Toggle the whole AI history layer — the "collapse it" the review
   * asked for. Hit-testing also respects this. */
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

  /** Entry-level projection from the decision bar rightward, in media x,
   * clamped to the pane. to=null (open) runs to the right edge; a same-bar
   * or last-bar decision gets a minimum length so it stays visible +
   * clickable. null if fully off-pane. */
  private projectionX(span: { from: number; to: number | null }):
    { x1: number; x2: number } | null {
    const width = this.width();
    const rawX1 = this.xOf(span.from);
    const lastTime = this.barTimes[this.barTimes.length - 1];
    const rawX2 = span.to == null
      ? width
      : this.xOf(Math.min(span.to, lastTime ?? span.to));
    if (rawX1 == null || rawX2 == null) return null;
    const x1 = Math.max(0, Math.min(width, rawX1));
    let x2 = Math.max(0, Math.min(width, rawX2));
    if (x2 <= 0 || x1 >= width) return null;
    if (x2 - x1 < AnnotationsPrimitive.MIN_PROJECTION_PX) {
      x2 = Math.min(width, x1 + AnnotationsPrimitive.MIN_PROJECTION_PX);
    }
    if (x2 <= x1) return null;
    return { x1, x2 };
  }

  /** The clean history layer (matches the mockup): a circular ▲/▼/✕ badge
   * on each decision plus, for executed plans, a colored dashed entry-level
   * line projected right. The full plan (stop/targets) lives behind the
   * AI-Plan toggle and the click-to-explain card, so history stays quiet. */
  private drawAll(
    ctx: CanvasRenderingContext2D, hr: number, vr: number,
  ): void {
    if (!this.visible || !this.series || this.annotations.length === 0) return;
    ctx.save();
    for (const a of this.annotations) {
      const x = this.xOf(a.time);
      if (x == null) continue;
      // executed plans: dashed entry-level projection + badge on the entry.
      // rejected: no plan line; badge sits on the bar's own price.
      const price = a.geometry
        ? a.geometry.entry
        : this.priceAt(a.time);
      if (price == null) continue;
      const y = this.series.priceToCoordinate(price);
      if (y == null) continue;
      const rejected = a.geometry == null;
      const color = rejected
        ? this.colors.neutral
        : a.geometry!.direction === "long"
          ? this.colors.bull
          : this.colors.bear;
      if (a.geometry && a.span) {
        const xs = this.projectionX(a.span);
        if (xs) {
          ctx.globalAlpha = a.span.to == null ? 0.9 : 0.4; // open brighter
          ctx.strokeStyle = color;
          ctx.lineWidth = 1.5 * vr;
          ctx.setLineDash([4 * hr, 3 * hr]);
          ctx.beginPath();
          ctx.moveTo(xs.x1 * hr, y * vr);
          ctx.lineTo(xs.x2 * hr, y * vr);
          ctx.stroke();
        }
      }
      this.drawBadge(ctx, hr, vr, x, y, color, a.action, rejected);
    }
    ctx.restore();
  }

  /** bar close at a snapped time (from the candle series) — the honest
   * price to anchor a rejected badge, which has no geometry. */
  private priceAt(time: number): number | null {
    const data = this.series?.data() as
      | ReadonlyArray<{ time: unknown; close?: number; value?: number }>
      | undefined;
    if (!data) return null;
    for (let i = data.length - 1; i >= 0; i--) {
      if (data[i]!.time === time) {
        return data[i]!.close ?? data[i]!.value ?? null;
      }
    }
    return null;
  }

  /** Circular decision badge: colored disc + white ring + white glyph
   * (▲ BUY / ▼ SELL / ✕ rejected). */
  private drawBadge(
    ctx: CanvasRenderingContext2D, hr: number, vr: number,
    x: number, y: number, color: string,
    action: SnappedAnnotation["action"], rejected: boolean,
  ): void {
    const cx = x * hr;
    const cy = y * vr;
    const R = 8 * vr;
    const g = 3.4 * vr;
    ctx.globalAlpha = 1;
    ctx.setLineDash([]);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.lineWidth = 2 * vr;
    ctx.strokeStyle = "rgba(255,255,255,0.95)";
    ctx.stroke();
    ctx.fillStyle = "#fff";
    ctx.strokeStyle = "#fff";
    ctx.beginPath();
    if (rejected) {
      ctx.lineWidth = 1.6 * vr;
      ctx.moveTo(cx - g, cy - g);
      ctx.lineTo(cx + g, cy + g);
      ctx.moveTo(cx + g, cy - g);
      ctx.lineTo(cx - g, cy + g);
      ctx.stroke();
    } else if (action === "BUY") {
      ctx.moveTo(cx, cy - g);
      ctx.lineTo(cx - g, cy + g);
      ctx.lineTo(cx + g, cy + g);
      ctx.closePath();
      ctx.fill();
    } else {
      ctx.moveTo(cx, cy + g);
      ctx.lineTo(cx - g, cy - g);
      ctx.lineTo(cx + g, cy - g);
      ctx.closePath();
      ctx.fill();
    }
  }

  /** Run whose badge (entry-bar vicinity) or dashed entry line contains the
   * point. (Named like DrawingsPrimitive.findNearest — LWC has its own
   * optional hitTest.) */
  findNearestRun(point: { x: number; y: number }, radius = 8): string | null {
    if (!this.visible || !this.series) return null;
    // entry-bar vicinity — covers the ▲/▼/✕ badge markers (y-independent)
    for (let i = this.annotations.length - 1; i >= 0; i--) {
      const a = this.annotations[i]!;
      const x = this.xOf(a.time);
      if (x != null && Math.abs(point.x - x) <= radius) return a.runId;
    }
    // the dashed entry-level projection line
    for (let i = this.annotations.length - 1; i >= 0; i--) {
      const a = this.annotations[i]!;
      if (!a.geometry || !a.span) continue;
      const xs = this.projectionX(a.span);
      if (!xs || point.x < xs.x1 || point.x > xs.x2) continue;
      const y = this.series.priceToCoordinate(a.geometry.entry);
      if (y != null && Math.abs(point.y - y) <= radius) return a.runId;
    }
    return null;
  }
}
