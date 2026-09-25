import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { AnalyzeForm } from "../components/AnalyzeForm";
import { DecisionStamp } from "../components/DecisionStamp";
import { ReportView } from "../components/ReportView";
import { HistoryTape } from "../components/HistoryTape";
import { MarketGlance } from "../components/MarketGlance";
import { StatCard } from "../components/StatCard";
import { useJobPolling } from "../hooks/useJobPolling";
import { useApp } from "../context/AppContext";

export function DashboardPage() {
  const { api, account, loadAccount } = useApp();
  const location = useLocation();
  const [currentJobId, setCurrentJobId] = useState(null);
  const tapeRef = useRef(null);

  const { job, error: pollError } = useJobPolling(currentJobId, api.fetchJob);

  const settled = job && (job.status === "done" || job.status === "failed");
  useEffect(() => {
    if (!settled) return;
    loadAccount();
    tapeRef.current?.reload();
    // Only re-run when the settled job itself changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.id, job?.status]);

  // A Watchlist row's "Analyze" action navigates here with state: { ticker }.
  const prefillTicker = location.state?.ticker || "";

  const cacheRate =
    account && account.total_jobs > 0 ? Math.round((account.cached_jobs / account.total_jobs) * 100) : null;

  return (
    <main className="app-main">
      {account && (
        <div className="dashboard-span stats-row">
          <StatCard label="runs this month" value={`${account.jobs_this_month}/${account.free_tier_limit}`} hint={account.plan === "pro" ? "unlimited on Pro" : "resets monthly"} />
          <StatCard label="total prints" value={account.total_jobs} hint={`${account.distinct_tickers} ticker${account.distinct_tickers === 1 ? "" : "s"} covered`} />
          <StatCard
            label="served from cache"
            value={cacheRate === null ? "—" : `${cacheRate}%`}
            hint={cacheRate === null ? "run your first analysis" : "instant, no quota used"}
            tone="buy"
          />
          <StatCard label="watchlist" value={account.watchlist_count} hint="tracked tickers" />
        </div>
      )}

      <div aria-label="Desk">
        <AnalyzeForm onSubmitted={setCurrentJobId} initialTicker={prefillTicker} />
      </div>
      <div aria-label="Print">
        <DecisionStamp job={job} pollError={pollError} />
        <ReportView job={job} />
        <HistoryTape refreshRef={tapeRef} limit={8} />
      </div>

      <div className="dashboard-span">
        <MarketGlance />
      </div>
    </main>
  );
}
