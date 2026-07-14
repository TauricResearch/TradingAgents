/** The pipeline's gauntlet, rendered faithfully from node_sequence +
 * rejection: every stage a decision passed, and exactly where it died.
 * This is the "how risky is it" answer in one strip. */
import { Check, X } from "lucide-react";

import { cn } from "@/lib/utils";

const STAGE_LABELS: Record<string, string> = {
  prepare: "Prepare",
  team_technical: "Technical",
  team_macro: "Macro",
  team_news_sentiment: "Sentiment",
  team_quant: "Quant",
  team_risk: "Risk team",
  onchain: "On-chain",
  join: "Join",
  technical_bull: "Tech bull",
  technical_bear: "Tech bear",
  macro_bull: "Macro bull",
  macro_bear: "Macro bear",
  risk_gate: "Risk gate",
  critic: "Critic",
  reflection: "Reflection",
  judge: "Judge",
  portfolio_manager: "PM gate",
  pm_gate: "PM gate",
  human_approval: "Approval",
  execution: "Execution",
  rejected: "Rejected",
};

/** every real node stays visible (honesty); unknown ids just lose the
 * underscores instead of leaking raw enum names */
function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage.replaceAll("_", " ");
}

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
                {stageLabel(stage)}
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
