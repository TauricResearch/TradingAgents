"use client";

import Panel from "./ui/Panel";

const agents = [
  { icon: "\u{1F4CA}", label: "Market Analyst", detail: "RSI, MACD, Bollinger analysis complete", status: "Done", color: "cyan" as const },
  { icon: "\u{1F4CB}", label: "Fundamentals Analyst", detail: "Balance sheet & cash flow reviewed", status: "Done", color: "amber" as const },
  { icon: "\u{1F4F0}", label: "News Analyst", detail: "Global news & macro scan complete", status: "Done", color: "cyan" as const },
  { icon: "\u{1F4AC}", label: "Social Media Analyst", detail: "Sentiment scoring finalized", status: "Done", color: "purple" as const },
  { icon: "\u{1F402}", label: "Bull Researcher", detail: "Argument round 1 submitted", status: "Active", color: "green" as const },
  { icon: "\u{1F43B}", label: "Bear Researcher", detail: "Counter-argument pending", status: "Waiting", color: "amber" as const },
  { icon: "\u2696\uFE0F", label: "Trader", detail: "Awaiting debate conclusion", status: "Idle", color: "amber" as const },
  { icon: "\u{1F6E1}\uFE0F", label: "Risk Manager", detail: "Awaiting trade proposal", status: "Idle", color: "amber" as const },
];

const logs = [
  { time: "14:32:08", agent: "MKT", agentType: "analyst" as const, msg: "Technical indicators computed \u2014 MACD bullish cross detected" },
  { time: "14:32:15", agent: "FND", agentType: "analyst" as const, msg: "Balance sheet analysis complete \u2014 strong cash position" },
  { time: "14:32:22", agent: "NWS", agentType: "analyst" as const, msg: "Processed 47 news articles \u2014 net positive sentiment" },
  { time: "14:32:28", agent: "SOC", agentType: "analyst" as const, msg: "Social sentiment score: 0.62 \u2014 mixed retail signals" },
  { time: "14:32:35", agent: "BULL", agentType: "researcher" as const, msg: "Opening argument submitted \u2014 AI infrastructure thesis" },
  { time: "14:32:42", agent: "BEAR", agentType: "researcher" as const, msg: "Counter-argument: valuation stretched at 65x forward" },
];

const iconBgMap = {
  cyan: "bg-cyan-dim",
  amber: "bg-amber-dim",
  green: "bg-green-dim",
  purple: "bg-purple-dim",
};

const statusColorMap: Record<string, string> = {
  Done: "text-green",
  Active: "text-amber",
  Waiting: "text-text-tertiary",
  Idle: "text-text-tertiary",
};

const agentTypeColorMap = {
  analyst: "text-cyan",
  researcher: "text-amber",
  trader: "text-green",
  risk: "text-red",
};

export default function AgentStatus() {
  return (
    <Panel title="Agent Status" badge="8 Agents" badgeVariant="amber" delay={0.2}>
      <div className="flex flex-col gap-2">
        {agents.map((a) => (
          <div key={a.label} className="flex items-center gap-2.5 p-2 rounded bg-bg-elevated">
            <div className={`w-7 h-7 rounded-md grid place-items-center text-xs shrink-0 ${iconBgMap[a.color]}`}>
              {a.icon}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[11px] text-text-primary font-medium">{a.label}</div>
              <div className="text-[10px] text-text-tertiary mt-px">{a.detail}</div>
            </div>
            <div className={`text-[10px] font-medium ${statusColorMap[a.status]}`}>{a.status}</div>
          </div>
        ))}

        <div className="mt-2 max-h-[150px] overflow-y-auto flex flex-col">
          {logs.map((l, i) => (
            <div
              key={i}
              className="flex gap-2 py-1.5 border-b border-border-subtle text-[10px]"
            >
              <span className="text-text-tertiary shrink-0 tabular-nums">{l.time}</span>
              <span className={`shrink-0 font-medium ${agentTypeColorMap[l.agentType]}`}>{l.agent}</span>
              <span className="text-text-secondary overflow-hidden text-ellipsis whitespace-nowrap">{l.msg}</span>
            </div>
          ))}
        </div>
      </div>
    </Panel>
  );
}
