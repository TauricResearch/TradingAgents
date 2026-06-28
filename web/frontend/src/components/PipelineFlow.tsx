import { useState, useMemo } from "react";
import { AlertCircle, BarChart3, FlaskConical, Briefcase, Shield, ClipboardList, TrendingUp } from "lucide-react";
import type { WsEvent } from "../lib/events";
import { TeamCard, deriveAgentStatus, deriveTeamStatus, computeTeamTiming, type TeamDef } from "./TeamCard";
import { PipelineStats } from "./PipelineStats";

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

const STAGES: { key: string; label: string; icon: JSX.Element }[] = [
  { key: "market", label: "Market", icon: <BarChart3 className="w-3.5 h-3.5" /> },
  { key: "sentiment", label: "Sentiment", icon: <BarChart3 className="w-3.5 h-3.5" /> },
  { key: "news", label: "News", icon: <BarChart3 className="w-3.5 h-3.5" /> },
  { key: "fundamentals", label: "Fundamentals", icon: <BarChart3 className="w-3.5 h-3.5" /> },
  { key: "research", label: "Research", icon: <FlaskConical className="w-3.5 h-3.5" /> },
  { key: "trader", label: "Trader", icon: <TrendingUp className="w-3.5 h-3.5" /> },
  { key: "risk", label: "Risk", icon: <Shield className="w-3.5 h-3.5" /> },
];

const TEAMS: TeamDef[] = [
  {
    id: "analysts",
    label: "Analyst Team",
    icon: <BarChart3 className="w-3.5 h-3.5" />,
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
    icon: <FlaskConical className="w-3.5 h-3.5" />,
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
    icon: <Briefcase className="w-3.5 h-3.5" />,
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
    icon: <Shield className="w-3.5 h-3.5" />,
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
    icon: <ClipboardList className="w-3.5 h-3.5" />,
    agents: [
      { name: "Portfolio Manager" },
    ],
    color: "#a78bfa",
    bgDim: "rgba(167,139,250,0.08)",
    stageKeys: ["risk"],
  },
];

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
    (e) => e.type === "analyst_started" && AGENT_TO_STAGE[(e.data as Record<string, unknown>)?.node] === stage,
  );
  const lastStartIdx = (() => {
    for (let i = events.length - 1; i >= 0; i--) {
      const e = events[i];
      if (e.type === "analyst_started" && AGENT_TO_STAGE[(e.data as Record<string, unknown>)?.node] === stage) return i;
    }
    return -1;
  })();

  const hasReport = events.some((e) => {
    if (e.type !== "analyst_completed") return false;
    if ((e.data as Record<string, unknown>)?.stage !== stage) return false;
    const d = e.data as Record<string, unknown>;
    return !!(d.report_excerpt || d.report_text);
  });
  const lastReportEvent = (() => {
    for (let i = events.length - 1; i >= 0; i--) {
      const e = events[i];
      if (e.type !== "analyst_completed") continue;
      if ((e.data as Record<string, unknown>)?.stage !== stage) continue;
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
        const nodeStage = AGENT_TO_STAGE[(e.data as Record<string, unknown>)?.node];
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
      node: lastStartIdx !== -1 ? (events[lastStartIdx].data as Record<string, unknown>)?.node ?? undefined : undefined,
      thinkingLog,
    };
  }

  return {
    status: "running",
    node: lastStartIdx !== -1 ? (events[lastStartIdx].data as Record<string, unknown>)?.node ?? undefined : undefined,
    thinkingLog,
  };
}

const AGENT_COLORS: Record<string, { base: string; dim: string; ring: string }> = {
  market:       { base: "#38bdf8", dim: "rgba(56,189,248,0.15)",  ring: "rgba(56,189,248,0.3)" },
  sentiment:    { base: "#a78bfa", dim: "rgba(167,139,250,0.15)", ring: "rgba(167,139,250,0.3)" },
  news:         { base: "#34d399", dim: "rgba(52,211,153,0.15)",  ring: "rgba(52,211,153,0.3)" },
  fundamentals: { base: "#f472b6", dim: "rgba(244,114,182,0.15)", ring: "rgba(244,114,182,0.3)" },
  research:     { base: "#fb923c", dim: "rgba(251,146,60,0.15)",  ring: "rgba(251,146,60,0.3)" },
  risk:         { base: "#ef4444", dim: "rgba(239,68,68,0.15)",   ring: "rgba(239,68,68,0.3)" },
  trader:       { base: "#fbbf24", dim: "rgba(251,191,36,0.15)",  ring: "rgba(251,191,36,0.3)" },
};

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
          <span className="inline-flex items-center justify-center w-6 h-6 rounded-md" style={{ backgroundColor: ac.dim, color: ac.base }}>
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
            <span className="inline-block w-1.5 h-3 ml-0.5 align-middle rounded-sm animate-pulse" style={{ backgroundColor: ac.base }} />
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
            <div className="text-xs text-slate-400 italic">No report content.</div>
          )}
        </div>
      ) : stageDerived.status === "errored" ? (
        <div className="flex items-center gap-2 text-xs text-red-400">
          <AlertCircle className="w-3.5 h-3.5" />
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

export function PipelineFlow({ events }: { events: WsEvent[] }) {
  const [expandedStage, setExpandedStage] = useState<string | null>(null);

  const stageDerivedMap = useMemo(() => {
    const map = new Map<string, StageDerived>();
    for (const s of STAGES) map.set(s.key, deriveStage(s.key, events));
    return map;
  }, [events]);

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

  const derived = useMemo(() => {
    const teamStatuses = TEAMS.map((t) => ({
      team: t,
      status: deriveTeamStatus(t, events),
      agentStatuses: t.agents.map((a) => deriveAgentStatus(a.name, events)),
      timing: computeTeamTiming(t, events),
    }));
    const stats = computeStats(events);
    return { teamStatuses, stats };
  }, [events]);

  const { teamStatuses, stats } = derived;

  const toggleStage = (key: string) => setExpandedStage((prev) => (prev === key ? null : key));

  const handleAgentClick = (agentName: string) => {
    const stage = AGENT_TO_STAGE[agentName];
    if (stage) toggleStage(stage);
  };

  return (
    <div className="glass-panel px-3 py-2.5" data-testid="pipeline-flow">
      <div className="flex items-stretch gap-0 overflow-x-auto scrollable-mobile -mx-3 px-3 md:mx-0 md:px-0 md:overflow-visible">
        {teamStatuses.map(({ team, status, agentStatuses, timing }, i) => (
          <div key={team.id} className="flex items-stretch flex-1 min-w-[170px] md:min-w-0">
            <TeamCard
              team={team}
              status={status}
              agentStatuses={agentStatuses}
              timing={timing}
              onAgentClick={handleAgentClick}
              agentThinkingPreview={agentThinkingPreview}
            />
            {i < teamStatuses.length - 1 && (
              <div className="flex items-center shrink-0 px-1">
                <div aria-hidden="true" className="w-1.5 h-1.5 rounded-full bg-slate-600" />
              </div>
            )}
          </div>
        ))}
      </div>

      {expandedStage && stageDerivedMap.has(expandedStage) && (
        <StageDetailPanel
          stageKey={expandedStage}
          stageDerived={stageDerivedMap.get(expandedStage)!}
          onClose={() => setExpandedStage(null)}
        />
      )}

      {stats.hasRun && <PipelineStats stats={stats} />}
    </div>
  );
}
