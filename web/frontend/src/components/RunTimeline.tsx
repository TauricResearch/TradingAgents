import { useState, useMemo } from "react";
import { useFocusedRunEvents } from "../hooks/useFocusedRunEvents";
import type { WsEvent } from "../lib/events";

const STAGES = [
  { key: "market", label: "Market" },
  { key: "sentiment", label: "Sentiment" },
  { key: "news", label: "News" },
  { key: "fundamentals", label: "Fundamentals" },
  { key: "research", label: "Research" },
  { key: "risk", label: "Risk" },
  { key: "trader", label: "Trader" },
] as const;

type StageKey = (typeof STAGES)[number]["key"];

/* Map node name -> stage key (mirrors runner._STAGE_MAP). */
const NODE_TO_STAGE: Record<string, StageKey> = {
  "Market Analyst": "market",
  "Sentiment Analyst": "sentiment",
  "News Analyst": "news",
  "Fundamentals Analyst": "fundamentals",
  "Bull Researcher": "research",
  "Bear Researcher": "research",
  "Research Manager": "research",
  "Trader": "trader",
  "Aggressive Analyst": "risk",
  "Conservative Analyst": "risk",
  "Neutral Analyst": "risk",
};

function findLast<T>(arr: T[], fn: (item: T) => boolean): T | undefined {
  for (let i = arr.length - 1; i >= 0; i--) {
    if (fn(arr[i])) return arr[i];
  }
  return undefined;
}

interface StageDerived {
  status: "idle" | "running" | "done" | "errored";
  node?: string;
  thinkingLog: string[];
  excerpt?: string;
  fullText?: string;
}

function deriveStage(stage: StageKey, events: WsEvent[]): StageDerived {
  const completed = findLast(
    events,
    (e) => e.type === "analyst_completed" && (e.data as any)?.stage === stage,
  );
  const started = findLast(
    events,
    (e) => e.type === "analyst_started" && NODE_TO_STAGE[(e.data as any)?.node] === stage,
  );

  const hasFailed = events.some((e) => e.type === "run_failed");

  if (completed) {
    const d = completed.data as Record<string, unknown>;
    return {
      status: "done",
      excerpt: (d.report_excerpt as string) ?? undefined,
      fullText: (d.report_text as string) ?? undefined,
      thinkingLog: [],
    };
  }

  if (started) {
    const startIdx = events.lastIndexOf(started);
    const thinkingLog: string[] = [];
    for (let i = startIdx + 1; i < events.length; i++) {
      const e = events[i];
      if (e.type === "analyst_completed") break;
      if (e.type === "analyst_started" && e !== started) break;
      if (e.type === "analyst_thinking") {
        const d = e.data as Record<string, unknown>;
        const preview = d.text_preview as string | undefined;
        const fragment = d.text_fragment as string | undefined;
        if (preview) thinkingLog.push(`[ask] ${preview}`);
        if (fragment) thinkingLog.push(fragment);
      }
    }
    return {
      status: "running",
      node: (started.data as any)?.node ?? undefined,
      thinkingLog,
    };
  }

  return { status: hasFailed ? "errored" : "idle", thinkingLog: [] };
}

/* A segment between stages i and i+1 is:
   - "traversed" once stage i is done (we have crossed the segment,
     even if stage i+1 has not started yet)
   - "active" when stage i+1 is the currently-running one
   - "future" before any progress through it
   "failed" if a run_failed has been emitted (whole timeline is red). */
function deriveSegmentProgress(
  stages: { status: StageDerived["status"] }[],
  failed: boolean,
): Array<"traversed" | "active" | "future" | "failed"> {
  const out: Array<"traversed" | "active" | "future" | "failed"> = [];
  for (let i = 0; i < stages.length - 1; i++) {
    const cur = stages[i].status;
    const nxt = stages[i + 1].status;
    if (failed) {
      out.push("failed");
      continue;
    }
    if (cur === "done") {
      out.push("traversed");
    } else if (nxt === "running") {
      out.push("active");
    } else if (cur === "running" && nxt === "idle") {
      out.push("active");
    } else if (nxt === "errored" || cur === "errored") {
      out.push("traversed");
    } else {
      out.push("future");
    }
  }
  return out;
}

const STATUS_DOT: Record<StageDerived["status"], string> = {
  idle: "bg-slate-300 text-slate-500 border-slate-300",
  running: "bg-blue-500 text-white border-blue-500 ring-2 ring-blue-200 animate-pulse",
  done: "bg-emerald-500 text-white border-emerald-500",
  errored: "bg-rose-500 text-white border-rose-500",
};

const STATUS_LABEL: Record<StageDerived["status"], string> = {
  idle: "queued",
  running: "running…",
  done: "✓ done",
  errored: "errored",
};

