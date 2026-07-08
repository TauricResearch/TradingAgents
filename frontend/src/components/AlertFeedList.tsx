import { ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";

import { EmptyState } from "./EmptyState";
import type { Alert } from "@/lib/api/types";
import { fmtDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const GLYPH = { critical: "⛔", warning: "⚠", info: "ℹ" } as const;
const TONE = {
  critical: "text-bear",
  warning: "text-neutral",
  info: "text-fg-muted",
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
        <li key={`${alert.run_id}-${i}`} className="flex gap-2 py-1.5 text-sm">
          <span className={cn("shrink-0", TONE[alert.severity])} aria-hidden="true">
            {alert.text.includes("injection") ? (
              <ShieldAlert size={14} className="mt-0.5" />
            ) : (
              GLYPH[alert.severity]
            )}
          </span>
          <div className="min-w-0">
            <span className={cn("mr-2 text-xs uppercase", TONE[alert.severity])}>
              {alert.severity}
            </span>
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
