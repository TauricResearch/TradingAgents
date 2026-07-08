/** User annotations on price charts. Anchored in data space (time +
 * price) so they survive pan/zoom/timeframe switches. Pure geometry —
 * no derived trading numbers beyond the standard Fibonacci ratios. */

export interface DrawingPoint {
  time: number; // unix seconds (bar time)
  price: number;
}

export type DrawingKind = "trend" | "hray" | "fib";

export interface Drawing {
  id: string;
  kind: DrawingKind;
  /** trend/fib: exactly 2 anchors; hray: exactly 1 */
  points: DrawingPoint[];
}

export type ToolMode = "select" | "erase" | DrawingKind;

export const POINTS_REQUIRED: Record<DrawingKind, number> = {
  trend: 2,
  hray: 1,
  fib: 2,
};

export interface PreviewState {
  kind: DrawingKind;
  placed: DrawingPoint[];
  cursor: DrawingPoint | null;
}
