import { useState } from "react";
import { ChevronDown, ChevronUp, BarChart3, MessageSquare, Newspaper, TrendingUp, FlaskConical, Briefcase, Shield } from "lucide-react";
import type { WsEvent } from "../lib/events";

interface TraceNode {
  stage: string;
  label: string;
  Icon: React.ComponentType<{ className?: string }>;
  agent: string;
  summary: string;
  fullText: string | null;
}

const STAGE_CONFIG: Record<string, { label: string; Icon: React.ComponentType<{ className?: string }> }> = {
  market: { label: "Market Analysis", Icon: BarChart3 },
  sentiment: { label: "Sentiment Analysis", Icon: MessageSquare },
  news: { label: "News Analysis", Icon: Newspaper },
  fundamentals: { label: "Fundamentals", Icon: TrendingUp },
  research: { label: "Research & Debate", Icon: FlaskConical },
  trader: { label: "Trader Proposal", Icon: Briefcase },
  risk: { label: "Risk Discussion", Icon: Shield },
};

export function DecisionTrace({ events }: { events: WsEvent[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  const completedEvents = events.filter(e => e.type === "analyst_completed");
  const decisionEvent = events.find(e => e.type === "decision");

  const nodes: TraceNode[] = [];
  for (const e of completedEvents) {
    const d = e.data as any;
    const stage = d.stage as string;
    const config = STAGE_CONFIG[stage];
    if (!config) continue;
    nodes.push({
      stage,
      label: config.label,
      Icon: config.Icon,
      agent: d.node || stage,
      summary: (d.report_excerpt || d.report_text || "").slice(0, 120),
      fullText: d.report_text || null,
    });
  }

  if (nodes.length === 0 && !decisionEvent) {
    return <div className="text-xs text-slate-600 italic py-4 text-center">No decision data yet.</div>;
  }

  return (
    <div className="space-y-0" data-testid="decision-trace">
      {nodes.map((n, i) => (
        <div key={`${n.stage}-${n.agent}`}>
          <button
            onClick={() => {
              const key = `${n.stage}-${n.agent}`;
              setExpanded(expanded === key ? null : key);
            }}
            className="w-full flex items-center gap-2 px-3 py-2 text-xs text-left hover:bg-slate-800/30 transition-colors border-l-2 border-slate-700 hover:border-sky-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/50 focus-visible:ring-inset">
            <n.Icon className="w-3.5 h-3.5 shrink-0 text-sky-400" />
            <div className="min-w-0 flex-1">
              <div className="text-slate-300 font-medium truncate">{n.agent}</div>
              <div className="text-slate-500 text-[10px] truncate">{n.summary}</div>
            </div>
            {expanded === `${n.stage}-${n.agent}` ? <ChevronUp className="w-3 h-3 text-slate-600" /> : <ChevronDown className="w-3 h-3 text-slate-600" />}
          </button>
          {expanded === `${n.stage}-${n.agent}` && n.fullText && (
            <pre className="ml-6 mr-2 mb-2 p-3 bg-slate-950/60 rounded-lg text-xs text-slate-300 whitespace-pre-wrap font-mono border border-slate-800/50 max-h-64 overflow-y-auto">
              {n.fullText}
            </pre>
          )}
          {i < nodes.length - 1 && <div className="ml-3 w-px h-4 bg-slate-700/50 mx-auto" />}
        </div>
      ))}
      {decisionEvent && (
        <div className="mt-3 p-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10">
          <div className="text-xs font-bold text-emerald-400">DECISION</div>
          <div className="text-sm font-bold text-emerald-300 mt-1">
            {(decisionEvent.data as any)?.action || "HOLD"}
            {(decisionEvent.data as any)?.target ? ` @ $${(decisionEvent.data as any).target}` : ""}
          </div>
          <div className="text-xs text-slate-400 mt-1">
            Confidence: {((decisionEvent.data as any)?.confidence || 0) * 100}%
          </div>
        </div>
      )}
    </div>
  );
}
