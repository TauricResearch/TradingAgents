/** The pipeline's gauntlet, rendered faithfully from node_sequence +
 * rejection: every stage a decision passed, and exactly where it died.
 * This is the "how risky is it" answer in one strip. */
import { Check, X } from "lucide-react";

import { cn } from "@/lib/utils";

// Mockup buckets: every real node maps into a display group; the exact
// failing node is still named in the rejection detail line below the strip
// (display grouping, not information hiding).
const STAGE_GROUPS: [group: string, nodes: string[]][] = [
  ["Prepare", ["prepare"]],
  ["Technical", ["team_technical", "technical"]],
  ["Macro", ["team_macro", "macro"]],
  ["Sentiment", ["team_news_sentiment", "sentiment"]],
  ["Quant", ["team_quant"]],
  ["On-chain", ["onchain"]],
  ["Risk team", ["team_risk", "risk_team"]],
  ["Debate", ["join", "technical_bull", "technical_bear", "macro_bull",
              "macro_bear", "debate", "critic", "reflection"]],
  ["Judge", ["judge"]],
  ["Risk gate", ["risk_gate"]],
  ["PM gate", ["pm_gate", "portfolio_manager"]],
  ["Approval", ["human_approval"]],
  ["Execution", ["execution"]],
];

function groupOf(stage: string): string {
  for (const [group, nodes] of STAGE_GROUPS) {
    if (nodes.includes(stage)) return group;
  }
  return stage.replaceAll("_", " ");
}

export function GateWaterfall({
  nodeSequence,
  rejection,
}: {
  nodeSequence: string[];
  rejection: { stage?: string | null; [k: string]: unknown } | null;
}) {
  // group real nodes into the display buckets, preserving pipeline order
  const stages = [...new Set(
    nodeSequence.filter((s) => s !== "rejected").map(groupOf),
  )];
  const failedAt = rejection?.stage ? groupOf(String(rejection.stage)) : null;
  const failedNode = rejection?.stage ?? null;
  const reasons = (rejection?.reasons as string[] | undefined) ?? [];

  return (
    <div data-testid="gate-waterfall">
      <ol className="flex flex-wrap items-center gap-1.5 text-[11.5px]">
        {stages.map((stage, i) => {
          const failed = stage === failedAt;
          const reached =
            failedAt == null || stages.indexOf(String(failedAt)) >= i;
          return (
            <li key={stage} className="flex items-center gap-1.5">
              {i > 0 && <span className="text-border-strong">→</span>}
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-full px-2.5 py-[3px] font-bold",
                  failed
                    ? "bg-bear-muted text-bear"
                    : reached
                      ? "bg-bull-muted text-bull"
                      : "text-fg-subtle",
                )}
              >
                {failed ? (
                  <X size={10} aria-label="failed" />
                ) : reached ? (
                  <Check size={10} aria-label="passed" />
                ) : null}
                {stage}
              </span>
            </li>
          );
        })}
      </ol>
      {failedNode != null && (
        <p className="mt-2 text-xs text-bear">
          rejected at <span className="font-mono">{String(failedNode)}</span>
        </p>
      )}
      {failedAt && reasons.length > 0 && (
        <ul className="mt-1 list-disc pl-5 text-xs text-bear">
          {reasons.map((reason, i) => (
            <li key={i}>{String(reason)}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
