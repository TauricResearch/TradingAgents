import { useEffect, useState, type ReactNode } from "react";
import { Check } from "lucide-react";
import type { WsEvent } from "../lib/events";
import { formatDuration } from "../lib/format";

export interface TeamDef {
  id: string;
  label: string;
  icon: ReactNode;
  agents: { name: string }[];
  color: string;
  bgDim: string;
  stageKeys: string[];
}

type AgentStatus = "pending" | "in_progress" | "completed";
type TeamStatus = "idle" | "active" | "done";

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

export function deriveAgentStatus(agent: string, events: WsEvent[]): AgentStatus {
  const stage = NODE_TO_STAGE[agent];
  if (!stage) return "pending";
  const started = events.some(
    (e) => e.type === "analyst_started" && (e.data as Record<string, unknown>)?.node === agent,
  );
  if (!started) return "pending";
  const stageCompletions = events.filter(
    (e) => e.type === "analyst_completed" && (e.data as Record<string, unknown>)?.stage === stage,
  ).length;
  const order = AGENT_ORDER_IN_STAGE[agent] ?? 0;
  return stageCompletions > order ? "completed" : "in_progress";
}

export function deriveTeamStatus(team: TeamDef, events: WsEvent[]): TeamStatus {
  const agentStatuses = team.agents.map((a) => deriveAgentStatus(a.name, events));
  const allPending = agentStatuses.every((s) => s === "pending");
  const allDone = agentStatuses.every((s) => s === "completed");
  if (allDone) return "done";
  if (allPending) return "idle";
  return "active";
}

export interface TeamTiming {
  startIso: string | undefined;
  duration_ms: number | undefined;
}

export function computeTeamTiming(team: TeamDef, events: WsEvent[]): TeamTiming {
  const agentNames = team.agents.map((a) => a.name);
  const stageKeys = team.stageKeys;
  let startIso: string | undefined;
  let endIso: string | undefined;
  for (const e of events) {
    if (e.type === "analyst_started") {
      const node = (e.data as Record<string, unknown>)?.node as string | undefined;
      if (node && agentNames.includes(node)) {
        if (!startIso || e.ts < startIso) startIso = e.ts;
      }
    }
    if (e.type === "analyst_completed") {
      const stage = (e.data as Record<string, unknown>)?.stage as string | undefined;
      if (stage && stageKeys.includes(stage)) {
        if (!endIso || e.ts > endIso) endIso = e.ts;
      }
    }
  }
  const teamSt = deriveTeamStatus(team, events);
  let duration_ms: number | undefined;
  if (teamSt === "done" && startIso && endIso) {
    duration_ms = new Date(endIso).getTime() - new Date(startIso).getTime();
  }
  return { startIso, duration_ms };
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
      <Check className="w-2.5 h-2.5 shrink-0" style={{ color: teamColor }} strokeWidth={3} />
    ) : status === "in_progress" ? (
      <span className="block w-2 h-2 rounded-full shrink-0 animate-pulse" style={{ backgroundColor: teamColor, boxShadow: `0 0 6px ${teamColor}60` }} />
    ) : (
      <span className="block w-2 h-2 rounded-full shrink-0 bg-slate-700" />
    );

  const [showTooltip, setShowTooltip] = useState(false);
  const hasHoverContent = status === "in_progress" && thinkingPreview;

  return (
    <div
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

export function TeamCard({
  team,
  status,
  agentStatuses,
  timing,
  onAgentClick,
  agentThinkingPreview,
}: {
  team: TeamDef;
  status: TeamStatus;
  agentStatuses: AgentStatus[];
  timing: TeamTiming;
  onAgentClick: (agentName: string) => void;
  agentThinkingPreview: Map<string, string>;
}) {
  const doneCount = agentStatuses.filter((s) => s === "completed").length;
  const total = agentStatuses.length;
  const fraction = total > 0 ? doneCount / total : 0;

  const [elapsedSec, setElapsedSec] = useState(0);
  useEffect(() => {
    if (status !== "active" || !timing.startIso) {
      setElapsedSec(0);
      return;
    }
    const tick = () => {
      const startMs = new Date(timing.startIso!).getTime();
      if (isNaN(startMs)) { setElapsedSec(0); return; }
      setElapsedSec(Math.max(0, Math.floor((Date.now() - startMs) / 1000)));
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [status, timing.startIso]);

  const fmtElapsed = (s: number) => {
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${m}m ${r}s`;
  };

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
          <span className="text-sm leading-none" style={{ filter: status === "idle" ? "grayscale(1) opacity(0.4)" : "none", color: team.color }}>
            {team.icon}
          </span>
          <span
            className="text-[11px] font-semibold truncate tracking-tight"
            style={{ color: status === "done" ? team.color : status === "active" ? `${team.color}cc` : "#64748b" }}
          >
            {team.label}
          </span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {status === "active" && timing.startIso && (
            <span className="text-[10px] font-mono tabular-nums text-sky-400/80">
              {fmtElapsed(elapsedSec)}
            </span>
          )}
          {status === "done" && timing.duration_ms != null && (
            <span className="text-[10px] font-mono tabular-nums flex items-center gap-0.5" style={{ color: team.color }}>
              <Check className="w-2.5 h-2.5" />
              {formatDuration(timing.duration_ms)}
            </span>
          )}
          <span className="text-[10px] font-mono font-semibold tabular-nums" style={{ color: doneCount > 0 ? team.color : "#475569" }}>
            {doneCount}/{total}
          </span>
        </div>
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
