/** Pure drawing math — unit-tested, no chart dependencies. */

export const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1] as const;

/** Retracement prices between two anchor prices. Level 0 sits at the
 * second anchor (the retracement origin), level 1 at the first — the
 * TradingView convention. */
export function fibPrices(
  priceA: number,
  priceB: number,
): { level: number; price: number }[] {
  return FIB_LEVELS.map((level) => ({
    level,
    price: priceB + (priceA - priceB) * level,
  }));
}

export interface XY {
  x: number;
  y: number;
}

/** Distance from point p to segment ab (pixels). Degenerate segments
 * collapse to point distance. */
export function pointToSegmentDistance(p: XY, a: XY, b: XY): number {
  const abx = b.x - a.x;
  const aby = b.y - a.y;
  const lengthSquared = abx * abx + aby * aby;
  if (lengthSquared === 0) return Math.hypot(p.x - a.x, p.y - a.y);
  let t = ((p.x - a.x) * abx + (p.y - a.y) * aby) / lengthSquared;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(p.x - (a.x + t * abx), p.y - (a.y + t * aby));
}

/** Distance to a rightward horizontal ray starting at `origin`. */
export function pointToRayDistance(p: XY, origin: XY, rightEdgeX: number): number {
  return pointToSegmentDistance(p, origin, { x: rightEdgeX, y: origin.y });
}
