"use client";

import { decisionClass } from "@/lib/format";

export function DecisionBadge({ action, size = "md" }: { action?: string | null; size?: "sm" | "md" | "lg" }) {
  const label = (action || "—").toUpperCase();
  const pad = size === "lg" ? "px-5 py-3 text-3xl" : size === "sm" ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-sm";
  return (
    <span className={`inline-flex items-center rounded-md border font-semibold tracking-wide ${pad} ${decisionClass(action)}`}>
      {label}
    </span>
  );
}
