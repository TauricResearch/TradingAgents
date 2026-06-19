import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchWatchlist, getAccuracyLeaderboard } from "../lib/api";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface DecisionAccuracyLeaderboardProps {
  onClose?: () => void;
}

interface TickerAccuracy {
  rank: number;
  ticker: string;
  companyName: string;
  total_runs: number;
  right: number;
  wrong: number;
  win_rate: number | null;
  accuracy_pct: number | null;
  avg_confidence: number | null;
  trending_accuracy: number | null;
  last_evaluated: string | null;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

/** Tailwind text color class for a given accuracy percentage. */
function accuracyColor(pct: number | null): string {
  if (pct == null) return "text-slate-500";
  if (pct >= 80) return "text-emerald-400";
  if (pct >= 50) return "text-amber-400";
  return "text-red-400";
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function DecisionAccuracyLeaderboard({
  onClose,
}: DecisionAccuracyLeaderboardProps) {
  const { data: watchlist = [], isLoading: watchlistLoading } = useQuery({
    queryKey: ["watchlist"],
    queryFn: fetchWatchlist,
  });

  const { data: agentData, isLoading: agentLoading, isError: agentError } = useQuery({
    queryKey: ["ticker-agent", "leaderboard"],
    queryFn: getAccuracyLeaderboard,
    refetchInterval: 30000,
  });

  const rows = useMemo(() => {
    if (!agentData?.scores) return [];

    const watchlistMap = new Map(watchlist.map((w) => [w.ticker, w.company_name]));
    const scores = agentData.scores as Record<string, Record<string, unknown>>;

    return Object.entries(scores)
      .filter(([, s]) => s && typeof s === "object")
      .map(([ticker, s], i) => ({
        rank: i + 1,
        ticker,
        companyName: watchlistMap.get(ticker) ?? "",
        total_runs: (s.total_runs as number) ?? 0,
        right: (s.right as number) ?? 0,
        wrong: (s.wrong as number) ?? 0,
        win_rate: (s.win_rate as number | null) ?? null,
        accuracy_pct: (s.accuracy_pct as number | null) ?? null,
        avg_confidence: (s.avg_confidence as number | null) ?? null,
        trending_accuracy: (s.trending_accuracy as number | null) ?? null,
        last_evaluated: (s.last_evaluated as string | null) ?? null,
      }))
      .sort((a, b) => {
        const aPct = a.accuracy_pct ?? -1;
        const bPct = b.accuracy_pct ?? -1;
        if (bPct !== aPct) return bPct - aPct;
        return b.total_runs - a.total_runs;
      });
  }, [agentData, watchlist]);

  const isLoading = watchlistLoading || agentLoading;

  return (
    <div className="glass-panel">
      {/* ── Header ── */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-700/50">
        <h3 className="section-header flex items-center gap-2 mb-0">
          <span className="w-1 h-1 rounded-full bg-emerald-400" />
          Decision Accuracy Leaderboard
        </h3>
        {onClose && (
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-300 transition-colors text-lg leading-none"
            aria-label="Close"
          >
            ×
          </button>
        )}
      </div>

      {/* ── Content ── */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 rounded-full border-2 border-sky-500/30 border-t-sky-400 animate-spin" />
        </div>
      ) : agentError ? (
        <div className="text-center py-12">
          <p className="text-sm text-red-400">Failed to load agent accuracy data.</p>
        </div>
      ) : rows.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-sm text-slate-500">No accuracy data yet. Run the Ticker Accuracy Agent to populate.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-800/60 text-slate-500 font-medium uppercase tracking-wider">
                <th className="px-4 py-2.5 text-left w-10">#</th>
                <th className="px-4 py-2.5 text-left">Ticker</th>
                <th className="px-4 py-2.5 text-left">Company</th>
                <th className="px-4 py-2.5 text-right">Runs</th>
                <th className="px-4 py-2.5 text-right">Wins</th>
                <th className="px-4 py-2.5 text-right">Losses</th>
                <th className="px-4 py-2.5 text-right">Accuracy</th>
                <th className="px-4 py-2.5 text-right">Trending</th>
                <th className="px-4 py-2.5 text-right">Confidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/40">
              {rows.map((row) => (
                <tr
                  key={row.ticker}
                  className="hover:bg-slate-800/20 transition-colors"
                >
                  <td className="px-4 py-2.5 text-slate-500">{row.rank}</td>
                  <td className="px-4 py-2.5">
                    <span className="font-semibold text-slate-100">
                      {row.ticker}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-slate-400 truncate max-w-[160px]">
                    {row.companyName || "—"}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <span className="data-text text-slate-300">
                      {row.total_runs}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <span className="data-text text-emerald-400">
                      {row.right}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <span className="data-text text-red-400">
                      {row.wrong}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <span className={`data-text ${accuracyColor(row.accuracy_pct)}`}>
                      {row.accuracy_pct != null ? `${row.accuracy_pct.toFixed(1)}%` : "—"}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <span className={`data-text ${accuracyColor(row.trending_accuracy)}`}>
                      {row.trending_accuracy != null ? `${row.trending_accuracy.toFixed(1)}%` : "—"}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <span className="data-text text-sky-400">
                      {row.avg_confidence != null
                        ? `${(row.avg_confidence * 100).toFixed(0)}%`
                        : "—"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}