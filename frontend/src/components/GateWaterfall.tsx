/** The pipeline's gauntlet, rendered faithfully from node_sequence +
 * rejection: every stage a decision passed, and exactly where it died.
 * This is the "how risky is it" answer in one strip. */
import { Check, X } from "lucide-react";

import { cn } from "@/lib/utils";

const STAGE_LABELS: Record<string, string> = {
  prepare: "Prepare",
  technical: "Technical",
  macro: "Macro",
  sentiment: "Sentiment",
  onchain: "On-chain",
  risk_team: "Risk team",
  debate: "Debate",
  risk_gate: "Risk gate",
  critic: "Critic",
  reflection: "Reflection",
  judge: "Judge",
  portfolio_manager: "PM gate",
  execution: "Execution",
  rejected: "Rejected",
};

export function GateWaterfall({
  nodeSequence,
  rejection,
}: {
  nodeSequence: string[];
  rejection: { stage?: string | null; [k: string]: unknown } | null;
}) {
  // preserve pipeline order, drop fan-out duplicates
  const stages = [...new Set(nodeSequence)].filter((s) => s !== "rejected");
  const failedAt = rejection?.stage ?? null;
  const reasons = (rejection?.reasons as string[] | undefined) ?? [];

  return (
    <div data-testid="gate-waterfall">
      <ol className="flex flex-wrap items-center gap-1 text-xs">
        {stages.map((stage, i) => {
          const failed = stage === failedAt;
          const reached =
            failedAt == null || stages.indexOf(String(failedAt)) >= i;
          return (
            <li key={stage} className="flex items-center gap-1">
              {i > 0 && <span className="text-fg-subtle">→</span>}
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5",
                  failed
                    ? "border-bear/50 bg-bear-muted text-bear"
                    : reached
                      ? "border-bull/40 bg-bull-muted text-bull"
                      : "border-border text-fg-subtle",
                )}
              >
                {failed ? (
                  <X size={11} aria-label="failed" />
                ) : reached ? (
                  <Check size={11} aria-label="passed" />
                ) : null}
                {STAGE_LABELS[stage] ?? stage}
              </span>
            </li>
          );
        })}
      </ol>
      {failedAt && reasons.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-xs text-bear">
          {reasons.map((reason, i) => (
            <li key={i}>{String(reason)}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
