/** "Since you left" derivations (review P1.5): the marker widget counted
 * new runs but never said when the AI CHANGED ITS MIND — the single most
 * decision-relevant diff for a returning trader. */

export interface RunLike {
  run_id: string;
  symbol: string;
  action?: string | null;
  started_at: string;
}

export interface StanceFlip {
  symbol: string;
  from: string;
  to: string;
  run_id: string;
}

/** Per symbol: the last decided stance before the marker vs the latest
 * stance now. Rejected/undecided runs (action == null) don't count as a
 * stance. Runs are expected oldest-first (API order); we scan directly. */
export function computeStanceFlips(
  runs: readonly RunLike[],
  since: Date,
): StanceFlip[] {
  const before = new Map<string, string>();
  const after = new Map<string, { action: string; run_id: string }>();
  for (const run of runs) {
    if (!run.action) continue;
    if (new Date(run.started_at) <= since) {
      before.set(run.symbol, run.action);
    } else {
      after.set(run.symbol, { action: run.action, run_id: run.run_id });
    }
  }
  const flips: StanceFlip[] = [];
  for (const [symbol, latest] of after) {
    const prior = before.get(symbol);
    if (prior && prior !== latest.action) {
      flips.push({
        symbol,
        from: prior,
        to: latest.action,
        run_id: latest.run_id,
      });
    }
  }
  return flips.sort((a, b) => a.symbol.localeCompare(b.symbol));
}
