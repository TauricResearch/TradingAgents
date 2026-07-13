/** Segmented control (reskin): a --surface-2 track whose active segment
 * pops as a solid white chip with brand text. Pure presentation — callers
 * own the state; each segment is a plain button with aria-pressed. */
import * as React from "react";

import { cn } from "@/lib/utils";

export function Segmented({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      role="group"
      className={cn(
        "inline-flex items-center gap-0.5 rounded-xl bg-surface-2 p-0.5",
        className,
      )}
      {...props}
    />
  );
}

export function Segment({
  active,
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      className={cn(
        "cursor-pointer rounded-[10px] px-2.5 py-1 text-xs font-semibold transition-colors",
        active
          ? "bg-surface-solid text-accent shadow-sm"
          : "text-fg-muted hover:text-fg",
        className,
      )}
      {...props}
    />
  );
}
