/** User annotations on price charts. Anchored in data space (time +
 * price) so they survive pan/zoom/timeframe switches. Pure geometry —
 * no derived trading numbers beyond the standard Fibonacci ratios. */

export interface DrawingPoint {
  time: number; // unix seconds (bar time)
  price: number;
}

export type DrawingKind =
  | "trend"
  | "hray"
  | "fib"
  | "long"
  | "short"
  | "rect"
  | "channel"
  | "text";

export interface Drawing {
  id: string;
  kind: DrawingKind;
  /** trend/fib/rect: exactly 2 anchors; hray/text: exactly 1;
   *  long/short: 3 (entry → stop → target);
   *  channel: 3 (base line a→b, then the parallel offset point) */
  points: DrawingPoint[];
  /** text notes only */
  text?: string;
  /** object list visibility toggle — hidden, never deleted */
  hidden?: boolean;
}

export type ToolMode = "select" | "erase" | DrawingKind;

export const POINTS_REQUIRED: Record<DrawingKind, number> = {
  trend: 2,
  hray: 1,
  fib: 2,
  long: 3,
  short: 3,
  rect: 2,
  channel: 3,
  text: 1,
};

export interface PreviewState {
  kind: DrawingKind;
  placed: DrawingPoint[];
  cursor: DrawingPoint | null;
}
