/** Lightweight Charts v5 series primitive rendering user drawings on
 * the price pane: trend segments, horizontal rays, fib retracements,
 * plus the in-progress placement preview. Anchors convert through the
 * chart's own scales every frame, so drawings stick to data under
 * pan/zoom. Anchors scrolled out of the visible range skip rendering
 * for that frame (known v1 limit, documented). */
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

import { fibPrices } from "./geometry";
import type { Drawing, DrawingPoint, PreviewState } from "./types";

export interface DrawingColors {
  line: string;
  fib: string;
  fibFill: string;
  label: string;
}

interface Segment {
  kind: Drawing["kind"] | "preview";
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  label?: string;
  dashed?: boolean;
  fillTo?: number; // y of previous fib level, for band fill
}

export class DrawingsPrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null;
  private series: ISeriesApi<SeriesType> | null = null;
  private requestUpdateFn: (() => void) | null = null;
  private drawings: Drawing[] = [];
  private preview: PreviewState | null = null;
  // fallbacks only — PriceChart overrides all of these with theme tokens
  // via setDrawings before anything is drawn
  private colors: DrawingColors = {
    line: "#2456c5",
    fib: "#8b610d",
    fibFill: "rgba(139,97,13,0.08)",
    label: "#646f84",
  };
  private paneView: IPrimitivePaneView;

  constructor() {
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    const source = this;
    const renderer: IPrimitivePaneRenderer = {
      draw(target: CanvasRenderingTarget2D) {
        const segments = source.computeSegments();
        if (segments.length === 0) return;
        target.useBitmapCoordinateSpace((scope) => {
          const ctx = scope.context;
          const hr = scope.horizontalPixelRatio;
          const vr = scope.verticalPixelRatio;
          ctx.save();
          ctx.font = `${Math.round(10 * vr)}px ui-monospace, monospace`;
          for (const seg of segments) {
            if (seg.fillTo != null) {
              ctx.fillStyle = source.colors.fibFill;
              ctx.fillRect(
                seg.x1 * hr,
                Math.min(seg.y1, seg.fillTo) * vr,
                (seg.x2 - seg.x1) * hr,
                Math.abs(seg.fillTo - seg.y1) * vr,
              );
            }
            ctx.beginPath();
            ctx.strokeStyle =
              seg.kind === "fib" ? source.colors.fib : source.colors.line;
            ctx.lineWidth = (seg.kind === "preview" ? 1 : 1.5) * vr;
            ctx.setLineDash(
              seg.dashed || seg.kind === "preview" ? [4 * hr, 4 * hr] : [],
            );
            ctx.moveTo(seg.x1 * hr, seg.y1 * vr);
            ctx.lineTo(seg.x2 * hr, seg.y2 * vr);
            ctx.stroke();
            if (seg.label) {
              ctx.fillStyle = source.colors.label;
              ctx.fillText(
                seg.label,
                seg.x2 * hr - ctx.measureText(seg.label).width - 4 * hr,
                seg.y2 * vr - 3 * vr,
              );
            }
          }
          ctx.restore();
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

  setDrawings(drawings: Drawing[], colors?: Partial<DrawingColors>): void {
    this.drawings = drawings;
    if (colors) this.colors = { ...this.colors, ...colors };
    this.requestUpdateFn?.();
  }

  /** Imperative: called from raw mouse handlers — the placement preview
   * must never round-trip through React state (a re-render per mousemove
   * disrupts the chart's own click/tap tracking). */
  setPreview(preview: PreviewState | null): void {
    this.preview = preview;
    this.requestUpdateFn?.();
  }

  /** media-space coordinates or null when the anchor is off-scale */
  toCoord(point: DrawingPoint): { x: number; y: number } | null {
    if (!this.chart || !this.series) return null;
    const x = this.chart.timeScale().timeToCoordinate(point.time as Time);
    const y = this.series.priceToCoordinate(point.price);
    if (x == null || y == null) return null;
    return { x, y };
  }

  paneWidth(): number {
    return this.chart?.timeScale().width() ?? 0;
  }

  /** Exposed for hit-testing (erase mode) and the renderer. */
  computeSegments(): Segment[] {
    const segments: Segment[] = [];
    const width = this.paneWidth();

    const pushDrawing = (
      kind: Drawing["kind"] | "preview",
      realKind: Drawing["kind"],
      points: DrawingPoint[],
      cursor: DrawingPoint | null = null,
    ) => {
      const anchors = [...points];
      if (cursor && anchors.length === 1) anchors.push(cursor);
      if (realKind === "hray") {
        const origin = this.toCoord(anchors[0]!);
        if (origin) {
          segments.push({
            kind,
            x1: origin.x,
            y1: origin.y,
            x2: width,
            y2: origin.y,
            dashed: true,
            label: anchors[0]!.price.toFixed(2),
          });
        }
        return;
      }
      if (anchors.length < 2) return;
      const a = this.toCoord(anchors[0]!);
      const b = this.toCoord(anchors[1]!);
      if (!a || !b) return;
      if (realKind === "trend") {
        segments.push({ kind, x1: a.x, y1: a.y, x2: b.x, y2: b.y });
        return;
      }
      // fib: level lines spanning the anchor x-range, extended right
      const left = Math.min(a.x, b.x);
      let previousY: number | null = null;
      for (const { level, price } of fibPrices(
        anchors[0]!.price,
        anchors[1]!.price,
      )) {
        const y = this.series?.priceToCoordinate(price);
        if (y == null) {
          previousY = null;
          continue;
        }
        segments.push({
          kind: "fib",
          x1: left,
          y1: y,
          x2: width,
          y2: y,
          label: `${level} · ${price.toFixed(2)}`,
          dashed: level !== 0 && level !== 1,
          fillTo: previousY ?? undefined,
        });
        previousY = y;
      }
    };

    for (const drawing of this.drawings) {
      pushDrawing(drawing.kind, drawing.kind, drawing.points);
    }
    if (this.preview) {
      pushDrawing("preview", this.preview.kind, this.preview.placed, this.preview.cursor);
    }
    return segments;
  }

  /** Nearest drawing within `radius` px of the media-space point.
   * (Named to avoid ISeriesPrimitive's own optional hitTest(x, y).) */
  findNearest(point: { x: number; y: number }, radius = 8): string | null {
    let bestId: string | null = null;
    let bestDistance = radius;
    for (const drawing of this.drawings) {
      const distance = this.distanceTo(drawing, point);
      if (distance != null && distance <= bestDistance) {
        bestDistance = distance;
        bestId = drawing.id;
      }
    }
    return bestId;
  }

  private distanceTo(
    drawing: Drawing,
    p: { x: number; y: number },
  ): number | null {
    const width = this.paneWidth();
    if (drawing.kind === "hray") {
      const origin = this.toCoord(drawing.points[0]!);
      if (!origin) return null;
      // rightward ray
      if (p.x < origin.x - 4) return null;
      return Math.abs(p.y - origin.y);
    }
    const a = this.toCoord(drawing.points[0]!);
    const b = this.toCoord(drawing.points[1]!);
    if (!a || !b) return null;
    if (drawing.kind === "trend") {
      const abx = b.x - a.x;
      const aby = b.y - a.y;
      const lengthSquared = abx * abx + aby * aby || 1;
      let t = ((p.x - a.x) * abx + (p.y - a.y) * aby) / lengthSquared;
      t = Math.max(0, Math.min(1, t));
      return Math.hypot(p.x - (a.x + t * abx), p.y - (a.y + t * aby));
    }
    // fib: nearest level line, active from min-x to the right edge
    const left = Math.min(a.x, b.x);
    if (p.x < left - 4 || p.x > width) return null;
    let best: number | null = null;
    for (const { price } of fibPrices(drawing.points[0]!.price, drawing.points[1]!.price)) {
      const y = this.series?.priceToCoordinate(price);
      if (y == null) continue;
      const distance = Math.abs(p.y - y);
      if (best == null || distance < best) best = distance;
    }
    return best;
  }
}
