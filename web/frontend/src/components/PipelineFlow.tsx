import { useState, useEffect, useMemo, useRef } from "react";
import type { WsEvent } from "../lib/events";
import { formatDuration } from "../lib/format";

/* ─── agent-to-stage mapping ──────────────────────────── */

const AGENT_TO_STAGE: Record<string, string> = {
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
  "Portfolio Manager": "risk",
};

const STAGES: { key: string; label: string; icon: string }[] = [
  { key: "market", label: "Market", icon: "M" },
  { key: "sentiment", label: "Sentiment", icon: "S" },
  { key: "news", label: "News", icon: "N" },
  { key: "fundamentals", label: "Fundamentals", icon: "F" },
  { key: "research", label: "Research", icon: "R" },
  { key: "trader", label: "Trader", icon: "T" },
  { key: "risk", label: "Risk", icon: "⚠" },
];

const NODE_TO_STAGE: Record<string, string> = {
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
  "Portfolio Manager": "risk",
};

const AGENT_ORDER_IN_STAGE: Record<string, number> = {
  "Market Analyst": 0,
  "Sentiment Analyst": 0,
  "News Analyst": 0,
  "Fundamentals Analyst": 0,
  "Trader": 0,
  "Bull Researcher": 0,
  "Bear Researcher": 1,
  "Research Manager": 2,
  "Aggressive Analyst": 0,
  "Conservative Analyst": 1,
  "Neutral Analyst": 2,
  "Portfolio Manager": 3,
};

/* ─── team definitions ─────────────────────────────────── */

interface AgentDef {
  name: string;
}

interface TeamDef {
  id: string;
  label: string;
  icon: string;
  agents: AgentDef[];
  color: string;
  bgDim: string;
  stageKeys: string[];
}

const TEAMS: TeamDef[] = [
  {
    id: "analysts",
    label: "Analyst Team",
    icon: "📊",
    agents: [
      { name: "Market Analyst" },
      { name: "Sentiment Analyst" },
      { name: "News Analyst" },
      { name: "Fundamentals Analyst" },
    ],
    color: "#38bdf8",
    bgDim: "rgba(56,189,248,0.08)",
    stageKeys: ["market", "sentiment", "news", "fundamentals"],
  },
  {
    id: "research",
    label: "Research Team",
    icon: "🔬",
    agents: [
      { name: "Bull Researcher" },
      { name: "Bear Researcher" },
      { name: "Research Manager" },
    ],
    color: "#fb923c",
    bgDim: "rgba(251,146,60,0.08)",
    stageKeys: ["research"],
  },
  {
    id: "trader",
    label: "Trading Team",
    icon: "💼",
    agents: [
      { name: "Trader" },
    ],
    color: "#fbbf24",
    bgDim: "rgba(251,191,36,0.08)",
    stageKeys: ["trader"],
  },
  {
    id: "risk",
    label: "Risk Management",
    icon: "⚠️",
    agents: [
      { name: "Aggressive Analyst" },
      { name: "Conservative Analyst" },
      { name: "Neutral Analyst" },
    ],
    color: "#ef4444",
    bgDim: "rgba(239,68,68,0.08)",
    stageKeys: ["risk"],
  },
  {
    id: "portfolio",
    label: "Portfolio Mgmt",
    icon: "📋",
    agents: [
      { name: "Portfolio Manager" },
    ],
    color: "#a78bfa",
    bgDim: "rgba(167,139,250,0.08)",
    stageKeys: ["risk"],
  },
];

/* ─── per-stage status derivation ─────────────────────── */

type StageDerived = {
  status: "idle" | "running" | "done" | "errored";
  node?: string;
  thinkingLog: string[];
  duration_ms?: number;
  excerpt?: string;
  fullText?: string;
};

