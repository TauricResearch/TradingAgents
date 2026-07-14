import { ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";

import { EmptyState } from "./EmptyState";
import type { Alert } from "@/lib/api/types";
import { fmtDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const CHIP = {
  critical: "bg-bear-muted text-bear",
  warning: "bg-neutral-muted text-neutral",
  info: "bg-accent-muted text-accent",
} as const;

export function AlertFeedList({
  alerts,
  limit,
  emptySince,
}: {
  alerts: Alert[];
  limit?: number;
  emptySince?: string;
}) {
  const shown = limit ? alerts.slice(0, limit) : alerts;
  if (shown.length === 0) {
    return (
      <EmptyState
        kind="empty"
        title="All clear"
        detail={emptySince ? `No alerts since ${fmtDateTime(emptySince)}.` : "No alerts."}
      />
    );
  }
  return (
    <ul className="divide-y divide-border/60" data-testid="alert-feed">
      {shown.map((alert, i) => (
        <li key={`${alert.run_id}-${i}`} className="flex gap-2.5 py-2 text-sm">
          <span
            className={cn(
              "mt-0.5 inline-flex h-fit shrink-0 items-center gap-1 rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide",
              CHIP[alert.severity],
            )}
          >
            {alert.text.includes("injection") && (
              <ShieldAlert size={11} aria-hidden="true" />
            )}
            {alert.severity}
          </span>
          <div className="min-w-0">
            <span className="text-fg-muted">{alert.text}</span>
            <div className="text-xs text-fg-subtle">
              {fmtDateTime(alert.time)} ·{" "}
              <Link to={`/decisions/${alert.run_id}`} className="text-accent underline underline-offset-2">
                view run
              </Link>
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}
