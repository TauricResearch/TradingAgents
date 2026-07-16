/** Agent leaderboard with the honesty column: calibration gap =
 * avg confidence − realized hit rate. Sorted by hit rate, unscored
 * agents grayed at the bottom, never hidden.
 *
 * Hit/gap render only from n >= MIN_SCORED closed outcomes — a 100%(n=1)
 * next to a 0%(n=1) is statistical noise dressed as insight (trader
 * review P0.6); below the bar the row shows "accruing" instead. */
import type { AgentPerf } from "@/lib/api/types";
import { MIN_SCORED } from "@/lib/thresholds";
import { cn } from "@/lib/utils";

export function AgentLeaderboard({ perf }: { perf: AgentPerf }) {
  const rows = Object.entries(perf).sort((a, b) => {
    const scoredA = a[1].scored >= MIN_SCORED ? (a[1].hit_rate ?? -1) : -1;
    const scoredB = b[1].scored >= MIN_SCORED ? (b[1].hit_rate ?? -1) : -1;
    return scoredB - scoredA || b[1].votes - a[1].votes;
  });

  return (
    <div className="max-h-96 overflow-y-auto overflow-x-auto">
      <table className="w-full text-[11.5px]" data-testid="agent-leaderboard">
        <thead className="sticky top-0 bg-surface-solid">
          <tr className="border-b border-border text-left text-fg-subtle">
            <th className="py-1 pr-1.5 font-semibold">agent</th>
            <th className="py-1 pr-1.5 text-right font-semibold">votes</th>
            <th className="whitespace-nowrap py-1 pr-1.5 text-right font-semibold">conf</th>
            <th className="whitespace-nowrap py-1 pr-1.5 text-right font-semibold">hit</th>
            <th className="py-1 text-right font-semibold">gap</th>
          </tr>
        </thead>
        <tbody className="tabular">
          {rows.map(([agentId, row]) => {
            const accruing = row.hit_rate != null && row.scored < MIN_SCORED;
            const unscored = row.hit_rate == null || accruing;
            const gap =
              row.hit_rate != null && !accruing
                ? row.avg_confidence / 100 - row.hit_rate
                : null;
            return (
              <tr
                key={agentId}
                className={cn(
                  "border-b border-border/50",
                  unscored && "text-fg-subtle",
                )}
              >
                <td className="py-[5px] pr-1.5 font-mono">{agentId}</td>
                <td className="py-[5px] pr-1.5 text-right">{row.votes}</td>
                <td className="py-[5px] pr-1.5 text-right">
                  {row.avg_confidence.toFixed(0)}
                </td>
                <td className="whitespace-nowrap py-[5px] pr-1.5 text-right">
                  {row.hit_rate == null ? (
                    <>
                      — <span className="text-fg-subtle">({row.scored})</span>
                    </>
                  ) : accruing ? (
                    <span
                      className="text-fg-subtle"
                      title={`hit rate hidden until ${MIN_SCORED} scored outcomes — n=${row.scored} is noise, not signal`}
                    >
                      accruing ({row.scored}/{MIN_SCORED})
                    </span>
                  ) : (
                    <>
                      <span className="font-bold">{Math.round(row.hit_rate * 100)}%</span>{" "}
                      <span className="text-fg-subtle">({row.scored})</span>
                    </>
                  )}
                </td>
                <td
                  className={cn(
                    "py-[5px] text-right font-bold",
                    gap != null && gap > 0.15 && "text-neutral",
                    gap != null && gap <= 0 && "text-bull",
                  )}
                >
                  {gap == null ? "—" : `${gap > 0 ? "+" : ""}${Math.round(gap * 100)}`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
