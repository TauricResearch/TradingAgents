import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchWatchlist, fetchPrices } from "../lib/api";
import { useUi } from "../store/ui";
import type { WsEvent } from "../lib/events";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface DecisionAccuracyLeaderboardProps {
  onClose?: () => void;
}

interface PriceData {
  price: number;
  change_pct: number;
  sparkline: number[];
  stale: boolean;
}

interface DecisionData {
  action: string;
  target: number;
  rationale: string;
  confidence: number;
}

interface TickerAccuracy {
  rank: number;
  ticker: string;
  companyName: string;
  totalDecisions: number;
  wins: number;
  losses: number;
  winRate: number | null;
  avgConfidence: number | null;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

/** Classify a single decision outcome based on price movement. */
function classifyOutcome(
  action: string,
  changePct: number,
): "win" | "loss" | "neutral" {
  if (action === "BUY") return changePct > 0 ? "win" : "loss";
  if (action === "SELL") return changePct < 0 ? "win" : "loss";
  return "neutral";
}

/** Tailwind text color class for a given win-rate value. */
function winRateColor(rate: number | null): string {
  if (rate == null) return "text-slate-500";
  if (rate >= 70) return "text-emerald-400";
  if (rate >= 40) return "text-amber-400";
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
  const { data: prices = {}, isLoading: pricesLoading } = useQuery({
    queryKey: ["prices"],
    queryFn: fetchPrices,
  });
  const eventBuffer = useUi((s) => s.eventBuffer);
  const lastRunIdByTicker = useUi((s) => s.lastRunIdByTicker);

  const rows = useMemo(() => {
    const pxMap = prices as Record<string, PriceData>;

    // -- Per-ticker accuracy computation --
    const accuracies: TickerAccuracy[] = watchlist
      .map((row) => {
        const runId = lastRunIdByTicker[row.ticker] ?? null;
        const px = pxMap[row.ticker];

        // All decision events for this ticker's last run
        const decisions = eventBuffer.filter(
          (e: WsEvent) => e.type === "decision" && e.run_id === runId,
        );

        const totalDecisions = decisions.length;
        if (totalDecisions === 0) return null;

        let wins = 0;
        let losses = 0;
        let totalConfidence = 0;
        let confidenceCount = 0;

        for (const dec of decisions) {
          const d = dec.data as DecisionData;

          if (typeof d.confidence === "number") {
            totalConfidence += d.confidence;
            confidenceCount++;
          }

          if (px && typeof px.change_pct === "number") {
            const outcome = classifyOutcome(d.action, px.change_pct);
            if (outcome === "win") wins++;
            else if (outcome === "loss") losses++;
          }
        }

        const winRate =
          wins + losses > 0 ? (wins / (wins + losses)) * 100 : null;
        const avgConfidence =
          confidenceCount > 0 ? totalConfidence / confidenceCount : null;

        return {
          rank: 0,
          ticker: row.ticker,
          companyName: row.company_name,
          totalDecisions,
          wins,
          losses,
          winRate,
          avgConfidence,
        };
      })
      .filter((t): t is TickerAccuracy => t !== null);

    // Sort by win rate descending (null rates sink to the bottom)
    accuracies.sort((a, b) => {
      const aRate = a.winRate ?? -1;
      const bRate = b.winRate ?? -1;
      if (bRate !== aRate) return bRate - aRate;
      // Tiebreaker: total decisions descending
      return b.totalDecisions - a.totalDecisions;
    });

    // Assign ordinal ranks
    return accuracies.map((t, i) => ({ ...t, rank: i + 1 }));
  }, [watchlist, prices, eventBuffer, lastRunIdByTicker]);

  const isLoading = watchlistLoading || pricesLoading;

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
      ) : rows.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-sm text-slate-500">No decision data yet.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-800/60 text-slate-500 font-medium uppercase tracking-wider">
                <th className="px-4 py-2.5 text-left w-10">#</th>
                <th className="px-4 py-2.5 text-left">Ticker</th>
                <th className="px-4 py-2.5 text-left">Company Name</th>
                <th className="px-4 py-2.5 text-right">Decisions</th>
                <th className="px-4 py-2.5 text-right">Wins</th>
                <th className="px-4 py-2.5 text-right">Losses</th>
                <th className="px-4 py-2.5 text-right">Win Rate</th>
                <th className="px-4 py-2.5 text-right">Avg Confidence</th>
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
                  <td className="px-4 py-2.5 text-slate-400 truncate max-w-[200px]">
                    {row.companyName}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <span className="data-text text-slate-300">
                      {row.totalDecisions}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <span className="data-text text-emerald-400">
                      {row.wins}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <span className="data-text text-red-400">
                      {row.losses}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <span className={`data-text ${winRateColor(row.winRate)}`}>
                      {row.winRate != null ? `${row.winRate.toFixed(0)}%` : "—"}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <span className="data-text text-sky-400">
                      {row.avgConfidence != null
                        ? `${(row.avgConfidence * 100).toFixed(0)}%`
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
