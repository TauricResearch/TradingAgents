import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { startRun, cancelRun, fetchTickerRuns, type RunRow } from "../lib/api";
import { useUi } from "../store/ui";

interface Props {
  ticker: string;
  price?: number;
  changePct?: number;
}

function formatStartedAt(iso: string | null): string {
  if (!iso) return "(no timestamp)";
  // Local-time short form: YYYY-MM-DD HH:MM
  return iso.replace("T", " ").slice(0, 16);
}

function runLabel(r: RunRow): string {
  const when = formatStartedAt(r.started_at);
  const action = r.decision_action ? ` — ${r.decision_action}` : "";
  return `${when}${action}`;
}

export function TickerHeader({ ticker, price, changePct }: Props) {
  const qc = useQueryClient();
  const activeRunId = useUi((s) => s.activeRunIdByTicker[ticker] ?? null);
  const lastRunId = useUi((s) => s.lastRunIdByTicker[ticker] ?? null);
  const historicalRunId = useUi((s) => s.historicalRunIdByTicker[ticker] ?? null);

  const setActiveRunIdForTicker = useUi((s) => s.setActiveRunIdForTicker);
  const setLastRunIdForTicker = useUi((s) => s.setLastRunIdForTicker);
  const clearActiveRunForTicker = useUi((s) => s.clearActiveRunForTicker);
  const clearHistoricalRunForTicker = useUi((s) => s.clearHistoricalRunForTicker);
  const clearBuffer = useUi((s) => s.clearBuffer);

  // Only load the per-ticker run list when the user has already
  // analyzed this ticker at least once. Avoids pointless /api/.../runs
  // hits for fresh tickers.
  const hasHistory = lastRunId != null;
  const tickerRuns = useQuery({
    queryKey: ["ticker-runs", ticker],
    queryFn: () => fetchTickerRuns(ticker),
    enabled: hasHistory,
    staleTime: 30_000,
  });

  const isRunning = !!activeRunId;
  // "Re-run" when prior history exists: the user already has a run to
  // compare against, so they're explicitly forcing a new one. First
  // visit (no history) is the regular "Run analysis" path.
  const hasHistoryForButton = hasHistory;

  const start = useMutation({
    mutationFn: () => startRun(ticker, hasHistoryForButton),
    onSuccess: ({ run_id }) => {
      clearBuffer();
      // Always clear any historical selection so the user sees the new
      // run live, not the older one they had selected.
      clearHistoricalRunForTicker(ticker);
      setActiveRunIdForTicker(ticker, run_id);
      setLastRunIdForTicker(ticker, run_id);
      qc.invalidateQueries({ queryKey: ["ticker-runs", ticker] });
      qc.invalidateQueries({ queryKey: ["runs", "list"] });
    },
  });

  const cancel = useMutation({
    mutationFn: () => cancelRun(activeRunId!),
    onSuccess: () => {
      // Optimistic clear: the server's run_failed will arrive over the
      // WS and is handled by useRunStream, but we don't want to leave
      // the UI showing "running" while that propagates.
      clearActiveRunForTicker(ticker);
    },
  });

  const onSelectHistorical = (id: number | null) => {
    if (id == null) {
      clearHistoricalRunForTicker(ticker);
    } else {
      useUi.getState().setHistoricalRunForTicker?.(ticker, id);
      // Fallback for store versions that don't have the action yet
      // (shouldn't happen on the deployed build, but keeps the
      // selector robust if the store migrates between releases).
      if (!useUi.getState().setHistoricalRunForTicker) {
        useUi.setState((s) => ({
          historicalRunIdByTicker: { ...s.historicalRunIdByTicker, [ticker]: id },
        }));
      }
    }
  };

  const actionLabel = start.isPending
    ? "Starting…"
    : hasHistoryForButton
    ? "Re-run analysis"
    : "Run analysis";

  return (
    <div className="flex items-center justify-between mb-4">
      <div>
        <h2 className="text-2xl font-semibold">{ticker}</h2>
        <p className="text-sm text-slate-500">
          {price != null ? `$${price.toFixed(2)}` : "—"}
          {changePct != null && (
            <span className={changePct >= 0 ? "text-emerald-600 ml-2" : "text-rose-600 ml-2"}>
              {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
            </span>
          )}
        </p>
      </div>
      <div className="flex items-center gap-2">
        {hasHistory && (
          <select
            aria-label="Run history"
            value={historicalRunId ?? "latest"}
            onChange={(e) => {
              const v = e.target.value;
              onSelectHistorical(v === "latest" ? null : Number(v));
            }}
            className="px-2 py-1.5 text-sm border border-slate-300 rounded-md bg-white"
          >
            <option value="latest">Latest (live)</option>
            {(Array.isArray(tickerRuns.data) ? tickerRuns.data : []).map((r) => (
              <option key={r.id} value={r.id}>
                {runLabel(r)}
              </option>
            ))}
          </select>
        )}
        <button
          disabled={isRunning || start.isPending}
          onClick={() => start.mutate()}
          className="px-3 py-1.5 text-sm font-medium rounded-md bg-blue-600 text-white disabled:opacity-50"
        >
          {actionLabel}
        </button>
        {isRunning && (
          <button
            onClick={() => cancel.mutate()}
            className="px-3 py-1.5 text-sm font-medium rounded-md border border-slate-300"
          >
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}
