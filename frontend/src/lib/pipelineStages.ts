/** THE single progress vocabulary for an in-flight pipeline run.
 *
 * The 3D board and the header progress chip previously counted on two
 * different scales ("stage 2/10" vs "team_macro (5/18)") — the trader
 * review flagged the disagreement. Every surface now derives its counter
 * from these buckets; raw LangGraph node names remain display detail. */

export const PIPELINE_BUCKETS = [
  "prepare", "teams", "join", "debate", "risk_gate",
  "review", "judge", "sizing", "approval", "execution",
] as const;

export type PipelineBucket = (typeof PIPELINE_BUCKETS)[number];

/** LangGraph node name → progress bucket. */
export function bucketOf(node: string): string {
  if (node.startsWith("team_")) return "teams";
  if (/^(technical|macro)_(bull|bear)$/.test(node) || node === "sentiment")
    return "debate";
  if (node === "critic" || node === "reflection") return "review";
  if (node === "portfolio_manager") return "sizing";
  if (node === "human_approval") return "approval";
  return node; // prepare, join, risk_gate, judge, execution, rejected
}

/** 1-based bucket position for "stage k/N" counters; 1 when unknown. */
export function stageProgress(node: string | null | undefined): {
  index: number;
  total: number;
} {
  const idx = node
    ? PIPELINE_BUCKETS.indexOf(bucketOf(node) as PipelineBucket)
    : -1;
  return { index: Math.max(idx + 1, 1), total: PIPELINE_BUCKETS.length };
}
