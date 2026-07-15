/** Diverging consensus bar: bear left, bull right, neutral notch —
 * confidence-weighted vote share with exact counts labeled. A sankey
 * was rejected: votes are a tally, not a flow. */
import { directionOf } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Vote {
  agent_id: string;
  vote: string;
  confidence: number;
}

export function ConsensusBar({
  votes,
  judgeAction,
}: {
  votes: Vote[];
  judgeAction?: string | null;
}) {
  if (votes.length === 0) return null;
  const weights = { bull: 0, bear: 0, neutral: 0 };
  const counts = { bull: 0, bear: 0, neutral: 0 };
  votes.forEach((vote) => {
    const dir = directionOf(vote.vote);
    weights[dir] += Math.max(vote.confidence, 1);
    counts[dir] += 1;
  });
  const total = weights.bull + weights.bear + weights.neutral || 1;
  const pct = {
    bull: (weights.bull / total) * 100,
    bear: (weights.bear / total) * 100,
    neutral: (weights.neutral / total) * 100,
  };
  const judge = judgeAction ? directionOf(judgeAction) : null;

  return (
    <div data-testid="consensus-bar">
      <div
        className="flex h-[22px] w-full overflow-hidden rounded-full shadow-[inset_0_1px_3px_rgba(26,33,48,0.12)]"
        role="img"
        aria-label={`consensus: ${counts.bear} bearish, ${counts.neutral} neutral, ${counts.bull} bullish votes, confidence weighted`}
      >
        <div className="bg-bear/75" style={{ width: `${pct.bear}%` }} />
        <div className="bg-neutral/55" style={{ width: `${pct.neutral}%` }} />
        <div className="bg-bull/80" style={{ width: `${pct.bull}%` }} />
      </div>
      <div className="mt-1.5 flex justify-between text-xs font-semibold tabular">
        <span className="text-bear">▼ {counts.bear} bearish</span>
        <span className="text-neutral">– {counts.neutral} neutral</span>
        <span className="text-bull">▲ {counts.bull} bullish</span>
      </div>
      {judge && (
        <div className="mt-1.5 text-xs text-fg-muted">
          judge ruled{" "}
          <span
            className={cn(
              "font-bold",
              judge === "bull"
                ? "text-bull"
                : judge === "bear"
                  ? "text-bear"
                  : "text-neutral",
            )}
          >
            {judgeAction}
          </span>
          {((judge === "bull" && pct.bear > pct.bull) ||
            (judge === "bear" && pct.bull > pct.bear)) && (
            <span className="text-neutral"> — against the weighted consensus</span>
          )}
        </div>
      )}
    </div>
  );
}
