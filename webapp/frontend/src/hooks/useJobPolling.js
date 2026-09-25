import { useEffect, useRef, useState } from "react";

const POLL_INTERVAL_MS = 4000;
const ACTIVE_STATUSES = new Set(["queued", "running"]);

/**
 * Polls GET /api/jobs/{jobId} on an interval until the job leaves
 * queued/running. Cancels cleanly on unmount or when jobId changes, so a
 * stale timer from a previous job can never call setState after this
 * component (or a re-run) has moved on.
 */
export function useJobPolling(jobId, fetchJob) {
  const [job, setJob] = useState(null);
  const [error, setError] = useState("");
  const fetchJobRef = useRef(fetchJob);
  fetchJobRef.current = fetchJob;

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      setError("");
      return undefined;
    }

    let cancelled = false;
    let timeoutId;

    async function poll() {
      try {
        const result = await fetchJobRef.current(jobId);
        if (cancelled) return;
        setJob(result);
        setError("");
        if (ACTIVE_STATUSES.has(result.status)) {
          timeoutId = setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    }

    setJob(null);
    setError("");
    poll();

    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, [jobId]);

  return { job, error };
}
