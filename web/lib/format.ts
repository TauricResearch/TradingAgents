// Tiny shared formatters.

export function fmtTokens(n: number | null | undefined): string {
  return (n ?? 0).toLocaleString();
}

export function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  // Display only the date+minute, drop seconds/ms.
  return iso.replace("T", " ").replace("Z", "").slice(0, 16);
}

export function statusColor(status: string): string {
  switch (status) {
    case "done":
      return "bg-success/15 text-success";
    case "running":
      return "bg-accent/15 text-accent";
    case "error":
      return "bg-danger/15 text-danger";
    default:
      return "bg-muted/15 text-muted";
  }
}

export function decisionColor(decision?: string | null): string {
  if (!decision) return "text-muted";
  const d = decision.toUpperCase();
  if (d.includes("BUY") || d.includes("OVERWEIGHT")) return "text-success";
  if (d.includes("SELL") || d.includes("REDUCE") || d.includes("AVOID")) return "text-danger";
  return "text-warning";
}
