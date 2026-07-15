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
        <li key={`${alert.run_id}-${i}`} className="flex gap-3 py-[9px] text-[13px]">
          <span
            className={cn(
              "mt-0.5 inline-flex h-fit shrink-0 items-center gap-1 rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-[0.05em]",
              CHIP[alert.severity],
            )}
          >
            {alert.text.includes("injection") && (
              <ShieldAlert size={11} aria-hidden="true" />
            )}
            {alert.severity}
          </span>
          <div className="min-w-0">
            {/* mockup alerts are one-liners; long texts (a critic's full
                rejection) clamp here — the run page has the whole record */}
            <p className="line-clamp-2 text-fg" title={alert.text}>
              {alert.text}
            </p>
            <div className="text-[11px] text-fg-subtle">
              {fmtDateTime(alert.time)} ·{" "}
              <Link to={`/decisions/${alert.run_id}`} className="text-accent">
                view run
              </Link>
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}
