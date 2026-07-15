import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** Small-n honesty: stats always show their sample size when given. */
export function StatCard({
  label,
  value,
  sub,
  n,
  tone,
  elevated = false,
  className,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  n?: number;
  tone?: "bull" | "bear" | "neutral";
  /** mockup KPI tiles are elevated (bordered + shadow on `surface`);
   * grouped tiles (Intel) stay flat on `surface-2` */
  elevated?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        // mockup: elevated KPI tiles are 16px radius / 12px vertical pad;
        // flat grouped tiles (Intel) are 14px radius / 10px pad
        "px-3.5",
        elevated
          ? "rounded-[16px] border border-border bg-surface py-3 shadow-(--shadow-1)"
          : "rounded-[14px] bg-surface-2 py-2.5",
        className,
      )}
    >
      <div className="truncate text-[9.5px] font-bold uppercase tracking-[0.09em] text-fg-subtle">
        {label}
        {n != null && <span className="ml-1 normal-case">(n={n})</span>}
      </div>
      <div
        className={cn(
          "font-mono text-[16.5px] font-bold tabular tracking-[-0.01em]",
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
