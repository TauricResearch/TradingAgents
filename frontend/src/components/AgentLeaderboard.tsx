/** Agent leaderboard with the honesty column: calibration gap =
 * avg confidence − realized hit rate. Sorted by hit rate, unscored
 * agents grayed at the bottom, never hidden. */
import type { AgentPerf } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export function AgentLeaderboard({ perf }: { perf: AgentPerf }) {
  const rows = Object.entries(perf).sort((a, b) => {
    const ha = a[1].hit_rate ?? -1;
    const hb = b[1].hit_rate ?? -1;
    return hb - ha || b[1].votes - a[1].votes;
  });

  return (
    <div className="max-h-96 overflow-y-auto">
      <table className="w-full text-xs" data-testid="agent-leaderboard">
        <thead className="sticky top-0 bg-surface">
          <tr className="border-b border-border text-left text-fg-subtle">
            <th className="py-1 pr-2 font-medium">agent</th>
            <th className="py-1 pr-2 text-right font-medium">votes</th>
            <th className="whitespace-nowrap py-1 pr-2 text-right font-medium">conf</th>
            <th className="whitespace-nowrap py-1 pr-2 text-right font-medium">hit</th>
            <th className="py-1 text-right font-medium">calib gap</th>
          </tr>
        </thead>
        <tbody className="tabular">
          {rows.map(([agentId, row]) => {
            const unscored = row.hit_rate == null;
            const gap =
              row.hit_rate != null
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
                <td className="py-1 pr-2 font-mono">{agentId}</td>
                <td className="py-1 pr-2 text-right">{row.votes}</td>
                <td className="py-1 pr-2 text-right">
                  {row.avg_confidence.toFixed(0)}
                </td>
                <td className="py-1 pr-2 text-right">
                  {row.hit_rate == null
                    ? `— (n=${row.scored})`
                    : `${Math.round(row.hit_rate * 100)}% (n=${row.scored})`}
                </td>
                <td
                  className={cn(
                    "py-1 text-right",
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
