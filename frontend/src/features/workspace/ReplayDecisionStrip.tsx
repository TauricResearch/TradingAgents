/** Decision replay strip (chart Phase 1): shown when replay auto-pauses
 * on a bar the AI decided at. Steps through the run's recorded debate —
 * user-driven, not clock-synced: node timestamps live at seconds scale
 * inside one bar, and pretending the debate spans bars would be a lie. */
import { ChevronLeft, ChevronRight, Play } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useRunTimeline } from "@/lib/api/queries";

export function ReplayDecisionStrip({
  runId,
  onResume,
}: {
  runId: string;
  onResume: () => void;
}) {
  const timeline = useRunTimeline(runId, false);
  const [step, setStep] = useState(0);
  useEffect(() => setStep(0), [runId]);

  const entries = timeline.data?.entries ?? [];
  const entry = entries[step];
  const nodes = timeline.data?.node_sequence ?? [];

  return (
    <div
      data-testid="replay-decision-strip"
      className="mt-2 rounded-xl border border-border bg-surface-2/60 px-3 py-2 text-xs"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-semibold text-fg">
          AI decided here
          {nodes.length > 0 && (
            <span className="ml-2 font-normal text-fg-subtle">
              {nodes.join(" → ")}
            </span>
          )}
        </span>
        <span className="flex items-center gap-1">
          <Button
            size="icon"
            variant="ghost"
            aria-label="Previous debate turn"
            disabled={step <= 0}
            onClick={() => setStep((s) => Math.max(0, s - 1))}
          >
            <ChevronLeft size={13} />
          </Button>
          <span className="tabular text-fg-subtle">
            {entries.length ? `${step + 1}/${entries.length}` : "—"}
          </span>
          <Button
            size="icon"
            variant="ghost"
            aria-label="Next debate turn"
            disabled={step >= entries.length - 1}
            onClick={() => setStep((s) => Math.min(entries.length - 1, s + 1))}
          >
            <ChevronRight size={13} />
          </Button>
          <Link to={`/decisions/${runId}`} className="ml-2 text-accent hover:underline">
            Full decision →
          </Link>
          <Button size="sm" variant="ghost" onClick={onResume}>
            <Play size={12} /> Resume
          </Button>
        </span>
      </div>
      {entry && (
        <p className="mt-1 text-fg-muted">
          <span className="font-semibold text-fg">{entry.speaker}</span>
          {entry.stance ? ` (${entry.stance})` : ""}
          {": "}
          {entry.argument}
        </p>
      )}
    </div>
  );
}
