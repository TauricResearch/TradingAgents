/** The four honest states every widget must express. Copy is declarative,
 * timestamped, and never fakes liveness — no placeholder numbers, no
 * "Oops!". Locked = paid feed not purchased (a trust signal, not a bug). */
import { AlertTriangle, Clock, Inbox, Lock } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

const ICONS = {
  empty: Inbox,
  waiting: Clock,
  error: AlertTriangle,
  locked: Lock,
} as const;

export function EmptyState({
  kind = "empty",
  title,
  detail,
  action,
  className,
}: {
  kind?: keyof typeof ICONS;
  title: string;
  detail?: string;
  action?: ReactNode;
  className?: string;
}) {
  const Icon = ICONS[kind];
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 py-8 text-center",
        kind === "locked" && "opacity-70",
        className,
      )}
    >
      <Icon
        size={20}
        className={kind === "error" ? "text-bear" : "text-fg-subtle"}
        aria-hidden="true"
      />
      <div className="text-sm text-fg-muted">{title}</div>
      {detail && <div className="max-w-sm text-xs text-fg-subtle">{detail}</div>}
      {action}
    </div>
  );
}
