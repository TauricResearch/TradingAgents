/** Trade replay: scrub the recorded run bar-by-bar and see equity, open
 * fills, and the AI's decision exactly as-of each revealed bar. Built entirely
 * from the per-run artifacts (equity + trades + decisions) — no extra backend
 * data. Reuses the market-replay controller (auto-pause on decisions). */
import { useMemo } from "react";

import { EquityCurve } from "@/components/charts/EquityCurve";
import { ReplayControls, useReplay } from "@/components/charts/ReplayController";
import {
  useBacktestDecisionsArtifact,
  useBacktestEquityArtifact,
  useBacktestTradesArtifact,
} from "@/lib/api/queries";
import type { BacktestDecisionRow, BacktestTrade } from "@/lib/api/types";
import { fmtPrice } from "@/lib/format";

type EquityRow = [string, number];

export interface ReplaySnapshot {
  time: string | null;
  equity: number | null;
  curve: number[];
  openFills: BacktestTrade[];
  closedCount: number;
  decision: BacktestDecisionRow | null;
}

/** As-of state at ``cursor`` visible rows (1..equity.length). Equity rows and
 * decision rows are 1:1 (one per decision), so row index i is the same in
 * both. A trade is open as-of t when it opened by t and hasn't closed yet. */
export function replayAsOf(
  equity: EquityRow[],
  trades: BacktestTrade[],
  decisions: BacktestDecisionRow[],
  cursor: number,
): ReplaySnapshot {
  const n = Math.max(0, Math.min(cursor, equity.length));
  const row = n > 0 ? equity[n - 1] : undefined;
  if (!row) {
    return { time: null, equity: null, curve: [], openFills: [], closedCount: 0, decision: null };
  }
  const [time, equityValue] = row;
  const curve = equity.slice(0, n).map(([, v]) => v);
  const openFills = trades.filter(
    (t) => t.opened_at != null && t.opened_at <= time &&
      (t.closed_at == null || t.closed_at > time),
  );
  const closedCount = trades.filter(
    (t) => t.closed_at != null && t.closed_at <= time,
  ).length;
  return {
    time,
    equity: equityValue,
    curve,
    openFills,
    closedCount,
    decision: decisions[n - 1] ?? null,
  };
}

/** 0-based indices of decisions that executed — the bars replay pauses on. */
export function executedBars(decisions: BacktestDecisionRow[]): Set<number> {
  const out = new Set<number>();
  decisions.forEach((d, i) => {
    if (d.outcome === "executed") out.add(i);
  });
  return out;
}

export function BacktestReplay({ runId }: { runId: string }) {
  const equityQ = useBacktestEquityArtifact(runId);
  const tradesQ = useBacktestTradesArtifact(runId);
  const decisionsQ = useBacktestDecisionsArtifact(runId);

  // memoize the defaulted arrays so their identity is stable across renders
  // (otherwise the `?? []` fallback churns the downstream useMemo deps)
  const equity = useMemo(() => (equityQ.data ?? []) as EquityRow[], [equityQ.data]);
  const trades = useMemo(() => tradesQ.data ?? [], [tradesQ.data]);
  const decisions = useMemo(() => decisionsQ.data ?? [], [decisionsQ.data]);
  const decisionBars = useMemo(() => executedBars(decisions), [decisions]);

  const replay = useReplay(equity.length, decisionBars);
  const snap = useMemo(
    () => replayAsOf(equity, trades, decisions, replay.cursor),
    [equity, trades, decisions, replay.cursor],
  );

  if (equity.length < 10) {
    return (
      <div className="text-xs text-fg-subtle" data-testid="backtest-replay-empty">
        Replay needs a run with recorded per-decision equity.
      </div>
    );
  }

  return (
    <div className="space-y-2" data-testid="backtest-replay">
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs font-semibold text-fg-muted">Trade replay</div>
        <ReplayControls
          replay={replay}
          totalBars={equity.length}
          cursorLabel={snap.time ? snap.time.slice(0, 10) : null}
        />
      </div>
      {snap.curve.length >= 2 && <EquityCurve curve={snap.curve} height={150} />}
      <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <ReplayStat label="As-of" value={snap.time ? snap.time.slice(0, 10) : "—"} />
        <ReplayStat label="Equity" value={fmtPrice(snap.equity, 0)} />
        <ReplayStat label="Open" value={String(snap.openFills.length)} />
        <ReplayStat label="Closed" value={String(snap.closedCount)} />
      </div>
      {snap.decision && (
        <div
          className="rounded-lg border border-border bg-surface-2 p-2 text-xs"
          data-testid="backtest-replay-decision"
        >
          <span className="font-semibold">
            {snap.decision.action ?? "hold"}
          </span>{" "}
          · {snap.decision.outcome}
          {snap.decision.regime && <> · regime {snap.decision.regime}</>}
          {snap.decision.confidence != null && (
            <> · conf {(snap.decision.confidence * 100).toFixed(0)}%</>
          )}
          {snap.decision.reasons && (
            <div className="mt-0.5 text-fg-subtle">{snap.decision.reasons}</div>
          )}
        </div>
      )}
      {snap.openFills.length > 0 && (
        <div className="text-xs text-fg-subtle" data-testid="backtest-replay-fills">
          Open:{" "}
          {snap.openFills
            .map((t) => `${t.side} ${fmtPrice(t.entry_price)}`)
            .join(" · ")}
        </div>
      )}
    </div>
  );
}

function ReplayStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface-2 px-2 py-1">
      <div className="text-fg-subtle">{label}</div>
      <div className="font-semibold tabular">{value}</div>
    </div>
  );
}

/** Open the generated report file in a new tab, fetching with auth headers so
 * it works under both cookie and X-API-Key sessions (a bare <a> would drop the
 * key). */
export async function openReportFile(runId: string, name: string): Promise<void> {
  const { apiHeaders } = await import("@/lib/api/client");
  const res = await fetch(`/api/backtest/runs/${runId}/${name}`, {
    headers: apiHeaders(),
  });
  if (!res.ok) return;
  const url = URL.createObjectURL(await res.blob());
  window.open(url, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
