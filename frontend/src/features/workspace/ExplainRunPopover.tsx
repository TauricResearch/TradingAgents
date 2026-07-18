/** Click-to-explain (chart Phase 1): a decision zone/marker on the chart
 * opens this popover — the run's verdict, honest sample-sized p(win),
 * votes, evidence, counterarguments, a link to the full decision page,
 * and the grounded ask-the-record chat. Everything renders the recorded
 * numbers; nothing is recomputed here (Constraint 2). */
import { X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { EvidenceChat } from "@/components/EvidenceChat";
import { SkeletonCard } from "@/components/ui/skeleton";
import { useRunRecommendation } from "@/lib/api/queries";
import { cn } from "@/lib/utils";

export interface ExplainTarget {
  runId: string;
  x: number;
  y: number;
}

export function ExplainRunPopover({
  target,
  onClose,
}: {
  target: ExplainTarget;
  onClose: () => void;
}) {
  const rec = useRunRecommendation(target.runId);
  const [showChat, setShowChat] = useState(false);
  const boxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const onDown = (e: PointerEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onDown);
    };
  }, [onClose]);

  const d = rec.data;
  const action = d?.action ?? null;
  const evidence = d?.evidence ?? [];
  const counters = d?.counterarguments ?? [];
  const tally = d?.vote_tally ?? {};

  return (
    <div
      ref={boxRef}
      data-testid="explain-run-popover"
      className="absolute z-40 w-80 max-w-[calc(100%-16px)] rounded-xl border border-border-strong bg-surface p-3 text-xs shadow-(--shadow-2)"
      style={{
        left: Math.max(8, Math.min(target.x, 9999)),
        top: Math.max(8, target.y + 12),
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="font-semibold text-fg">
          {rec.isPending ? (
            "Loading decision…"
          ) : d?.rejection ? (
            <>
              Rejected at {d.rejection.stage ?? "gate"}
              {d.rejection.reasons?.[0] && (
                <span className="block font-normal text-fg-muted">
                  {d.rejection.reasons[0]}
                </span>
              )}
            </>
          ) : (
            <>
              <span
                className={cn(
                  action === "BUY" && "text-bull",
                  action === "SELL" && "text-bear",
                )}
              >
                {action ?? "—"}
              </span>{" "}
              {d?.symbol}
              {d?.confidence != null && (
                <span className="text-fg-muted"> · {d.confidence}%</span>
              )}
            </>
          )}
        </div>
        <button
          aria-label="Close explanation"
          onClick={onClose}
          className="rounded p-0.5 text-fg-subtle hover:text-fg"
        >
          <X size={13} />
        </button>
      </div>

      {rec.isPending ? (
        <SkeletonCard lines={3} />
      ) : d == null ? (
        <p className="mt-1 text-fg-subtle">
          This run's record is unavailable.
        </p>
      ) : (
        <div className="mt-2 space-y-2">
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-fg-muted">
            {d.market_regime && <span>regime {d.market_regime}</span>}
            {d.p_win != null && (
              <span>
                p(win) {(d.p_win.p_win * 100).toFixed(0)}%{" "}
                <span className="text-fg-subtle">(n={d.p_win.n})</span>
              </span>
            )}
            {Object.keys(tally).length > 0 && (
              <span>
                votes{" "}
                {Object.entries(tally)
                  .map(([k, v]) => `${k} ${v}`)
                  .join(" · ")}
              </span>
            )}
          </div>

          {evidence.length > 0 && (
            <div>
              <div className="mb-1 font-semibold text-fg">Evidence</div>
              <ul className="space-y-1">
                {evidence.slice(0, 3).map((e, i) => (
                  <li key={i} className="text-fg-muted">
                    <span className="font-mono text-[10px] text-fg-subtle">
                      [{e.agent_id}]
                    </span>{" "}
                    {e.claim}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {counters.length > 0 && (
            <div>
              <div className="mb-1 font-semibold text-fg">
                Counterarguments
              </div>
              <ul className="space-y-1">
                {counters.slice(0, 2).map((e, i) => (
                  <li key={i} className="text-fg-muted">
                    <span className="font-mono text-[10px] text-fg-subtle">
                      [{e.agent_id}]
                    </span>{" "}
                    {e.claim}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex items-center justify-between border-t border-border pt-2">
            <Link
              to={`/decisions/${target.runId}`}
              className="text-accent hover:underline"
            >
              Full decision →
            </Link>
            <button
              className="text-fg-subtle hover:text-fg"
              onClick={() => setShowChat((v) => !v)}
            >
              {showChat ? "Hide ask" : "Ask the record"}
            </button>
          </div>
          {showChat && <EvidenceChat runId={target.runId} />}
        </div>
      )}
    </div>
  );
}
