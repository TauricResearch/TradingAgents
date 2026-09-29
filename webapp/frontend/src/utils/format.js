export function formatPrintTime(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString);
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString().slice(11, 19) + " UTC";
}

export function shortTicketId(jobId) {
  if (!jobId) return "";
  return jobId.slice(0, 8);
}
