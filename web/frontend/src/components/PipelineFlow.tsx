import { useMemo } from "react";
import type { WsEvent } from "../lib/events";

interface TeamDef {
  id: string;
  label: string;
  agents: string[];
  color: string;
}

const TEAMS: TeamDef[] = [
  { id: "analysts", label: "Analysts", agents: ["Market Analyst", "Sentiment Analyst", "News Analyst", "Fundamentals Analyst"], color: "#38bdf8" },
  { id: "research", label: "Research", agents: ["Bull Researcher", "Bear Researcher", "Research Manager"], color: "#fb923c" },
  { id: "trader", label: "Trader", agents: ["Trader"], color: "#fbbf24" },
  { id: "risk", label: "Risk Mgmt", agents: ["Aggressive Analyst", "Conservative Analyst", "Neutral Analyst"], color: "#ef4444" },
  { id: "portfolio", label: "Portfolio", agents: ["Portfolio Manager"], color: "#a78bfa" },
];

function deriveTeamStatus(team: TeamDef, events: WsEvent[]): "idle" | "active" | "done" {
  const started = events.some((e) =>
    e.type === "analyst_started" &&
    team.agents.some((a) => (e.data as any)?.node === a)
  );
  if (!started) return "idle";

  const allDone = team.agents.every((agent) =>
    events.some((e) => {
      if (e.type !== "analyst_completed") return false;
      const node = (e.data as any)?.node;
      if (!node) return false;
      // The completed node name may differ slightly (e.g. "Research Manager" vs node name).
      // Use partial match: check if the completed node's stage belongs to this team
      // or if the node name directly matches an agent.
      if (node === agent) return true;
      // For agents without exact node match, check stage
      const stage = (e.data as any)?.stage;
      if (stage) {
        const stageTeam: Record<string, string[]> = {
          analysts: ["market", "sentiment", "news", "fundamentals"],
          research: ["research"],
          trader: ["trader"],
          risk: ["risk"],
          portfolio: ["portfolio"],
        };
        const teamStages = stageTeam[team.id] ?? [];
        if (teamStages.includes(stage)) return true;
      }
      return false;
    })
  );

  if (allDone) return "done";
  return "active";
}

export function PipelineFlow({ events }: { events: WsEvent[] }) {
  const teamStatuses = useMemo(
    () => TEAMS.map((t) => ({ team: t, status: deriveTeamStatus(t, events) })),
    [events],
  );

  const doneIdx = teamStatuses.filter((ts) => ts.status === "done").length;

  return (
    <div className="glass-panel px-4 py-2.5">
      <div className="flex items-center gap-0">
        {teamStatuses.map(({ team, status }, i) => {
          const isActive = status === "active";
          const isDone = status === "done";
          const isLast = i === teamStatuses.length - 1;

          return (
            <div key={team.id} className="flex items-center flex-1 min-w-0">
              {/* Team node */}
              <div className="flex items-center gap-2 min-w-0">
                <div
                  className={`shrink-0 w-2 h-2 rounded-full transition-all duration-500 ${
                    isDone
                      ? "shadow-[0_0_6px_var(--team-glow)]"
                      : isActive
                      ? "animate-pulse"
                      : ""
                  }`}
                  style={{
                    backgroundColor: isDone || isActive ? team.color : "#334155",
                    boxShadow: isDone ? `0 0 8px ${team.color}40` : isActive ? `0 0 8px ${team.color}30` : "none",
                    ['--team-glow' as string]: team.color,
                  }}
                />
                <span
                  className={`text-[11px] font-semibold truncate transition-colors duration-300 ${
                    isDone
                      ? "text-slate-200"
                      : isActive
                      ? "text-slate-300"
                      : "text-slate-600"
                  }`}
                >
                  {team.label}
                </span>
                {isDone && (
                  <svg className="w-3 h-3 shrink-0 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                  </svg>
                )}
                {isActive && (
                  <span className="shrink-0 w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse shadow-[0_0_6px_rgba(56,189,248,0.5)]" />
                )}
              </div>

              {/* Connector segment */}
              {!isLast && (
                <div className="flex-1 mx-2">
                  <div
                    className={`h-[2px] rounded-full transition-all duration-500 ${
                      i < doneIdx
                        ? "bg-emerald-500/60"
                        : i === doneIdx && teamStatuses[i + 1]?.status !== "idle"
                        ? "bg-sky-500/40"
                        : "bg-slate-700/50"
                    }`}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
