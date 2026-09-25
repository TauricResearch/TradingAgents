import { decisionKind } from "../utils/decision";
import { formatPrintTime, shortTicketId } from "../utils/format";

/**
 * The one hero moment on the page: a resolved decision reads as an actual
 * market print (ticket id + UTC timestamp), not a generic result card.
 * Everything else on the page is styled to recede so this holds attention.
 */
export function DecisionStamp({ job, pollError }) {
  if (pollError) {
    return (
      <div className="print-stage">
        <p className="status-line" data-tone="error" role="alert">
          {pollError}
        </p>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="print-stage">
        <p className="print-stage__idle">Run an analysis to print a call.</p>
      </div>
    );
  }

  if (job.status === "queued" || job.status === "running") {
    return (
      <div className="print-stage" role="status" aria-live="polite">
        <p className="print-stage__idle">
          {job.status === "queued" ? "Queued" : "Agents debating"}{" "}
          <span className="print-pulse" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
        </p>
      </div>
    );
  }

  if (job.status === "failed") {
    return (
      <div className="print-stage">
        <p className="status-line" data-tone="error" role="alert">
          Run failed: {job.error}
        </p>
      </div>
    );
  }

  const kind = decisionKind(job.decision);
  return (
    <div className="print-stage" role="status" aria-live="polite">
      <span className="print-stamp" data-decision={kind}>
        {job.decision}
      </span>
      <p className="print-meta">
        PRINT #{shortTicketId(job.id)} · {formatPrintTime(job.finished_at)}
        {job.cached ? " · from the tape" : ""}
      </p>
    </div>
  );
}
