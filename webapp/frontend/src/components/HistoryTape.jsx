import { useCallback, useEffect, useImperativeHandle } from "react";
import { useState } from "react";
import { decisionKind } from "../utils/decision";

/**
 * `refreshRef` lets a parent (App) trigger a reload after a new print
 * resolves, without HistoryTape polling on its own timer — the tape only
 * needs to move when something actually happened.
 */
export function HistoryTape({ api, refreshRef }) {
  const [jobs, setJobs] = useState([]);
  const [status, setStatus] = useState("idle"); // idle | loading | error
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    if (!api.apiKey) return;
    setStatus("loading");
    try {
      const data = await api.fetchJobs();
      setJobs(data);
      setStatus("idle");
      setMessage("");
    } catch (err) {
      setStatus("error");
      setMessage(err.message);
    }
  }, [api]);

  useImperativeHandle(refreshRef, () => ({ reload: load }), [load]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section aria-labelledby="tape-heading">
      <div className="tape-heading">
        <h2 id="tape-heading">recent prints</h2>
        <button type="button" className="btn btn--ghost" onClick={load} disabled={status === "loading"}>
          Refresh
        </button>
      </div>
      {status === "error" && (
        <p className="status-line" data-tone="error" role="alert">
          {message}
        </p>
      )}
      {status !== "error" && jobs.length === 0 && (
        <p className="tape-empty">No runs yet — analyze a ticker to start your tape.</p>
      )}
      {jobs.length > 0 && (
        <ul className="tape-list">
          {jobs.map((job) => (
            <li key={job.id}>
              <span className="ticker">{job.ticker}</span>
              <span>{job.trade_date}</span>
              <span>
                {job.status === "done" ? (
                  <>
                    <span className="decision" data-decision={decisionKind(job.decision)}>
                      {job.decision}
                    </span>{" "}
                    · {job.cached ? "cached" : "live"}
                  </>
                ) : (
                  job.status
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