const SEGMENT_CLASS: Record<"traversed" | "active" | "future" | "failed", string> = {
  traversed: "bg-emerald-400",
  active: "bg-blue-400 animate-pulse",
  future: "bg-slate-200",
  failed: "bg-rose-400",
};

/* ── component ─────────────────────────────────────── */

export function RunTimeline() {
  const events = useFocusedRunEvents();
  const [expanded, setExpanded] = useState<StageKey | null>(null);

  const derived = useMemo(
    () => STAGES.map((s) => ({ key: s.key, label: s.label, info: deriveStage(s.key, events) })),
    [events],
  );

  const failed = events.some((e) => e.type === "run_failed");
  const segmentProgress = useMemo(
    () => deriveSegmentProgress(derived.map((d) => d.info), failed),
    [derived, failed],
  );

  const toggle = (key: StageKey) => setExpanded((prev) => (prev === key ? null : key));

  return (
    <div className="mb-4">
      {/* timeline strip */}
      <div className="relative px-2 py-3" data-testid="run-timeline">
        <div className="flex items-start">
          {derived.map((d, i) => {
            const isExpanded = expanded === d.key;
            return (
              <div key={d.key} className="flex items-start flex-1 last:flex-none">
                {/* node column */}
                <div className="flex flex-col items-center" style={{ minWidth: 0 }}>
                  <button
                    type="button"
                    data-testid={`stage-${d.key}`}
                    data-status={d.info.status}
                    data-expanded={isExpanded}
                    onClick={() => toggle(d.key)}
                    aria-expanded={isExpanded}
                    aria-label={`${d.label} stage: ${STATUS_LABEL[d.info.status]}`}
                    className={`w-8 h-8 rounded-full border-2 flex items-center justify-center text-xs font-semibold transition-all hover:scale-110 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-400 ${STATUS_DOT[d.info.status]}`}
                  >
                    {d.info.status === "done" ? "✓" : i + 1}
                  </button>
                  <div className="mt-1.5 text-[11px] font-medium text-slate-700 text-center truncate w-full">
                    {d.label}
                  </div>
                  <div className="text-[10px] text-slate-400 text-center">
                    {STATUS_LABEL[d.info.status]}
                  </div>
                </div>
                {/* segment */}
                {i < derived.length - 1 && (
                  <div
                    data-testid="timeline-segment"
                    data-progress={segmentProgress[i]}
                    aria-hidden="true"
                    className={`flex-1 h-1 mx-1 mt-3.5 rounded-full transition-colors ${SEGMENT_CLASS[segmentProgress[i]]}`}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* inline details panel (accordion: at most one open) */}
      {expanded && (() => {
        const d = derived.find((x) => x.key === expanded);
        if (!d) return null;
        const isRunning = d.info.status === "running";
        return (
          <div
            data-testid={`stage-${d.key}-details`}
            className="mt-2 rounded-lg border border-slate-200 bg-white p-3 text-sm"
          >
            <div className="flex items-center justify-between mb-2">
              <div className="font-medium">
                {d.label}
                {d.info.node && (
                  <span className="ml-2 text-xs text-slate-500 font-normal">
                    {d.info.node}
                  </span>
                )}
              </div>
              <button
                onClick={() => toggle(d.key)}
                className="text-xs text-slate-500 hover:text-slate-800"
              >
                Close
              </button>
            </div>
            {isRunning ? (
              d.info.thinkingLog.length > 0 ? (
                <pre className="text-xs leading-relaxed text-slate-700 bg-slate-50 rounded p-2 max-h-64 overflow-y-auto whitespace-pre-wrap font-mono">
                  {d.info.thinkingLog.join("\n")}
                  <span className="inline-block w-1.5 h-3 bg-blue-500 animate-pulse ml-0.5 align-middle" />
                </pre>
              ) : (
                <div className="text-xs text-slate-500 italic">
                  {d.info.node} is running…
                </div>
              )
            ) : d.info.status === "done" ? (
              <div className="space-y-2">
                {d.info.excerpt && (
                  <div className="text-xs text-slate-700">{d.info.excerpt}</div>
                )}
                {d.info.fullText && (
                  <pre className="text-xs leading-relaxed text-slate-800 bg-slate-50 rounded p-2 max-h-64 overflow-y-auto whitespace-pre-wrap font-mono">
                    {d.info.fullText}
                  </pre>
                )}
                {!d.info.excerpt && !d.info.fullText && (
                  <div className="text-xs text-slate-500 italic">No report content.</div>
                )}
              </div>
            ) : d.info.status === "errored" ? (
              <div className="text-xs text-rose-700">
                This stage did not run because the run failed earlier.
              </div>
            ) : (
              <div className="text-xs text-slate-500 italic">
                Waiting for {d.label} to start…
              </div>
            )}
          </div>
        );
      })()}
    </div>
  );
}