function deriveStage(stage: string, events: WsEvent[]): StageDerived {
  const firstStartIdx = events.findIndex(
    (e) => e.type === "analyst_started" && NODE_TO_STAGE[(e.data as any)?.node] === stage,
  );
  const lastStartIdx = (() => {
    for (let i = events.length - 1; i >= 0; i--) {
      const e = events[i];
      if (e.type === "analyst_started" && NODE_TO_STAGE[(e.data as any)?.node] === stage) return i;
    }
    return -1;
  })();

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

  if (firstStartIdx === -1) {
    return { status: hasFailed ? "errored" : "idle", thinkingLog: [] };
  }

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

/* ─── segment progress ────────────────────────────────── */

function deriveSegmentProgress(
  stages: { status: StageDerived["status"] }[],
  failed: boolean,
): Array<"traversed" | "active" | "future" | "failed"> {
  const out: Array<"traversed" | "active" | "future" | "failed"> = [];
  for (let i = 0; i < stages.length - 1; i++) {
    const cur = stages[i].status;
    const nxt = stages[i + 1].status;
    if (failed) { out.push("failed"); continue; }
    if (cur === "done") { out.push("traversed"); }
    else if (nxt === "running") { out.push("active"); }
    else if (cur === "running" && nxt === "idle") { out.push("active"); }
    else if (nxt === "errored" || cur === "errored") { out.push("traversed"); }
    else { out.push("future"); }
  }
  return out;
}

/* ─── per-stage agent colors ───────────────────────────── */

const AGENT_COLORS: Record<string, { base: string; dim: string; ring: string }> = {
  market:       { base: "#38bdf8", dim: "rgba(56,189,248,0.15)",  ring: "rgba(56,189,248,0.3)" },
  sentiment:    { base: "#a78bfa", dim: "rgba(167,139,250,0.15)", ring: "rgba(167,139,250,0.3)" },
  news:         { base: "#34d399", dim: "rgba(52,211,153,0.15)",  ring: "rgba(52,211,153,0.3)" },
  fundamentals: { base: "#f472b6", dim: "rgba(244,114,182,0.15)", ring: "rgba(244,114,182,0.3)" },
  research:     { base: "#fb923c", dim: "rgba(251,146,60,0.15)",  ring: "rgba(251,146,60,0.3)" },
  risk:         { base: "#ef4444", dim: "rgba(239,68,68,0.15)",   ring: "rgba(239,68,68,0.3)" },
  trader:       { base: "#fbbf24", dim: "rgba(251,191,36,0.15)",  ring: "rgba(251,191,36,0.3)" },
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

/* ─── per-agent status derivation ──────────────────────── */

type AgentStatus = "pending" | "in_progress" | "completed";

function deriveAgentStatus(agent: string, events: WsEvent[]): AgentStatus {
  const stage = AGENT_TO_STAGE[agent];
  if (!stage) return "pending";
  const started = events.some(
    (e) => e.type === "analyst_started" && (e.data as any)?.node === agent,
  );
  if (!started) return "pending";
  const stageCompletions = events.filter(
    (e) => e.type === "analyst_completed" && (e.data as any)?.stage === stage,
  ).length;
  const order = AGENT_ORDER_IN_STAGE[agent] ?? 0;
  return stageCompletions > order ? "completed" : "in_progress";
}

type TeamStatus = "idle" | "active" | "done";

function deriveTeamStatus(team: TeamDef, events: WsEvent[]): TeamStatus {
  const agentStatuses = team.agents.map((a) => deriveAgentStatus(a.name, events));
  const allPending = agentStatuses.every((s) => s === "pending");
  const allDone = agentStatuses.every((s) => s === "completed");
  if (allDone) return "done";
  if (allPending) return "idle";
  return "active";
}

/* ─── live stats ───────────────────────────────────────── */

interface LiveStats {
  agentsDone: number;
  agentsTotal: number;
  llmCalls: number;
  toolCalls: number;
  elapsedSec: number;
  hasRun: boolean;
}

function computeStats(events: WsEvent[]): LiveStats {
  const allAgents = TEAMS.flatMap((t) => t.agents.map((a) => a.name));
  let agentsDone = 0;
  for (const agent of allAgents) {
    if (deriveAgentStatus(agent, events) === "completed") agentsDone++;
  }
  let toolCalls = 0, llmCalls = 0;
  let firstTs: number | null = null, lastTs: number | null = null;
  for (const e of events) {
    const ts = new Date(e.ts).getTime();
    if (firstTs === null || ts < firstTs) firstTs = ts;
    if (lastTs === null || ts > lastTs) lastTs = ts;
    if (e.type === "tool_call") toolCalls++;
    else if (e.type === "analyst_thinking") llmCalls++;
  }
  const elapsedSec = firstTs != null && lastTs != null ? Math.round((lastTs - firstTs) / 1000) : 0;
  return { agentsDone, agentsTotal: allAgents.length, llmCalls, toolCalls, elapsedSec, hasRun: firstTs != null };
}

function formatElapsed(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/* ─── helpers ──────────────────────────────────────────── */

function lastStartedIsoFor(stage: string, events: WsEvent[]): string | undefined {
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (e.type === "analyst_started" && NODE_TO_STAGE[(e.data as any)?.node] === stage) {
      return (e.data as any)?.ts ?? undefined;
    }
  }
  return undefined;
}

function stageElapsedSeconds(startedAtIso: string | undefined, status: string): number {
  if (status !== "running" || !startedAtIso) return 0;
  return Math.max(0, Math.floor((Date.now() - new Date(startedAtIso).getTime()) / 1000));
}

/* ─── sub-components ───────────────────────────────────── */

function StageDot({
  stage,
  stageDerived,
  startedAtIso,
  onClick,
  isExpanded,
  compact,
}: {
  stage: { key: string; label: string; icon: string };
  stageDerived: StageDerived;
  startedAtIso?: string;
  onClick: () => void;
  isExpanded: boolean;
  compact: boolean;
}) {
  const { status } = stageDerived;
  const ac = AGENT_COLORS[stage.key] ?? AGENT_COLORS.market;
  const isRunning = status === "running";

  // Live elapsed timer (1 Hz tick)
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!isRunning || !startedAtIso) { setElapsed(0); return; }
    const tick = () => setElapsed(stageElapsedSeconds(startedAtIso, status));
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [isRunning, startedAtIso, status]);

  const pillShape = isRunning && !compact ? "min-w-[3.25rem] h-9 px-3 rounded-full" : "w-7 h-7 rounded-full";

  const dynamicStyle: React.CSSProperties = {
    borderColor: isRunning || status === "done" ? ac.base : "rgba(71,85,105,0.5)",
    backgroundColor:
      status === "done" ? ac.dim
      : status === "running" ? ac.dim
      : isExpanded ? "rgba(30,41,59,0.8)"
      : "transparent",
    color: status === "idle" ? "#64748b" : ac.base,
    boxShadow: isRunning ? `0 0 12px ${ac.ring}` : status === "done" ? `0 0 6px ${ac.ring}` : "none",
  };

  return (
    <button
      type="button"
      data-testid={`stage-${stage.key}`}
      data-status={status}
      data-expanded={isExpanded}
      onClick={onClick}
      aria-expanded={isExpanded}
      aria-label={`${stage.label}: ${STATUS_LABEL[status]}`}
      title={stageDerived.duration_ms != null ? formatDuration(stageDerived.duration_ms) : undefined}
      className={`flex items-center justify-center transition-all duration-200 hover:scale-110 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-market-DEFAULT shrink-0 ${pillShape}`}
      style={dynamicStyle}
    >
      {isRunning && !compact ? (
        <>
          <svg className="animate-spin h-3 w-3 shrink-0" viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" fill="none" />
            <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" fill="none" strokeLinecap="round" />
          </svg>
          <span className="ml-1 text-[10px] font-mono font-semibold">{formatElapsedSec(elapsed)}</span>
        </>
      ) : (
        <span className={`font-bold leading-none ${compact ? "text-[8px]" : "text-[10px]"}`}>
          {status === "done" ? "✓" : stage.icon}
        </span>
      )}
    </button>
  );
}

