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

/* ── helpers ───────────────────────────────────────── */

function findLast<T>(arr: T[], fn: (item: T) => boolean): T | undefined {
  for (let i = arr.length - 1; i >= 0; i--) {
    if (fn(arr[i])) return arr[i];
  }
  return undefined;
}

interface StageDerived {
  status: "idle" | "running" | "done" | "errored";
  /** node name shown while running */
  node?: string;
  /** LLM thinking / answer text fragments accumulated while running */
  thinkingLog: string[];
  /** completed-stage excerpt */
  excerpt?: string;
  /** completed-stage full report */
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
    // Gather all thinking events between started and now (no completed yet).
    // Since events are in chronological order, find the started index and
    // collect everything after it that belongs to this stage.
    const startIdx = events.lastIndexOf(started);
    const thinkingLog: string[] = [];
    for (let i = startIdx + 1; i < events.length; i++) {
      const e = events[i];
      if (e.type === "analyst_completed") break; // next stage started
      if (e.type === "analyst_started" && e !== started) break; // next stage
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

/* ── component ─────────────────────────────────────── */

export function StageGrid() {
  const events = useFocusedRunEvents();
  const [expanded, setExpanded] = useState<StageKey | null>(null);
  const [expandedLog, setExpandedLog] = useState<StageKey | null>(null);

  const toggleExpand = (key: StageKey) => {
    setExpanded((prev) => (prev === key ? null : key));
  };

  const toggleLog = (key: StageKey) => {
    setExpandedLog((prev) => (prev === key ? null : key));
  };

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2 mb-4">
      {STAGES.map((s) => {
        const info = deriveStage(s.key, events);
        const isRunning = info.status === "running";
        const logPreview = isRunning && info.thinkingLog.length > 0
          ? info.thinkingLog.join("\n").slice(0, 300)
          : "";
        const allLog = isRunning ? info.thinkingLog.join("\n") : "";
        const hasLog = isRunning && info.thinkingLog.length > 0;

        return (
          <div
            key={s.key}
            data-testid={`stage-${s.key}`}
            data-status={info.status}
            className={`rounded-lg border p-3 text-sm transition-all ${
              info.status === "done"
                ? "border-emerald-200 bg-emerald-50"
                : info.status === "errored"
                  ? "border-rose-200 bg-rose-50"
                  : info.status === "running"
                    ? "border-blue-200 bg-blue-50 ring-1 ring-blue-300"
                    : "border-slate-200 bg-white"
            }`}
          >
            {/* header row */}
            <div className="font-medium">{s.label}</div>
            <div className="text-xs text-slate-500 mt-1">
              {info.status === "done"
                ? "✓ done"
                : info.status === "errored"
                  ? "errored"
                  : info.status === "running"
                    ? "running…"
                    : "queued"}
            </div>

            {/* running stage: show node name + live LLM output */}
            {isRunning && info.node && (
              <div className="mt-2 text-[11px] text-blue-600 truncate font-medium">
                {info.node}
              </div>
            )}
            {isRunning && logPreview && (
              <div
                className={`mt-1 text-[11px] text-blue-800 leading-relaxed whitespace-pre-wrap ${
                  expandedLog !== s.key ? "line-clamp-4" : ""
                }`}
              >
                {expandedLog === s.key ? allLog : logPreview}
                {info.thinkingLog.length > 0 && (
                  <span className="inline-block w-1.5 h-3 bg-blue-500 animate-pulse ml-0.5 align-middle" />
                )}
              </div>
            )}
            {isRunning && hasLog && expandedLog !== s.key && info.thinkingLog.length > 3 && (
              <button
                onClick={() => toggleLog(s.key)}
                className="mt-1 text-[11px] text-blue-500 hover:underline block"
              >
                Show all {info.thinkingLog.length} messages
              </button>
            )}
            {isRunning && hasLog && expandedLog === s.key && (
              <button
                onClick={() => toggleLog(s.key)}
                className="mt-1 text-[11px] text-blue-500 hover:underline block"
              >
                Show less
              </button>
            )}

            {/* completed stage: show excerpt (clickable for full) */}
            {info.status === "done" && info.excerpt && (
              <div
                className={`mt-2 text-[11px] text-slate-600 leading-relaxed ${
                  expanded !== s.key ? "line-clamp-3" : ""
                } ${info.fullText ? "cursor-pointer select-none" : ""}`}
                onClick={info.fullText ? () => toggleExpand(s.key) : undefined}
              >
                {info.excerpt}
              </div>
            )}
            {expanded === s.key && info.fullText && (
              <pre className="mt-2 text-[11px] text-slate-800 bg-white/60 rounded p-1.5 border border-slate-200 max-h-48 overflow-y-auto whitespace-pre-wrap">
                {info.fullText}
              </pre>
            )}
          </div>
        );
      })}
    </div>
  );
}
