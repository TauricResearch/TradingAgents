import { useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { decisionKind } from "../utils/decision";
import { useApp } from "../context/AppContext";

const AUTO_REFRESH_MS = 12000;

/**
 * `refreshRef` lets a parent force an immediate reload (e.g. right after a
 * new print resolves) on top of the tape's own live polling below.
 *
 * `showFilters` turns on the ticker/status filter row (the full History
 * page); the compact "recent prints" list on the Dashboard omits it.
 */
export function HistoryTape({ refreshRef, limit = 20, showFilters = false, title = "recent prints" }) {
  const { api } = useApp();
  const [jobs, setJobs] = useState([]);
  const [status, setStatus] = useState("idle"); // idle | loading | error
  const [message, setMessage] = useState("");
  const [tickerFilter, setTickerFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const loadedOnce = useRef(false);

  const load = useCallback(async () => {
    if (!api.apiKey) return;
    // Only show a "loading" state for the first fetch — background polls
    // refresh the list silently so it reads as live, not as flickering.
    if (!loadedOnce.current) setStatus("loading");
    try {
      const data = await api.fetchJobs({
        limit,
        ticker: tickerFilter.trim() || undefined,
        status: statusFilter || undefined,
      });
      setJobs(data);
      setStatus("idle");
      setMessage("");
      loadedOnce.current = true;
    } catch (err) {
      setStatus("error");
      setMessage(err.message);
    }
  }, [api, limit, tickerFilter, statusFilter]);

  useImperativeHandle(refreshRef, () => ({ reload: load }), [load]);

  useEffect(() => {
    loadedOnce.current = false;
    load();
    const interval = setInterval(load, AUTO_REFRESH_MS);
    return () => clearInterval(interval);
  }, [load]);

  return (
    <section aria-labelledby="tape-heading">
      <div className="tape-heading">
        <h2 id="tape-heading">
          {title}
          <span className="live-dot" aria-hidden="true" />
          <span className="visually-hidden">Live, updates automatically</span>
        </h2>
      </div>

      {showFilters && (
        <div className="field-row tape-filters">
          <div className="field">
            <label htmlFor="filter-ticker">ticker</label>
            <input
              id="filter-ticker"
              type="text"
              placeholder="all"
              value={tickerFilter}
              onChange={(e) => setTickerFilter(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="filter-status">status</label>
            <select
              id="filter-status"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">all</option>
              <option value="done">done</option>
              <option value="failed">failed</option>
              <option value="running">running</option>
              <option value="queued">queued</option>
            </select>
          </div>
        </div>
      )}

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
