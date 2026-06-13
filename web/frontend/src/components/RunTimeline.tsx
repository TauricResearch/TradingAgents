import { useState, useMemo, useEffect } from "react";
import { useFocusedRunEvents } from "../hooks/useFocusedRunEvents";
import { formatDuration } from "../lib/format";
import type { WsEvent } from "../lib/events";

type StageKey = "market" | "sentiment" | "news" | "fundamentals" | "research" | "risk" | "trader";

interface StageConfig {
  key: StageKey;
  label: string;
  icon: string;
  agentColor: string;
  description: string;
}

const STAGES: StageConfig[] = [
  { key: "market", label: "Market", icon: "M", agentColor: "agent-market", description: "Technical indicators & price patterns" },
  { key: "sentiment", label: "Sentiment", icon: "S", agentColor: "agent-sentiment", description: "Social media & market mood" },
  { key: "news", label: "News", icon: "N", agentColor: "agent-news", description: "Global news & macro analysis" },
  { key: "fundamentals", label: "Fundamentals", icon: "F", agentColor: "agent-fundamentals", description: "Financials & performance metrics" },
  { key: "research", label: "Research", icon: "R", agentColor: "agent-research", description: "Bull & Bear debate analysis" },
  { key: "risk", label: "Risk", icon: "⚠", agentColor: "agent-risk", description: "Portfolio risk assessment" },
  { key: "trader", label: "Trader", icon: "T", agentColor: "agent-trader", description: "Execution & position sizing" },
] as const;

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

interface StageDerived {
  status: "idle" | "running" | "done" | "errored";
  node?: string;
  thinkingLog: string[];
  duration_ms?: number;
  excerpt?: string;
  fullText?: string;
}

