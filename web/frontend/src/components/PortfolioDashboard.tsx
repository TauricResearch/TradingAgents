import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchWatchlist, fetchPrices } from "../lib/api";
import { useUi } from "../store/ui";
import { fmtPct, fmtPrice } from "../lib/format";
import type { WsEvent } from "../lib/events";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

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

interface TickerSummary {
  ticker: string;
  companyName: string;
  lastDecision: string | null;
  changePct: number | null;
  price: number | null;
  stale: boolean;
  confidence: number | null;
  runId: string | null;
  outcome: "win" | "loss" | "neutral" | null;
}

interface RecentDecision {
  ticker: string;
  action: string;
  confidence: number;
  ts: string;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

/** Reverse-lookup: find the ticker that owns a given run_id. */
function tickerForRunId(
  map: Record<string, string | null>,
  runId: string,
): string | null {
  for (const [ticker, rid] of Object.entries(map)) {
    if (rid === runId) return ticker;
  }
  return null;
}

/** Determine if a decision action was correct given price movement. */
function classifyOutcome(
  action: string,
  changePct: number,
): "win" | "loss" | "neutral" {
  if (action === "BUY") return changePct > 0 ? "win" : "loss";
  if (action === "SELL") return changePct < 0 ? "win" : "loss";
  // HOLD — neutral by default
  return "neutral";
}

/** Action color (tailwind classes) */
function actionColor(action: string): string {
  if (action === "BUY") return "text-emerald-400";
  if (action === "SELL") return "text-red-400";
  return "text-slate-400";
}

function actionBg(action: string): string {
  if (action === "BUY") return "bg-emerald-500/10 border-emerald-500/25";
  if (action === "SELL") return "bg-red-500/10 border-red-500/25";
  return "bg-slate-700/30 border-slate-600/50";
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function PortfolioDashboard() {
  const { data: watchlist = [] } = useQuery({
    queryKey: ["watchlist"],
    queryFn: fetchWatchlist,
  });
  const { data: prices = {} } = useQuery({
    queryKey: ["prices"],
    queryFn: fetchPrices,
  });
  const eventBuffer = useUi((s) => s.eventBuffer);
  const lastRunIdByTicker = useUi((s) => s.lastRunIdByTicker);

  const stats = useMemo(() => {
    const pxMap = prices as Record<string, PriceData>;

    // -- Per-ticker summaries --
    const summaries: TickerSummary[] = watchlist.map((row) => {
      const px = pxMap[row.ticker];
      const runId = lastRunIdByTicker[row.ticker] ?? null;

      // Latest decision event for this ticker's run
      const decisionEvents = eventBuffer.filter(
        (e: WsEvent) => e.type === "decision" && e.run_id === runId,
      );
      const lastDecEvent =
        decisionEvents.length > 0
          ? decisionEvents[decisionEvents.length - 1]
          : null;
      const decisionData = lastDecEvent?.data as DecisionData | undefined;

      let outcome: "win" | "loss" | "neutral" | null = null;
      if (decisionData && px && typeof px.change_pct === "number") {
        outcome = classifyOutcome(decisionData.action, px.change_pct);
      }

      return {
        ticker: row.ticker,
        companyName: row.company_name,
        lastDecision: row.last_decision,
        changePct: px?.change_pct ?? null,
        price: px?.price ?? null,
        stale: px?.stale ?? false,
        confidence: decisionData?.confidence ?? null,
        runId,
        outcome,
      };
    });

    // -- Aggregate stats --
    const priced = summaries.filter(
      (s) => s.changePct != null && !s.stale,
    );
    const totalPnl = priced.reduce((sum, s) => sum + (s.changePct ?? 0), 0);
    const avgPnl = priced.length > 0 ? totalPnl / priced.length : null;

    const wins = summaries.filter((s) => s.outcome === "win").length;
    const losses = summaries.filter((s) => s.outcome === "loss").length;
    const totalOutcomes = wins + losses;
    const winRate =
      totalOutcomes > 0 ? (wins / totalOutcomes) * 100 : null;

    const totalRuns = Object.values(lastRunIdByTicker).filter(Boolean).length;

    const confs = summaries
      .filter((s) => s.confidence != null)
      .map((s) => s.confidence as number);
    const avgConfidence =
      confs.length > 0
        ? confs.reduce((a, b) => a + b, 0) / confs.length
        : null;

    // -- Recent decisions timeline --
    const allDecisions = eventBuffer.filter(
      (e: WsEvent) => e.type === "decision",
    );
    const recentDecisions: RecentDecision[] = allDecisions
      .slice(-10)
      .reverse()
      .map((e: WsEvent) => {
        const d = e.data as DecisionData;
        const tkr = tickerForRunId(lastRunIdByTicker, e.run_id) ?? "";
        return { ticker: tkr, action: d.action, confidence: d.confidence, ts: e.ts };
      })
      .filter((d: RecentDecision) => d.ticker !== "");

    return {
      summaries,
      avgPnl,
      wins,
      losses,
      winRate,
      totalRuns,
      avgConfidence,
      recentDecisions,
    };
  }, [watchlist, prices, eventBuffer, lastRunIdByTicker]);

  const { summaries, avgPnl, wins, losses, winRate, totalRuns, avgConfidence, recentDecisions } = stats;

  if (watchlist.length === 0) return null;

  return (
    <div className="animate-fade-in space-y-5">
      {/* ── Quick Stats Bar ── */}
      <div className="glass-panel px-4 py-3">
        <div className="flex items-center gap-6 text-xs">
          {/* Total P&L */}
          <div className="flex items-center gap-2">
            <span className="text-slate-500 font-medium">Total P&amp;L</span>
            <span
              className={`data-text font-semibold ${
                avgPnl != null
                  ? avgPnl >= 0
                    ? "text-emerald-400"
                    : "text-red-400"
                  : "text-slate-500"
              }`}
            >
              {avgPnl != null ? fmtPct(avgPnl) : "—"}
            </span>
          </div>

          <span className="w-px h-4 bg-slate-700/50" />

          {/* Total Runs */}
          <div className="flex items-center gap-2">
            <span className="text-slate-500 font-medium">Total Runs</span>
            <span className="data-text font-semibold text-slate-200">
              {totalRuns}
            </span>
          </div>

          <span className="w-px h-4 bg-slate-700/50" />

          {/* Win / Loss */}
          <div className="flex items-center gap-2">
            <span className="text-slate-500 font-medium">W/L</span>
            <span className="data-text font-semibold text-emerald-400">
              {wins}
            </span>
            <span className="text-slate-600">/</span>
            <span className="data-text font-semibold text-red-400">
              {losses}
            </span>
          </div>

          <span className="w-px h-4 bg-slate-700/50" />

          {/* Success Rate */}
          <div className="flex items-center gap-2">
            <span className="text-slate-500 font-medium">Success</span>
            <span className="data-text font-semibold text-slate-200">
              {winRate != null ? `${winRate.toFixed(0)}%` : "—"}
            </span>
          </div>

          <span className="w-px h-4 bg-slate-700/50" />

          {/* Avg Confidence */}
          <div className="flex items-center gap-2">
            <span className="text-slate-500 font-medium">Avg Confidence</span>
            <span className="data-text font-semibold text-sky-400">
              {avgConfidence != null
                ? `${(avgConfidence * 100).toFixed(0)}%`
                : "—"}
            </span>
          </div>
        </div>
      </div>

      {/* ── Per-Ticker Summary Cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {summaries.map((s) => {
          const outcomeDot =
            s.outcome === "win"
              ? "bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.4)]"
              : s.outcome === "loss"
                ? "bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.4)]"
                : "bg-slate-600";

          const changeColor =
            s.changePct != null
              ? s.changePct >= 0
                ? "text-emerald-400"
                : "text-red-400"
              : "text-slate-500";

          return (
            <div
              key={s.ticker}
              className="glass-panel px-3 py-2.5 space-y-1.5"
            >
              {/* Ticker + company */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 min-w-0">
                  <span className={`h-2 w-2 rounded-full shrink-0 ${outcomeDot}`} />
                  <span className="text-sm font-semibold text-slate-100">
                    {s.ticker}
                  </span>
                </div>
                {s.stale && (
                  <span className="text-[10px] uppercase tracking-wider font-medium text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded px-1.5 py-0.5">
                    unavailable
                  </span>
                )}
              </div>

              {/* Company name */}
              {s.companyName && (
                <p className="text-[11px] text-slate-600 truncate">
                  {s.companyName}
                </p>
              )}

              {/* Price */}
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500">Price</span>
                <span className="data-text font-medium text-slate-300">
                  {s.price != null ? fmtPrice(s.price) : "—"}
                </span>
              </div>

              {/* P&L */}
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500">P&amp;L</span>
                <span
                  className={`data-text font-semibold ${changeColor}`}
                >
                  {s.changePct != null ? fmtPct(s.changePct) : "—"}
                </span>
              </div>

              {/* Last Decision + confidence */}
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500">Decision</span>
                <span className="flex items-center gap-1.5">
                  {s.lastDecision && (
                    <span
                      className={`tag text-[10px] font-semibold ${actionBg(s.lastDecision)} ${actionColor(s.lastDecision)}`}
                    >
                      {s.lastDecision}
                    </span>
                  )}
                  {s.confidence != null && (
                    <span className="font-mono text-slate-400">
                      {(s.confidence * 100).toFixed(0)}%
                    </span>
                  )}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Recent Decisions Timeline ── */}
      {recentDecisions.length > 0 && (
        <div className="glass-panel">
          <h3 className="section-header px-4 py-2.5 border-b border-slate-700/50 flex items-center gap-2">
            <span className="w-1 h-1 rounded-full bg-sky-400" />
            Recent Decisions
          </h3>
          <div className="divide-y divide-slate-800/60">
            {recentDecisions.map((d, i) => (
              <div
                key={`${d.ticker}-${d.ts}-${i}`}
                className="flex items-center justify-between px-4 py-2 text-xs"
              >
                <div className="flex items-center gap-3">
                  <span className="font-semibold text-slate-200 w-14">
                    {d.ticker}
                  </span>
                  <span
                    className={`tag text-[10px] font-semibold ${actionBg(d.action)} ${actionColor(d.action)}`}
                  >
                    {d.action}
                  </span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="font-mono text-slate-400">
                    {(d.confidence * 100).toFixed(0)}%
                  </span>
                  <span className="text-slate-600 font-mono">
                    {new Date(d.ts).toLocaleTimeString("en-US", {
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                      hour12: false,
                    })}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
