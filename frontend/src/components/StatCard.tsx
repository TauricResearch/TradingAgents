import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** Small-n honesty: stats always show their sample size when given. */
export function StatCard({
  label,
  value,
  sub,
  n,
  tone,
  className,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  n?: number;
  tone?: "bull" | "bear" | "neutral";
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-md border border-border bg-surface-2/50 px-3 py-2",
        className,
      )}
    >
      <div className="text-[11px] uppercase tracking-wide text-fg-subtle">
        {label}
        {n != null && <span className="ml-1 normal-case">(n={n})</span>}
      </div>
      <div
        className={cn(
          "font-mono text-lg tabular",
          tone === "bull" && "text-bull",
          tone === "bear" && "text-bear",
          tone === "neutral" && "text-neutral",
        )}
      >
        {value}
      </div>
      {sub && <div className="text-xs text-fg-muted">{sub}</div>}
    </div>
  );
}
