import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { AnalyzeForm } from "../components/AnalyzeForm";
import { DecisionStamp } from "../components/DecisionStamp";
import { ReportView } from "../components/ReportView";
import { HistoryTape } from "../components/HistoryTape";
import { useJobPolling } from "../hooks/useJobPolling";
import { useApp } from "../context/AppContext";

export function DashboardPage() {
  const { api, loadAccount } = useApp();
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

  return (
    <main className="app-main">
      <div aria-label="Desk">
        <AnalyzeForm onSubmitted={setCurrentJobId} initialTicker={prefillTicker} />
      </div>
      <div aria-label="Print">
        <DecisionStamp job={job} pollError={pollError} />
        <ReportView job={job} />
        <HistoryTape refreshRef={tapeRef} limit={8} />
      </div>
    </main>
  );
}