function deriveStage(stage: StageKey, events: WsEvent[]): StageDerived {
  // The "active iteration" of a stage is bounded by:
  //   - the FIRST analyst_started for this stage (its entry)
  //   - the analyst_completed for this stage (its exit), if any
  //   - otherwise: the most recent analyst_started for a different
  //     stage, or end-of-events
  // We deliberately use the FIRST start, not the last, so that thinking
  // events from earlier tool-call round-trips of the SAME stage are
  // included in the log. The old behaviour used `findLast` here and so
  // truncated the log to the last iteration.
  const firstStartIdx = events.findIndex(
    (e) => e.type === "analyst_started" && NODE_TO_STAGE[(e.data as any)?.node] === stage,
  );
  // For "node" attribution use the last analyst_started for this stage
  // (the active node label) — but only within the active iteration.
  const lastStartIdx = (() => {
    for (let i = events.length - 1; i >= 0; i--) {
      const e = events[i];
      if (e.type === "analyst_started" && NODE_TO_STAGE[(e.data as any)?.node] === stage) {
        return i;
      }
    }
    return -1;
  })();

  // A "real" completion is one that carries a report. Multiple
  // completions for the same stage can exist (debate-style nodes like
  // Bull/Bear emit analyst_completed with no report; Research Manager
  // emits one with the investment_plan). A stage is only "done" if at
  // least one of its completions delivered a report — otherwise the
  // user used to see a green checkmark next to the stage and a
  // "No report content." placeholder inside, which is misleading.
  const hasReport = events.some((e) => {
    if (e.type !== "analyst_completed") return false;
    if ((e.data as any)?.stage !== stage) return false;
    const d = e.data as Record<string, unknown>;
    return !!(d.report_excerpt || d.report_text);
  });
  const lastReportEvent = (() => {
    for (let i = events.length - 1; i >= 0; i--) {
      const e = events[i];
      if (e.type !== "analyst_completed") continue;
      if ((e.data as any)?.stage !== stage) continue;
      const d = e.data as Record<string, unknown>;
      if (d.report_excerpt || d.report_text) return e;
    }
    return undefined;
  })();

  const hasFailed = events.some((e) => e.type === "run_failed");

  // Stage completed: show the persisted report excerpt/text.
  if (hasReport && lastReportEvent) {
    const d = lastReportEvent.data as Record<string, unknown>;
    return {
      status: "done",
      excerpt: (d.report_excerpt as string) ?? undefined,
      fullText: (d.report_text as string) ?? undefined,
      duration_ms: typeof d.duration_ms === "number" ? d.duration_ms : undefined,
      thinkingLog: [],
    };
  }

  // Stage never started. Errored if the whole run failed, otherwise idle.
  if (firstStartIdx === -1) {
    return { status: hasFailed ? "errored" : "idle", thinkingLog: [] };
  }

  // Stage started but never completed. The end of the active iteration
  // is: the most recent analyst_started for a DIFFERENT stage (we
  // already moved on), or end-of-events. We DON'T cap at the last
  // analyst_started for THIS stage — that would chop off the rest of
  // its log.
  const upperBound = (() => {
    for (let i = lastStartIdx + 1; i < events.length; i++) {
      const e = events[i];
      if (e.type === "analyst_started") {
        const nodeStage = NODE_TO_STAGE[(e.data as any)?.node];
        if (nodeStage && nodeStage !== stage) return i;
      }
    }
    return events.length;
  })();

  // Collect thinking events from FIRST start up to upperBound, skipping
  // events from other stages (tool nodes, other analysts).
  const thinkingLog: string[] = [];
  for (let i = firstStartIdx + 1; i < upperBound; i++) {
    const e = events[i];
    if (e.type === "analyst_thinking") {
      const d = e.data as Record<string, unknown>;
      const preview = d.text_preview as string | undefined;
      const fragment = d.text_fragment as string | undefined;
      if (preview) thinkingLog.push(`[ask] ${preview}`);
      if (fragment) thinkingLog.push(fragment);
    }
  }

  // If the run failed while this stage was active, mark it errored
  // (its report was never persisted) — even if the last event is just a
  // thinking event with no completion.
  if (hasFailed) {
    return {
      status: "errored",
      node: lastStartIdx !== -1 ? (events[lastStartIdx].data as any)?.node ?? undefined : undefined,
      thinkingLog,
    };
  }

  return {
    status: "running",
    node: lastStartIdx !== -1 ? (events[lastStartIdx].data as any)?.node ?? undefined : undefined,
    thinkingLog,
  };
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

/* Per-stage agent color tokens (used inline to avoid complex Tailwind JIT). */
const AGENT_COLORS: Record<string, { base: string; dim: string; ring: string }> = {
  market:       { base: "#38bdf8", dim: "rgba(56,189,248,0.15)",  ring: "rgba(56,189,248,0.3)" },
  sentiment:    { base: "#a78bfa", dim: "rgba(167,139,250,0.15)", ring: "rgba(167,139,250,0.3)" },
  news:         { base: "#34d399", dim: "rgba(52,211,153,0.15)",  ring: "rgba(52,211,153,0.3)" },
  fundamentals: { base: "#f472b6", dim: "rgba(244,114,182,0.15)", ring: "rgba(244,114,182,0.3)" },
  research:     { base: "#fb923c", dim: "rgba(251,146,60,0.15)",  ring: "rgba(251,146,60,0.3)" },
  risk:         { base: "#ef4444", dim: "rgba(239,68,68,0.15)",   ring: "rgba(239,68,68,0.3)" },
  trader:       { base: "#fbbf24", dim: "rgba(251,191,36,0.15)",  ring: "rgba(251,191,36,0.3)" },
};

const STATUS_DOT: Record<StageDerived["status"], string> = {
  idle: "",
  running: "ring-2 animate-pulse",
  done: "",
  errored: "",
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

function lastStartedIsoFor(stage: StageKey, events: WsEvent[]): string | undefined {
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (e.type === "analyst_started" && NODE_TO_STAGE[(e.data as any)?.node] === stage) {
      return (e.data as any)?.ts ?? undefined;
    }
  }
  return undefined;
}

function StageButton({
  status,
  testKey,
  durationMs,
  startedAtIso,
  isExpanded,
  onClick,
  ariaLabel,
  agentColor,
  agentIcon,
}: {
  status: StageDerived["status"];
  testKey: string;
  durationMs?: number;
  startedAtIso?: string;
  isExpanded: boolean;
  onClick: () => void;
  ariaLabel: string;
  agentColor: string;
  agentIcon: string;
}) {
  const isRunning = status === "running";
  const [elapsed, setElapsed] = useState<number>(0);
  const ac = AGENT_COLORS[agentColor] ?? AGENT_COLORS.market;

  useEffect(() => {
    if (!isRunning || !startedAtIso) return;
    const tick = () => {
      const ms = Date.now() - new Date(startedAtIso).getTime();
      setElapsed(Math.max(0, Math.floor(ms / 1000)));
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [isRunning, startedAtIso]);

  const baseShape = isRunning
    ? "min-w-[3.25rem] h-9 px-3 rounded-full"
    : "w-9 h-9 rounded-full";

  const dynamicStyle: React.CSSProperties = {
    borderColor: isRunning || status === "done" ? ac.base : "rgba(71,85,105,0.5)",
    backgroundColor: status === "done" ? ac.dim : status === "running" ? ac.dim : isExpanded ? "rgba(30,41,59,0.8)" : "transparent",
    color: status === "idle" ? "#64748b" : ac.base,
    boxShadow: isRunning ? `0 0 12px ${ac.ring}` : status === "done" ? `0 0 6px ${ac.ring}` : "none",
  };

  return (
    <button
      type="button"
      data-testid={`stage-${testKey}`}
      data-status={status}
      data-expanded={isExpanded}
      data-duration-ms={durationMs}
      onClick={onClick}
      aria-expanded={isExpanded}
      aria-label={ariaLabel}
      title={durationMs != null ? formatDuration(durationMs) : undefined}
      className={`flex items-center justify-center transition-all duration-200 hover:scale-110 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-market-DEFAULT ${baseShape} ${STATUS_DOT[status]}`}
      style={dynamicStyle}
    >
      {isRunning ? (
        <>
          <svg className="animate-spin h-3 w-3 shrink-0" viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" fill="none" />
            <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" fill="none" strokeLinecap="round" />
          </svg>
          <span className="ml-1 text-[10px] font-mono font-semibold">{formatElapsed(elapsed)}</span>
        </>
      ) : (
        <span className="text-sm font-bold leading-none">{status === "done" ? "✓" : agentIcon}</span>
      )}
    </button>
  );
}

function formatElapsed(s: number): string {
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}m ${r}s`;
}

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

  const TEAM_GROUPS = [
    { label: "Analyst Team", indices: [0, 1, 2, 3], color: "#38bdf8" },
    { label: "Research", indices: [4], color: "#fb923c" },
    { label: "Risk Mgmt", indices: [5], color: "#ef4444" },
    { label: "Trader", indices: [6], color: "#fbbf24" },
  ] as const;

  return (
    <div className="mb-4">
      {/* timeline strip */}
      <div className="relative px-2 py-4 rounded-xl bg-slate-900/40 border border-slate-800/60" data-testid="run-timeline">
        {/* Team grouping labels */}
        <div className="flex items-start mb-3 px-1">
          {TEAM_GROUPS.map((group) => {
            const groupStages = group.indices.map((i) => derived[i].info.status);
            const allDone = groupStages.every((s) => s === "done");
            const anyActive = groupStages.some((s) => s === "running");
            return (
              <div
                key={group.label}
                className="flex-1 last:flex-none text-center"
                style={{ maxWidth: group.indices.length > 1 ? `${group.indices.length * 14}%` : "14%" }}
              >
                <span
                  className="text-[9px] font-semibold uppercase tracking-widest transition-colors duration-300"
                  style={{
                    color: allDone ? group.color : anyActive ? `${group.color}99` : "#334155",
                  }}
                >
                  {group.label}
                </span>
              </div>
            );
          })}
        </div>
        <div className="flex items-start">
          {derived.map((d, i) => {
            const isExpanded = expanded === d.key;
            const stageConfig = STAGES.find((s) => s.key === d.key)!;
            return (
              <div key={d.key} className="flex items-start flex-1 last:flex-none">
                {/* node column */}
                <div className="flex flex-col items-center" style={{ minWidth: 0 }}>
                  <StageButton
                    testKey={d.key}
                    status={d.info.status}
                    durationMs={d.info.duration_ms}
                    startedAtIso={lastStartedIsoFor(d.key, events)}
                    isExpanded={isExpanded}
                    onClick={() => toggle(d.key)}
                    ariaLabel={`${d.label} stage: ${STATUS_LABEL[d.info.status]}`}
                    agentColor={stageConfig.key}
                    agentIcon={stageConfig.icon}
                  />
                  <div className="mt-1.5 text-[11px] font-semibold text-slate-400 text-center truncate w-full max-w-[80px]">
                    {d.label}
                  </div>
                  <div className="text-[10px] text-slate-600 text-center font-mono">
                    {d.info.duration_ms != null ? formatDuration(d.info.duration_ms) : STATUS_LABEL[d.info.status]}
                  </div>
                </div>
                {/* segment */}
                {i < derived.length - 1 && (
                  <div
                    data-testid="timeline-segment"
                    data-progress={segmentProgress[i]}
                    aria-hidden="true"
                    className={`flex-1 h-0.5 mx-1 mt-[18px] rounded-full transition-colors duration-500 ${SEGMENT_CLASS[segmentProgress[i]]}`}
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
        const stageConfig = STAGES.find((s) => s.key === d.key)!;
        const ac = AGENT_COLORS[d.key] ?? AGENT_COLORS.market;
        const isRunning = d.info.status === "running";
        const isDone = d.info.status === "done";
        return (
          <div
            data-testid={`stage-${d.key}-details`}
            className="mt-2 rounded-xl border border-slate-700/50 bg-slate-900/60 backdrop-blur-sm p-4 text-sm animate-fade-in"
            style={{ borderLeftColor: ac.base, borderLeftWidth: 2 }}
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span
                  className="inline-flex items-center justify-center w-6 h-6 rounded-md text-xs font-bold"
                  style={{ backgroundColor: ac.dim, color: ac.base }}
                >
                  {stageConfig.icon}
                </span>
                <div>
                  <div className="font-semibold text-slate-200">
                    {d.label}
                  </div>
                  <div className="text-[10px] text-slate-500 font-medium">{stageConfig.description}</div>
                </div>
                {d.info.node && (
                  <span className="ml-2 text-[10px] font-mono text-slate-500 bg-slate-800/60 px-2 py-0.5 rounded">
                    {d.info.node}
                  </span>
                )}
              </div>
              <button
                onClick={() => toggle(d.key)}
                className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
              >
                Close
              </button>
            </div>
            {isRunning ? (
              d.info.thinkingLog.length > 0 ? (
                <pre className="text-xs leading-relaxed text-slate-300 bg-slate-950/60 rounded-lg p-3 max-h-64 overflow-y-auto whitespace-pre-wrap font-mono border border-slate-800/50">
                  {d.info.thinkingLog.join("\n")}
                  <span className="inline-block w-1.5 h-3 ml-0.5 align-middle rounded-sm" style={{ backgroundColor: ac.base }} />
                </pre>
              ) : (
                <div className="flex items-center gap-2 text-xs text-slate-500 italic">
                  <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ backgroundColor: ac.base }} />
                  {d.info.node ?? stageConfig.label} is thinking…
                </div>
              )
            ) : isDone ? (
              <div className="space-y-2">
                {d.info.excerpt && (
                  <div className="text-xs text-slate-400 leading-relaxed">{d.info.excerpt}</div>
                )}
                {d.info.fullText && (
                  <pre className="text-xs leading-relaxed text-slate-300 bg-slate-950/60 rounded-lg p-3 max-h-64 overflow-y-auto whitespace-pre-wrap font-mono border border-slate-800/50">
                    {d.info.fullText}
                  </pre>
                )}
                {!d.info.excerpt && !d.info.fullText && (
                  <div className="text-xs text-slate-600 italic">No report content.</div>
                )}
              </div>
            ) : d.info.status === "errored" ? (
              <div className="flex items-center gap-2 text-xs text-red-400">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
                </svg>
                This stage did not run because the run failed earlier.
              </div>
            ) : (
              <div className="flex items-center gap-2 text-xs text-slate-600 italic">
                <span className="w-1.5 h-1.5 rounded-full bg-slate-700" />
                Waiting for {d.label} to start…
              </div>
            )}
          </div>
        );
      })()}
    </div>
  );
}
