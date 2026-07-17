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

import { fibPrices, pointToSegmentDistance, positionMetrics } from "./geometry";
import type { Drawing, DrawingPoint, PreviewState } from "./types";

export interface DrawingColors {
  line: string;
  fib: string;
  fibFill: string;
  label: string;
  bull: string;
  bear: string;
  bullFill: string;
  bearFill: string;
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
  fillColor?: string; // overrides fibFill for position-tool zones
  strokeColor?: string; // overrides the kind-derived stroke
  labelColor?: string;
  labelAlign?: "left"; // default: right-aligned ending at x2
}

export class DrawingsPrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null;
  private series: ISeriesApi<SeriesType> | null = null;
  private requestUpdateFn: (() => void) | null = null;
  private drawings: Drawing[] = [];
  private preview: PreviewState | null = null;
  // measure tool (chart Phase 2): ephemeral ruler, never persisted
  private measure: { a: DrawingPoint; b: DrawingPoint; label: string } | null =
    null;
  // fallbacks only — PriceChart overrides all of these with theme tokens
  // via setDrawings before anything is drawn
  private colors: DrawingColors = {
    line: "#2456c5",
    fib: "#8b610d",
    fibFill: "rgba(139,97,13,0.08)",
    label: "#646f84",
    bull: "#16824a",
    bear: "#c03434",
    bullFill: "rgba(22,130,74,0.10)",
    bearFill: "rgba(192,52,52,0.10)",
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
              ctx.fillStyle = seg.fillColor ?? source.colors.fibFill;
              ctx.fillRect(
                seg.x1 * hr,
                Math.min(seg.y1, seg.fillTo) * vr,
                (seg.x2 - seg.x1) * hr,
                Math.abs(seg.fillTo - seg.y1) * vr,
              );
            }
            ctx.beginPath();
            ctx.strokeStyle =
              seg.strokeColor ??
              (seg.kind === "fib" ? source.colors.fib : source.colors.line);
            ctx.lineWidth = (seg.kind === "preview" ? 1 : 1.5) * vr;
            ctx.setLineDash(
              seg.dashed || seg.kind === "preview" ? [4 * hr, 4 * hr] : [],
            );
            ctx.moveTo(seg.x1 * hr, seg.y1 * vr);
            ctx.lineTo(seg.x2 * hr, seg.y2 * vr);
            ctx.stroke();
            if (seg.label) {
              ctx.fillStyle = seg.labelColor ?? source.colors.label;
              ctx.fillText(
                seg.label,
                seg.labelAlign === "left"
                  ? seg.x1 * hr + 4 * hr
                  : seg.x2 * hr - ctx.measureText(seg.label).width - 4 * hr,
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

  /** Measure ruler: same imperative discipline as setPreview. The label
   * is computed by the caller (Δprice/Δ%/Δbars are presentation
   * arithmetic, not trading numbers). */
  setMeasure(
    measure: { a: DrawingPoint; b: DrawingPoint; label: string } | null,
  ): void {
    this.measure = measure;
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
      text?: string,
    ) => {
      const anchors = [...points];
      const required =
        realKind === "long" || realKind === "short" || realKind === "channel"
          ? 3
          : 2;
      if (cursor && anchors.length < required) anchors.push(cursor);
      if (realKind === "long" || realKind === "short") {
        this.pushPosition(segments, kind, realKind, anchors, width);
        return;
      }
      if (realKind === "rect") {
        this.pushRect(segments, kind, anchors);
        return;
      }
      if (realKind === "channel") {
        this.pushChannel(segments, kind, anchors);
        return;
      }
      if (realKind === "text") {
        const origin = anchors[0] && this.toCoord(anchors[0]);
        if (origin) {
          segments.push({
            kind,
            // 6px tick marks the anchor; the note reads to its right
            x1: origin.x, y1: origin.y,
            x2: origin.x + 6, y2: origin.y,
            label: text || "…",
            labelAlign: "left",
          });
        }
        return;
      }
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
      if (realKind === "vline") {
        const origin = this.toCoord(anchors[0]!);
        if (origin) {
          // full-pane vertical: a generous y-extent, clipped by the canvas
          segments.push({
            kind,
            x1: origin.x, y1: 0, x2: origin.x, y2: 10_000,
            dashed: true,
            label: new Date(anchors[0]!.time * 1000)
              .toISOString().slice(0, 10),
            labelAlign: "left",
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
      if (realKind === "arrow") {
        // shaft + two head strokes, computed in pixel space so the head
        // keeps its shape under zoom
        segments.push({ kind, x1: a.x, y1: a.y, x2: b.x, y2: b.y });
        const angle = Math.atan2(b.y - a.y, b.x - a.x);
        const head = 9;
        for (const spread of [Math.PI * 0.85, -Math.PI * 0.85]) {
          segments.push({
            kind,
            x1: b.x, y1: b.y,
            x2: b.x + head * Math.cos(angle + spread),
            y2: b.y + head * Math.sin(angle + spread),
          });
        }
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
      if (drawing.hidden) continue;
      pushDrawing(drawing.kind, drawing.kind, drawing.points, null, drawing.text);
    }
    if (this.preview) {
      pushDrawing("preview", this.preview.kind, this.preview.placed, this.preview.cursor);
    }
    if (this.measure) {
      const a = this.toCoord(this.measure.a);
      const b = this.toCoord(this.measure.b);
      if (a && b) {
        segments.push({
          kind: "preview",
          x1: a.x, y1: a.y, x2: b.x, y2: b.y,
          dashed: true,
          label: this.measure.label,
        });
      }
    }
    return segments;
  }

  /** Zone: fill between two corners with top/bottom edges — the way
   * traders mark supply/demand (side borders add noise, not meaning). */
  private pushRect(
    segments: Segment[],
    kind: Drawing["kind"] | "preview",
    anchors: DrawingPoint[],
  ): void {
    if (anchors.length < 2) return;
    const a = this.toCoord(anchors[0]!);
    const b = this.toCoord(anchors[1]!);
    if (!a || !b) return;
    const left = Math.min(a.x, b.x);
    const right = Math.max(a.x, b.x);
    const top = Math.min(a.y, b.y);
    const bottom = Math.max(a.y, b.y);
    const high = Math.max(anchors[0]!.price, anchors[1]!.price);
    const low = Math.min(anchors[0]!.price, anchors[1]!.price);
    segments.push({
      kind, x1: left, y1: top, x2: right, y2: top,
      fillTo: bottom, fillColor: this.colors.fibFill,
      label: `${low.toFixed(2)} – ${high.toFixed(2)}`,
    });
    segments.push({ kind, x1: left, y1: bottom, x2: right, y2: bottom });
  }

  /** Parallel channel: base line a→b plus its translate through c.
   * The offset is computed in DATA space (price at c minus the base
   * line's price at c's time), so the channel stays parallel under
   * pan/zoom — pixel-space offsets would shear. */
  private pushChannel(
    segments: Segment[],
    kind: Drawing["kind"] | "preview",
    anchors: DrawingPoint[],
  ): void {
    if (anchors.length < 2) return;
    const [p1, p2, p3] = anchors;
    const a = this.toCoord(p1!);
    const b = this.toCoord(p2!);
    if (!a || !b) return;
    segments.push({ kind, x1: a.x, y1: a.y, x2: b.x, y2: b.y });
    if (!p3) return;
    const dt = p2!.time - p1!.time;
    const slope = dt !== 0 ? (p2!.price - p1!.price) / dt : 0;
    const basePriceAtC = p1!.price + slope * (p3.time - p1!.time);
    const offset = p3.price - basePriceAtC;
    const a2 = this.toCoord({ time: p1!.time, price: p1!.price + offset });
    const b2 = this.toCoord({ time: p2!.time, price: p2!.price + offset });
    if (!a2 || !b2) return;
    // fillRect only draws axis-aligned rectangles: flat channels get the
    // faint band, slanted ones keep two clean rails (honest v1)
    const flat = a.y === b.y && a2.y === b2.y;
    segments.push({
      kind, x1: a2.x, y1: a2.y, x2: b2.x, y2: b2.y, dashed: true,
      ...(flat ? { fillTo: a.y, fillColor: this.colors.fibFill } : {}),
    });
  }

  /** Long/short position tool: entry line + stop zone + target zone from
   * anchor-x to the right edge, labeled with pure price geometry (R:R).
   * Sizing (account numbers) lives in the Workspace plan card, not here. */
  private pushPosition(
    segments: Segment[],
    kind: Drawing["kind"] | "preview",
    realKind: "long" | "short",
    anchors: DrawingPoint[],
    width: number,
  ): void {
    const entry = anchors[0] && this.toCoord(anchors[0]);
    if (!entry) return;
    const left = entry.x;
    const stroke = realKind === "long" ? this.colors.bull : this.colors.bear;
    // entry line always renders (even mid-placement)
    segments.push({
      kind, x1: left, y1: entry.y, x2: width, y2: entry.y,
      strokeColor: stroke,
      label: `${realKind.toUpperCase()} · entry ${anchors[0]!.price.toFixed(2)}`,
      labelColor: stroke,
    });
    const stop = anchors[1] && this.toCoord(anchors[1]);
    if (anchors[1] && stop) {
      segments.push({
        kind, x1: left, y1: stop.y, x2: width, y2: stop.y,
        strokeColor: this.colors.bear, dashed: true,
        fillTo: entry.y, fillColor: this.colors.bearFill,
        label: `stop ${anchors[1]!.price.toFixed(2)}`,
        labelColor: this.colors.bear,
      });
    }
    const target = anchors[2] && this.toCoord(anchors[2]);
    if (anchors[2] && target) {
      const metrics = positionMetrics(
        realKind, anchors[0]!.price, anchors[1]!.price, anchors[2]!.price,
      );
      segments.push({
        kind, x1: left, y1: target.y, x2: width, y2: target.y,
        strokeColor: this.colors.bull, dashed: true,
        fillTo: entry.y, fillColor: this.colors.bullFill,
        label: metrics.valid
          ? `target ${anchors[2]!.price.toFixed(2)} · R:R ${metrics.rr?.toFixed(2) ?? "—"}`
          : `target ${anchors[2]!.price.toFixed(2)} · invalid ${realKind} geometry`,
        labelColor: metrics.valid ? this.colors.bull : this.colors.bear,
      });
    }
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
    if (drawing.kind === "text") {
      const origin = this.toCoord(drawing.points[0]!);
      return origin ? Math.hypot(p.x - origin.x, p.y - origin.y) : null;
    }
    if (drawing.kind === "vline") {
      const origin = this.toCoord(drawing.points[0]!);
      return origin ? Math.abs(p.x - origin.x) : null;
    }
    if (drawing.kind === "rect") {
      const a = this.toCoord(drawing.points[0]!);
      const b = this.toCoord(drawing.points[1]!);
      if (!a || !b) return null;
      const inside =
        p.x >= Math.min(a.x, b.x) && p.x <= Math.max(a.x, b.x) &&
        p.y >= Math.min(a.y, b.y) && p.y <= Math.max(a.y, b.y);
      return inside ? 0 : null;
    }
    if (drawing.kind === "channel") {
      const [p1, p2, p3] = drawing.points;
      const a = this.toCoord(p1!);
      const b = this.toCoord(p2!);
      if (!a || !b) return null;
      let best = pointToSegmentDistance(p, a, b);
      if (p3) {
        const dt = p2!.time - p1!.time;
        const slope = dt !== 0 ? (p2!.price - p1!.price) / dt : 0;
        const offset = p3.price - (p1!.price + slope * (p3.time - p1!.time));
        const a2 = this.toCoord({ time: p1!.time, price: p1!.price + offset });
        const b2 = this.toCoord({ time: p2!.time, price: p2!.price + offset });
        if (a2 && b2) best = Math.min(best, pointToSegmentDistance(p, a2, b2));
      }
      return best;
    }
    if (drawing.kind === "long" || drawing.kind === "short") {
      // nearest of the three horizontal lines, from anchor-x rightward
      const entry = this.toCoord(drawing.points[0]!);
      if (!entry || p.x < entry.x - 4) return null;
      let best: number | null = null;
      for (const anchor of drawing.points) {
        const c = this.toCoord(anchor);
        if (!c) continue;
        const distance = Math.abs(p.y - c.y);
        if (best == null || distance < best) best = distance;
      }
      return best;
    }
    const a = this.toCoord(drawing.points[0]!);
    const b = this.toCoord(drawing.points[1]!);
    if (!a || !b) return null;
    if (drawing.kind === "trend" || drawing.kind === "arrow") {
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
