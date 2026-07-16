/** Debate as a timeline, not a 59-node graph: team-colored lanes, stance
 * glyphs, citation chips. Reads like a transcript because it is one. */
import { DirectionBadge } from "./DirectionBadge";
import { Emphasis } from "./Emphasis";
import type { Timeline } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const SPEAKER_TEAM: [RegExp, string][] = [
  [/technical/i, "border-l-accent"],
  [/macro/i, "border-l-bull"],
  [/sentiment|rapporteur/i, "border-l-neutral"],
  [/onchain|on-chain/i, "border-l-fg-subtle"],
  [/risk/i, "border-l-bear"],
  [/critic|judge|reflection|portfolio/i, "border-l-border-strong"],
];

function laneClass(speaker: string): string {
  for (const [pattern, cls] of SPEAKER_TEAM) {
    if (pattern.test(speaker)) return cls;
  }
  return "border-l-border";
}

export function DebateTimeline({ timeline }: { timeline: Timeline }) {
  return (
    <ol className="space-y-3" data-testid="debate-timeline">
      {timeline.entries.map((entry, i) => (
        <li
          key={i}
          className={cn(
            "rounded-sm border-l-[3px] pl-3.5",
            laneClass(entry.speaker),
          )}
        >
          <div className="flex flex-wrap items-baseline gap-2">
            <DirectionBadge value={entry.stance} showWord={false} />
            <span className="font-bold">{entry.speaker}</span>
            <span className="text-[11px] text-fg-subtle">
              {entry.stance ?? ""} · conf {entry.confidence ?? "–"}
            </span>
          </div>
          <p className="mt-[3px] text-[13px] text-fg-muted">
            <Emphasis text={entry.argument} />
          </p>
          {entry.cited.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {entry.cited.map((ref) => (
                <span
                  key={ref}
                  className="inline-flex items-center rounded-[7px] bg-surface-2 px-2 py-0.5 font-mono text-[10px] text-fg-muted"
                >
                  {ref}
                </span>
              ))}
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}