function formatElapsedSec(s: number): string {
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}m ${r}s`;
}

function AgentRow({
  name,
  status,
  teamColor,
  onClick,
  thinkingPreview,
}: {
  name: string;
  status: AgentStatus;
  teamColor: string;
  onClick?: () => void;
  thinkingPreview?: string;
}) {
  const dot =
    status === "completed" ? (
      <svg className="w-2.5 h-2.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke={teamColor} strokeWidth={3} strokeLinecap="round" strokeLinejoin="round">
        <path d="m4.5 12.75 6 6 9-13.5" />
      </svg>
    ) : status === "in_progress" ? (
      <span className="block w-2 h-2 rounded-full shrink-0 animate-pulse" style={{ backgroundColor: teamColor, boxShadow: `0 0 6px ${teamColor}60` }} />
    ) : (
      <span className="block w-2 h-2 rounded-full shrink-0 bg-slate-700" />
    );

  const [showTooltip, setShowTooltip] = useState(false);
  const hasHoverContent = status === "in_progress" && thinkingPreview;

  return (
    <div
      data-testid={`agent-row-${name}`}
      className={`relative flex items-center gap-1.5 min-w-0 ${onClick ? "cursor-pointer hover:bg-slate-700/30 rounded px-1 -mx-1 transition-colors" : ""}`}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick(); } } : undefined}
      onMouseEnter={hasHoverContent ? () => setShowTooltip(true) : undefined}
      onMouseLeave={hasHoverContent ? () => setShowTooltip(false) : undefined}
    >
      {dot}
      <span className={`text-[11px] truncate transition-colors duration-300 ${
        status === "completed" ? "text-slate-300"
        : status === "in_progress" ? "text-slate-400"
        : "text-slate-600"
      }`}>
        {name}
      </span>
      {hasHoverContent && showTooltip && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 z-50 pointer-events-none">
          <div className="bg-slate-800 text-slate-200 text-[10px] leading-relaxed rounded-lg px-3 py-2 shadow-xl border border-slate-700/60 whitespace-nowrap max-w-[240px] truncate">
            {thinkingPreview}
          </div>
          <div className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-slate-800" />
        </div>
      )}
    </div>
  );
}

function TeamCard({
  team,
  status,
  agentStatuses,
  onAgentClick,
  agentThinkingPreview,
}: {
  team: TeamDef;
  status: TeamStatus;
  agentStatuses: AgentStatus[];
  onAgentClick: (agentName: string) => void;
  agentThinkingPreview: Map<string, string>;
}) {
  const doneCount = agentStatuses.filter((s) => s === "completed").length;
  const total = agentStatuses.length;
  const fraction = total > 0 ? doneCount / total : 0;

  return (
    <div
      className="rounded-xl border min-w-0 flex-1 transition-all duration-300"
      style={{
        borderColor: status === "done" ? `${team.color}50` : status === "active" ? `${team.color}30` : "rgba(51,65,85,0.5)",
        backgroundColor: status === "done" || status === "active" ? team.bgDim : "rgba(15,23,42,0.4)",
      }}
    >
      <div
        className="flex items-center justify-between px-2.5 py-1.5 rounded-t-xl border-b"
        style={{ borderBottomColor: status === "done" ? `${team.color}30` : "rgba(51,65,85,0.3)" }}
      >
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="text-sm leading-none" style={{ filter: status === "idle" ? "grayscale(1) opacity(0.4)" : "none" }}>
            {team.icon}
          </span>
          <span
            className="text-[11px] font-semibold truncate tracking-tight"
            style={{ color: status === "done" ? team.color : status === "active" ? `${team.color}cc` : "#475569" }}
          >
            {team.label}
          </span>
        </div>
        <span className="text-[10px] font-mono font-semibold tabular-nums shrink-0 ml-1" style={{ color: doneCount > 0 ? team.color : "#475569" }}>
          {doneCount}/{total}
        </span>
      </div>
      <div className="px-2.5 py-1.5 space-y-1">
        {team.agents.map((agent) => (
          <AgentRow
            key={agent.name}
            name={agent.name}
            status={agentStatuses[team.agents.indexOf(agent)] ?? "pending"}
            teamColor={team.color}
            onClick={() => onAgentClick(agent.name)}
            thinkingPreview={agentThinkingPreview.get(agent.name)}
          />
        ))}
      </div>
      <div className="h-0.5 rounded-b-xl overflow-hidden bg-slate-700/50">
        <div
          className="h-full rounded-b-xl transition-all duration-500 ease-out"
          style={{
            width: `${fraction * 100}%`,
            backgroundColor: team.color,
            boxShadow: fraction > 0 ? `0 0 6px ${team.color}60` : "none",
          }}
        />
      </div>
    </div>
  );
}

/* ─── accordion detail panel ───────────────────────────── */

function StageDetailPanel({
  stageKey,
  stageDerived,
  onClose,
}: {
  stageKey: string;
  stageDerived: StageDerived;
  onClose: () => void;
}) {
  const stageConfig = STAGES.find((s) => s.key === stageKey)!;
  const ac = AGENT_COLORS[stageKey] ?? AGENT_COLORS.market;
  const isRunning = stageDerived.status === "running";
  const isDone = stageDerived.status === "done";

  return (
    <div
      data-testid={`stage-${stageKey}-details`}
      className="mt-3 rounded-xl border border-slate-700/50 bg-slate-900/60 backdrop-blur-sm p-4 text-sm animate-fade-in"
      style={{ borderLeftColor: ac.base, borderLeftWidth: 2 }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center justify-center w-6 h-6 rounded-md text-xs font-bold" style={{ backgroundColor: ac.dim, color: ac.base }}>
            {stageConfig.icon}
          </span>
          <div>
            <div className="font-semibold text-slate-200">{stageConfig.label}</div>
            <div className="text-[10px] text-slate-500 font-medium capitalize">{stageDerived.status}</div>
          </div>
          {stageDerived.node && (
            <span className="ml-2 text-[10px] font-mono text-slate-500 bg-slate-800/60 px-2 py-0.5 rounded">
              {stageDerived.node}
            </span>
          )}
        </div>
        <button onClick={onClose} className="text-xs text-slate-500 hover:text-slate-300 transition-colors">Close</button>
      </div>

      {isRunning ? (
        stageDerived.thinkingLog.length > 0 ? (
          <pre className="text-xs leading-relaxed text-slate-300 bg-slate-950/60 rounded-lg p-3 max-h-64 overflow-y-auto whitespace-pre-wrap font-mono border border-slate-800/50">
            {stageDerived.thinkingLog.join("\n")}
            <span className="inline-block w-1.5 h-3 ml-0.5 align-middle rounded-sm" style={{ backgroundColor: ac.base }} />
          </pre>
        ) : (
          <div className="flex items-center gap-2 text-xs text-slate-500 italic">
            <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ backgroundColor: ac.base }} />
            {stageDerived.node ?? stageConfig.label} is thinking…
          </div>
        )
      ) : isDone ? (
        <div className="space-y-2">
          {stageDerived.excerpt && <div className="text-xs text-slate-400 leading-relaxed">{stageDerived.excerpt}</div>}
          {stageDerived.fullText && (
            <pre className="text-xs leading-relaxed text-slate-300 bg-slate-950/60 rounded-lg p-3 max-h-64 overflow-y-auto whitespace-pre-wrap font-mono border border-slate-800/50">
              {stageDerived.fullText}
            </pre>
          )}
          {!stageDerived.excerpt && !stageDerived.fullText && (
            <div className="text-xs text-slate-600 italic">No report content.</div>
          )}
        </div>
      ) : stageDerived.status === "errored" ? (
        <div className="flex items-center gap-2 text-xs text-red-400">
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
          </svg>
          This stage did not run because the run failed earlier.
        </div>
      ) : (
        <div className="flex items-center gap-2 text-xs text-slate-600 italic">
          <span className="w-1.5 h-1.5 rounded-full bg-slate-700" />
          Waiting for {stageConfig.label} to start…
        </div>
      )}
    </div>
  );
}

/* ─── main component ───────────────────────────────────── */

export function PipelineFlow({ events }: { events: WsEvent[] }) {
  const [expandedStage, setExpandedStage] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [compact, setCompact] = useState(false);

  // Detect narrow container → compact mode
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setCompact(entry.contentRect.width < 600);
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Derive per-stage status
  const stageDerivedMap = useMemo(() => {
    const map = new Map<string, StageDerived>();
    for (const s of STAGES) map.set(s.key, deriveStage(s.key, events));
    return map;
  }, [events]);
  const stageDerivedList = useMemo(
    () => STAGES.map((s) => ({ key: s.key, derived: stageDerivedMap.get(s.key)! })),
    [stageDerivedMap],
  );

  const failed = events.some((e) => e.type === "run_failed");
  const segmentProgress = useMemo(
    () => deriveSegmentProgress(stageDerivedList.map((s) => s.derived), failed),
    [stageDerivedList, failed],
  );

  // Latest thinking text per agent (for hover tooltip)
  const agentThinkingPreview = useMemo(() => {
    const map = new Map<string, string>();
    for (const e of events) {
      if (e.type === "analyst_thinking") {
        const d = e.data as Record<string, unknown>;
        const node = d.node as string | undefined;
        if (node) {
          const preview = (d.text_preview as string) ?? (d.text_fragment as string) ?? "";
          if (preview) map.set(node, preview.slice(0, 120));
        }
      }
    }
    return map;
  }, [events]);

  // Derive team-level status
  const derived = useMemo(() => {
    const teamStatuses = TEAMS.map((t) => ({
      team: t,
      status: deriveTeamStatus(t, events),
      agentStatuses: t.agents.map((a) => deriveAgentStatus(a.name, events)),
    }));
    const stats = computeStats(events);
    return { teamStatuses, stats };
  }, [events]);

  const { teamStatuses, stats } = derived;
  const doneCount = teamStatuses.filter((ts) => ts.status === "done").length;

  const toggleStage = (key: string) => setExpandedStage((prev) => (prev === key ? null : key));

  // Click an agent row → open its stage detail panel
  const handleAgentClick = (agentName: string) => {
    const stage = AGENT_TO_STAGE[agentName];
    if (stage) toggleStage(stage);
  };

  const TEAM_GROUPS = [
    { label: "Analyst Team", indices: [0, 1, 2, 3], color: "#38bdf8" },
    { label: "Research", indices: [4], color: "#fb923c" },
    { label: "Trader", indices: [5], color: "#fbbf24" },
    { label: "Risk Mgmt", indices: [6], color: "#ef4444" },
  ] as const;

  // Map team connector index → stage segment index
  const TEAM_SEGMENT_MAP = [3, 4, 5, 5];

  return (
    <div ref={containerRef} className="glass-panel px-3 py-2.5" data-testid="pipeline-flow">
      {!compact && (
        <div className="flex items-start mb-2 px-1">
          {TEAM_GROUPS.map((group) => {
            const groupStages = group.indices.map((i) => stageDerivedList[i].derived.status);
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
                  style={{ color: allDone ? group.color : anyActive ? `${group.color}99` : "#334155" }}
                >
                  {group.label}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Timeline dots row with colored segments */}
      <div className={`flex items-start ${compact ? "mb-2" : "mb-3"}`}>
        {stageDerivedList.map(({ key, derived }, i) => {
          const isExpanded = expandedStage === key;
          return (
            <div key={key} className="flex items-start flex-1 last:flex-none">
              <div className="flex flex-col items-center">
                <StageDot
                  stage={STAGES[i]}
                  stageDerived={derived}
                  startedAtIso={lastStartedIsoFor(key, events)}
                  onClick={() => toggleStage(key)}
                  isExpanded={isExpanded}
                  compact={compact}
                />
                {!compact && (
                  <div className="mt-1 text-[10px] text-slate-500 text-center font-mono truncate max-w-[60px]">
                    {derived.duration_ms != null ? formatDuration(derived.duration_ms) : STATUS_LABEL[derived.status]}
                  </div>
                )}
              </div>
              {i < stageDerivedList.length - 1 && (
                <div
                  data-testid="timeline-segment"
                  data-progress={segmentProgress[i]}
                  aria-hidden="true"
                  className={`flex-1 h-0.5 ${compact ? "mx-0.5 mt-[10px]" : "mx-1 mt-[10px]"} rounded-full transition-colors duration-500 ${SEGMENT_CLASS[segmentProgress[i]]}`}
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Team cards row with colored segment connectors */}
      <div className="flex items-stretch gap-0">
        {teamStatuses.map(({ team, status, agentStatuses }, i) => (
          <div key={team.id} className="flex items-stretch flex-1 min-w-0">
            <TeamCard
              team={team}
              status={status}
              agentStatuses={agentStatuses}
              onAgentClick={handleAgentClick}
              agentThinkingPreview={agentThinkingPreview}
            />
            {i < teamStatuses.length - 1 && (
              <div className="flex items-center shrink-0 px-1">
                <div
                  aria-hidden="true"
                  className={`w-2 h-0.5 rounded-full transition-colors duration-500 ${
                    SEGMENT_CLASS[segmentProgress[TEAM_SEGMENT_MAP[i] as keyof typeof SEGMENT_CLASS] ?? "future"]
                  }`}
                />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Accordion detail panel */}
      {expandedStage && stageDerivedMap.has(expandedStage) && (
        <StageDetailPanel
          stageKey={expandedStage}
          stageDerived={stageDerivedMap.get(expandedStage)!}
          onClose={() => setExpandedStage(null)}
        />
      )}

      {/* Stats bar */}
      {stats.hasRun && (
        <div className="flex items-center gap-3 mt-2.5 pt-2 border-t border-slate-700/30 text-[10px] font-mono text-slate-500">
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: stats.agentsDone === stats.agentsTotal ? "#34d399" : "#38bdf8" }} />
            <span className="font-semibold tabular-nums" style={{ color: stats.agentsDone === stats.agentsTotal ? "#34d399" : "#94a3b8" }}>
              {stats.agentsDone}
            </span>
            <span className="text-slate-600">/</span>
            <span className="text-slate-400">{stats.agentsTotal}</span>
            <span className="text-slate-600">agents</span>
          </span>
          <span className="w-px h-3 bg-slate-700/40" />
          <span className="text-slate-600">LLM</span>
          <span className="text-sky-400/80 tabular-nums">{stats.llmCalls}</span>
          <span className="w-px h-3 bg-slate-700/40" />
          <span className="text-slate-600">tools</span>
          <span className="text-amber-400/80 tabular-nums">{stats.toolCalls}</span>
          <span className="w-px h-3 bg-slate-700/40" />
          <span className="text-slate-600">elapsed</span>
          <span className="text-slate-300 tabular-nums">{formatElapsed(stats.elapsedSec)}</span>
        </div>
      )}
    </div>
  );
}
