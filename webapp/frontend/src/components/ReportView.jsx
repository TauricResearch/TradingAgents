export function ReportView({ job }) {
  if (!job || job.status !== "done" || !job.report) return null;
  return <div className="report-view">{job.report}</div>;
}
