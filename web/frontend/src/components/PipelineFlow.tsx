import { useMemo } from "react";
import type { WsEvent } from "../lib/events";

/* ─── agent-to-stage mapping (mirrors runner._STAGE_MAP + RunTimeline) ─── */

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

/**
 * Per-agent position within the "shared" stage lanes.
 * Research agents share "research": 3 emit in order (Bull, Bear, Manager).
 * Risk agents + Portfolio Manager share "risk":  4 emit in order (Aggressive,
 * Conservative, Neutral, Portfolio Manager).
 * Agents with unique stages (market, sentiment, news, fundamentals, trader)
 * need just 1 completion.
 */
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
  },
];

/* ─── per-agent status derivation ──────────────────────── */

type AgentStatus = "pending" | "in_progress" | "completed";

function deriveAgentStatus(agent: string, events: WsEvent[]): AgentStatus {
  const stage = AGENT_TO_STAGE[agent];
  if (!stage) return "pending";

  // Has this agent started?
  const started = events.some(
    (e) => e.type === "analyst_started" && (e.data as any)?.node === agent,
  );
  if (!started) return "pending";

  // How many completions have been emitted for this agent's stage lane?
  const stageCompletions = events.filter(
    (e) =>
      e.type === "analyst_completed" &&
      (e.data as any)?.stage === stage,
  ).length;

  const order = AGENT_ORDER_IN_STAGE[agent] ?? 0;
  return stageCompletions > order ? "completed" : "in_progress";
}

/* ─── team-level status ────────────────────────────────── */

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

  let toolCalls = 0;
  let llmCalls = 0;
  let firstTs: number | null = null;
  let lastTs: number | null = null;

  for (const e of events) {
    const ts = new Date(e.ts).getTime();
    if (firstTs === null || ts < firstTs) firstTs = ts;
    if (lastTs === null || ts > lastTs) lastTs = ts;

    if (e.type === "tool_call") toolCalls++;
    else if (e.type === "analyst_thinking") llmCalls++;
  }

  const elapsedSec =
    firstTs != null && lastTs != null
      ? Math.round((lastTs - firstTs) / 1000)
      : 0;

  return {
    agentsDone,
    agentsTotal: allAgents.length,
    llmCalls,
    toolCalls,
    elapsedSec,
    hasRun: firstTs != null,
  };
}

function formatElapsed(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/* ─── sub-components ───────────────────────────────────── */

function AgentRow({
  name,
  status,
  teamColor,
}: {
  name: string;
  status: AgentStatus;
  teamColor: string;
}) {
  const dot =
    status === "completed" ? (
      <svg
        className="w-2.5 h-2.5 shrink-0"
        viewBox="0 0 24 24"
        fill="none"
        stroke={teamColor}
        strokeWidth={3}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="m4.5 12.75 6 6 9-13.5" />
      </svg>
    ) : status === "in_progress" ? (
      <span
        className="block w-2 h-2 rounded-full shrink-0 animate-pulse"
        style={{ backgroundColor: teamColor, boxShadow: `0 0 6px ${teamColor}60` }}
      />
    ) : (
      <span className="block w-2 h-2 rounded-full shrink-0 bg-slate-700" />
    );

  return (
    <div className="flex items-center gap-1.5 min-w-0">
      {dot}
      <span
        className={`text-[11px] truncate transition-colors duration-300 ${
          status === "completed"
            ? "text-slate-300"
            : status === "in_progress"
              ? "text-slate-400"
              : "text-slate-600"
        }`}
      >
        {name}
      </span>
    </div>
  );
}

function TeamCard({
  team,
  status,
  agentStatuses,
}: {
  team: TeamDef;
  status: TeamStatus;
  agentStatuses: AgentStatus[];
}) {
  const doneCount = agentStatuses.filter((s) => s === "completed").length;
  const total = agentStatuses.length;
  const fraction = total > 0 ? doneCount / total : 0;

  return (
    <div
      className="rounded-xl border min-w-0 flex-1 transition-all duration-300"
      style={{
        borderColor:
          status === "done"
            ? `${team.color}50`
            : status === "active"
              ? `${team.color}30`
              : "rgba(51,65,85,0.5)",
        backgroundColor: status === "done" || status === "active" ? team.bgDim : "rgba(15,23,42,0.4)",
      }}
    >
      {/* Team header */}
      <div
        className="flex items-center justify-between px-2.5 py-1.5 rounded-t-xl border-b"
        style={{
          borderBottomColor:
            status === "done"
              ? `${team.color}30`
              : "rgba(51,65,85,0.3)",
        }}
      >
        <div className="flex items-center gap-1.5 min-w-0">
          <span
            className="text-sm leading-none"
            style={{
              filter: status === "idle" ? "grayscale(1) opacity(0.4)" : "none",
            }}
          >
            {team.icon}
          </span>
          <span
            className="text-[11px] font-semibold truncate tracking-tight"
            style={{
              color:
                status === "done"
                  ? team.color
                  : status === "active"
                    ? `${team.color}cc`
                    : "#475569",
            }}
          >
            {team.label}
          </span>
        </div>
        <span
          className="text-[10px] font-mono font-semibold tabular-nums shrink-0 ml-1"
          style={{
            color: doneCount > 0 ? team.color : "#475569",
          }}
        >
          {doneCount}/{total}
        </span>
      </div>

      {/* Agents */}
      <div className="px-2.5 py-1.5 space-y-1">
        {team.agents.map((agent) => (
          <AgentRow
            key={agent.name}
            name={agent.name}
            status={
              agentStatuses[team.agents.indexOf(agent)] ?? "pending"
            }
            teamColor={team.color}
          />
        ))}
      </div>

      {/* Thin progress bar at bottom */}
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

/* ─── main component ───────────────────────────────────── */

export function PipelineFlow({ events }: { events: WsEvent[] }) {
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

  return (
    <div className="glass-panel px-3 py-2.5">
      {/* Team cards row */}
      <div className="flex items-stretch gap-2">
        {teamStatuses.map(({ team, status, agentStatuses }, i) => (
          <div key={team.id} className="flex items-stretch flex-1 min-w-0">
            <TeamCard
              team={team}
              status={status}
              agentStatuses={agentStatuses}
            />
            {/* Connector arrow between teams */}
            {i < teamStatuses.length - 1 && (
              <div className="flex items-center shrink-0 mx-1">
                <svg
                  className="w-4 h-4"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke={
                    i < doneCount
                      ? "rgba(52,211,153,0.5)"
                      : i === doneCount && status !== "idle"
                        ? "rgba(56,189,248,0.3)"
                        : "rgba(51,65,85,0.4)"
                  }
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="m9 18 6-6-6-6" />
                </svg>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Stats bar (mirrors CLI footer) */}
      {stats.hasRun && (
        <div className="flex items-center gap-3 mt-2.5 pt-2 border-t border-slate-700/30 text-[10px] font-mono text-slate-500">
          <span className="flex items-center gap-1">
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{
                backgroundColor:
                  stats.agentsDone === stats.agentsTotal
                    ? "#34d399"
                    : "#38bdf8",
              }}
            />
            <span
              className="font-semibold tabular-nums"
              style={{
                color:
                  stats.agentsDone === stats.agentsTotal
                    ? "#34d399"
                    : "#94a3b8",
              }}
            >
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
