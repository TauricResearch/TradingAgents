import { useCallback, useEffect, useRef, useState } from "react";
import { useTradingApi } from "./hooks/useTradingApi";
import { useJobPolling } from "./hooks/useJobPolling";
import { SignupPanel } from "./components/SignupPanel";
import { AccountPanel } from "./components/AccountPanel";
import { AnalyzeForm } from "./components/AnalyzeForm";
import { DecisionStamp } from "./components/DecisionStamp";
import { ReportView } from "./components/ReportView";
import { HistoryTape } from "./components/HistoryTape";
import { ThemeToggle } from "./components/ThemeToggle";

export function App() {
  const api = useTradingApi();
  const [account, setAccount] = useState(null);
  const [accountStatus, setAccountStatus] = useState("idle"); // idle | loading | error
  const [accountMessage, setAccountMessage] = useState("");
  const [currentJobId, setCurrentJobId] = useState(null);
  const tapeRef = useRef(null);

  const loadAccount = useCallback(async () => {
    if (!api.apiKey) {
      setAccountStatus("error");
      setAccountMessage("Enter a key first.");
      return;
    }
    setAccountStatus("loading");
    setAccountMessage("Loading…");
    try {
      const data = await api.fetchMe();
      setAccount(data);
      setAccountStatus("idle");
      setAccountMessage("");
    } catch (err) {
      setAccountStatus("error");
      setAccountMessage(err.message);
    }
  }, [api]);

  const { job, error: pollError } = useJobPolling(currentJobId, api.fetchJob);

  const settled = job && (job.status === "done" || job.status === "failed");
  useEffect(() => {
    if (!settled) return;
    loadAccount();
    tapeRef.current?.reload();
    // Only re-run when the settled job itself changes, not on every
    // loadAccount/tapeRef identity change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.id, job?.status]);

  function handleKeyIssued(key) {
    api.setApiKey(key);
  }

  return (
    <>
      <header className="app-rail">
        <div className="app-rail__brand">
          <strong>TradingAgents</strong>
          <span className="app-rail__quota">multi-agent equity research — not financial advice</span>
        </div>
        <div className="app-rail__brand">
          {account && (
            <span className="app-rail__quota">
              {account.plan} · {account.jobs_this_month}/{account.free_tier_limit} this month
            </span>
          )}
          <ThemeToggle />
        </div>
      </header>

      <main className="app-main">
        <div className="desk" aria-label="Desk">
          <SignupPanel api={api} onKeyIssued={handleKeyIssued} />
          <AccountPanel
            api={api}
            account={account}
            accountStatus={accountStatus}
            accountMessage={accountMessage}
            onLoad={loadAccount}
          />
          <AnalyzeForm api={api} onSubmitted={setCurrentJobId} />
        </div>

        <div className="print" aria-label="Print">
          <DecisionStamp job={job} pollError={pollError} />
          <ReportView job={job} />
          <HistoryTape api={api} refreshRef={tapeRef} />
        </div>
      </main>

      <footer className="app-footer">
        Research output only. TradingAgents places no trades and gives no investment advice.
      </footer>
    </>
  );
}
