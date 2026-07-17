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
  | "vline"
  | "arrow"
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

// "alert" and "measure" are interactions, not persisted drawings: alert
// creates a price alert at the clicked level (A2); measure is a two-click
// ephemeral ruler (chart Phase 2). Neither enters the store, so they stay
// out of DrawingKind / POINTS_REQUIRED.
export type ToolMode = "select" | "erase" | "alert" | "measure" | DrawingKind;

export const POINTS_REQUIRED: Record<DrawingKind, number> = {
  trend: 2,
  hray: 1,
  vline: 1,
  arrow: 2,
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
