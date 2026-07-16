/** Pane-height persistence (review P2.3): user-dragged pane proportions
 * survive indicator toggles and reloads. Keyed by pane COUNT — the same
 * layout shape restores the same proportions regardless of which
 * oscillators are showing (per-indicator keys would fragment endlessly). */

const STORAGE_KEY = "pro-pane-factors";

type FactorMap = Record<string, number[]>;

function read(): FactorMap {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : null;
    return parsed && typeof parsed === "object" ? (parsed as FactorMap) : {};
  } catch {
    return {};
  }
}

export function loadPaneFactors(paneCount: number): number[] | null {
  const factors = read()[String(paneCount)];
  return Array.isArray(factors) && factors.length === paneCount &&
    factors.every((f) => Number.isFinite(f) && f > 0)
    ? factors
    : null;
}

export function savePaneFactors(paneCount: number, factors: number[]): void {
  if (factors.length !== paneCount || factors.some((f) => !Number.isFinite(f) || f <= 0))
    return;
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ ...read(), [String(paneCount)]: factors }),
    );
  } catch {
    /* storage full/blocked — proportions just won't persist */
  }
}
