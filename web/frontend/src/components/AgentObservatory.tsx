import { useState } from "react";
import { X } from "lucide-react";
import type { WsEvent } from "../lib/events";
import { ObservatoryDag } from "./ObservatoryDag";
import { ThinkingStream } from "./ThinkingStream";
import { ToolTimeline } from "./ToolTimeline";
import { DebateFlow } from "./DebateFlow";
import { DecisionTrace } from "./DecisionTrace";
import { TickerAgentPanel } from "./TickerAgentPanel";

type Tab = "dag" | "thinking" | "tools" | "debate" | "risk" | "decision" | "ticker";

interface AgentObservatoryProps {
  events: WsEvent[];
}

export function AgentObservatory({ events, onClose }: AgentObservatoryProps & { onClose?: () => void }) {
  const [tab, setTab] = useState<Tab>("dag");
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

  const tabs: { key: Tab; label: string }[] = [
    { key: "dag", label: "Flow" },
    { key: "thinking", label: "Thinking" },
    { key: "tools", label: "Tools" },
    { key: "debate", label: "Debate" },
    { key: "risk", label: "Risk" },
    { key: "decision", label: "Trace" },
    { key: "ticker", label: "Ticker" },
  ];

  return (
    <div className="space-y-3" data-testid="agent-observatory">
      <div className="flex items-center gap-1 border-b border-slate-700/50 pb-1">
        {onClose && (
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-300 transition-colors rounded-md p-0.5 mr-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/50"
            title="Close Observatory"
          >
            <X className="w-4 h-4" />
          </button>
        )}
        {tabs.map(t => (
          <button key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-3 py-1.5 text-xs rounded-t-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/50 ${
              tab === t.key
                ? "bg-sky-500/15 text-sky-300 border-b-2 border-sky-400"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "dag" && (
        <ObservatoryDag events={events} onNodeClick={(name) => { setSelectedAgent(name); setTab("thinking"); }} />
      )}
      {tab === "thinking" && (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-1">
            {["Market Analyst", "Sentiment Analyst", "News Analyst", "Fundamentals Analyst",
              "Bull Researcher", "Bear Researcher", "Research Manager", "Trader",
              "Aggressive Analyst", "Conservative Analyst", "Neutral Analyst", "Portfolio Manager"].map(name => (
              <button key={name} onClick={() => setSelectedAgent(name)}
                className={`px-2 py-1 text-[10px] rounded-full border transition-colors ${
                  selectedAgent === name
                    ? "bg-sky-500/20 text-sky-300 border-sky-500/30"
                    : "text-slate-500 border-slate-700/50 hover:text-slate-300"
                }`}
              >
                {name}
              </button>
            ))}
          </div>
          {selectedAgent && <ThinkingStream events={events} agentName={selectedAgent} />}
        </div>
      )}
      {tab === "tools" && <ToolTimeline events={events} />}
      {tab === "debate" && <DebateFlow events={events} type="debate" />}
      {tab === "risk" && <DebateFlow events={events} type="risk" />}
      {tab === "decision" && <DecisionTrace events={events} />}
      {tab === "ticker" && <TickerAgentPanel onClose={onClose} />}
    </div>
  );
}
