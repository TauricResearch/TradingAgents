import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { startRun, cancelRun, fetchTickerRuns, type RunRow } from "../lib/api";
import { useUi } from "../store/ui";
import { formatDuration } from "../lib/format";
import { useFocusedRunEvents } from "../hooks/useFocusedRunEvents";

interface Props {
  ticker: string;
  price?: number;
  changePct?: number;
  stale?: boolean;
}

function formatStartedAt(iso: string | null): string {
  if (!iso) return "(no timestamp)";
  // Local-time short form: YYYY-MM-DD HH:MM
  return iso.replace("T", " ").slice(0, 16);
}

function formatPrice(p: number | null | undefined): string | null {
  if (p == null) return null;
  return `$${p.toFixed(2)}`;
}

function formatTotalDuration(s: number | null | undefined): string | null {
  if (s == null) return null;
  return formatDuration(s * 1000);
}

export function runLabel(r: RunRow): string {
  const when = formatStartedAt(r.started_at);
  const action = r.decision_action ? ` — ${r.decision_action}` : "";
  const model = r.deep_think_model ? ` · ${r.deep_think_model}` : "";
  const price = formatPrice(r.start_price) ? ` · ${formatPrice(r.start_price)}` : "";
  const dur = formatTotalDuration(r.total_duration_s) ? ` · ${formatTotalDuration(r.total_duration_s)}` : "";
  return `${when}${action}${model}${price}${dur}`;
}

export function TickerHeader({ ticker, price, changePct, stale }: Props) {
  const qc = useQueryClient();
  const activeRunId = useUi((s) => s.activeRunIdByTicker[ticker] ?? null);
  const lastRunId = useUi((s) => s.lastRunIdByTicker[ticker] ?? null);
  const historicalRunId = useUi((s) => s.historicalRunIdByTicker[ticker] ?? null);
  const events = useFocusedRunEvents();
  const agentProgress = useMemo(() => {
    if (!activeRunId) return null;
    const started = new Set<string>();
    const completed = new Set<string>();
    for (const e of events) {
      const data = e.data as Record<string, unknown>;
      if (e.type === "analyst_started") {
        const node = String(data.node ?? "");
        if (node) started.add(node);
      } else if (e.type === "analyst_completed") {
        const node = String(data.node ?? "");
        if (node) completed.add(node);
      }
    }
    if (started.size === 0) return null;
    return { done: completed.size, total: started.size };
  }, [events, activeRunId]);

  const setActiveRunIdForTicker = useUi((s) => s.setActiveRunIdForTicker);
  const setLastRunIdForTicker = useUi((s) => s.setLastRunIdForTicker);
  const setHistoricalRunForTicker = useUi((s) => s.setHistoricalRunForTicker);
  const clearActiveRunForTicker = useUi((s) => s.clearActiveRunForTicker);
  const clearHistoricalRunForTicker = useUi((s) => s.clearHistoricalRunForTicker);
  const clearBuffer = useUi((s) => s.clearBuffer);

  const hasHistory = lastRunId != null;
  const tickerRuns = useQuery({
    queryKey: ["ticker-runs", ticker],
    queryFn: () => fetchTickerRuns(ticker),
    staleTime: 30_000,
    retry: false,
  });
  const hasAnyRuns = hasHistory || (Array.isArray(tickerRuns.data) && tickerRuns.data.length > 0);

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

  const onSelectHistorical = (id: string | null) => {
    if (id == null) {
      clearHistoricalRunForTicker(ticker);
    } else {
      setHistoricalRunForTicker(ticker, id);
    }
  };

  const actionLabel = start.isPending
    ? "Starting…"
    : hasHistoryForButton
    ? "Re-run analysis"
    : "Run analysis";

  return (
    <div className="flex items-center justify-between mb-5">
      <div>
        <div className="flex items-center gap-3">
          <h2 className="text-2xl font-display font-semibold text-slate-100 tracking-tight">{ticker}</h2>
          {agentProgress && (
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 text-[10px] font-mono font-semibold rounded-md bg-sky-500/10 text-sky-300 border border-sky-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse shadow-[0_0_4px_rgba(56,189,248,0.4)]" />
              {agentProgress.done}/{agentProgress.total} agents
            </span>
          )}
          {!stale && changePct != null && (
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs data-text font-medium rounded-md ${
              changePct >= 0
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                : 'bg-red-500/10 text-red-400 border border-red-500/20'
            }`}>
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d={changePct >= 0 ? "M4.5 10.5L12 3m0 0l7.5 7.5M12 3v18" : "M19.5 13.5L12 21m0 0l-7.5-7.5M12 21V3"} />
              </svg>
              {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
            </span>
          )}
          {stale && (
            <span data-testid="ticker-header-unavailable" className="text-xs font-medium text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-md">
              Price data unavailable
            </span>
          )}
        </div>
        <p className="text-sm text-slate-500 mt-1">
          {stale ? (
            <span className="text-amber-400/60">Unavailable on Yahoo Finance</span>
          ) : (
            <span className="data-text text-slate-400">
              {price != null ? `$${price.toFixed(2)}` : "—"}
              {' · '}USD
            </span>
          )}
        </p>
      </div>
      <div className="flex items-center gap-2">
        {hasAnyRuns && (
          <select
            aria-label="Run history"
            value={historicalRunId ?? "latest"}
            onChange={(e) => {
              const v = e.target.value;
              onSelectHistorical(v === "latest" ? null : v);
            }}
            className="px-2 py-1.5 text-sm bg-slate-800 border border-slate-700 rounded-lg text-slate-300 
                       focus:outline-none focus:ring-2 focus:ring-sky-500/30 focus:border-sky-500/30"
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
          className="btn-primary"
        >
          {start.isPending && (
            <svg className="inline w-3 h-3 mr-1.5 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" className="opacity-25" />
              <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
            </svg>
          )}
          {actionLabel}
        </button>
        {isRunning && (
          <button
            onClick={() => cancel.mutate()}
            className="btn-secondary"
          >
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}
