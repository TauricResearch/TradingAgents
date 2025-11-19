"use client";

import { AgentStatusType } from "@/lib/types";

interface AgentStatus {
  agent: string;
  status: AgentStatusType;
  team: string;
}

interface AgentProgressProps {
  agentStatuses: Record<string, AgentStatusType>;
}

const TEAMS = {
  "Analyst Team": ["Market Analyst", "Social Analyst", "News Analyst", "Fundamentals Analyst"],
  "Research Team": ["Bull Researcher", "Bear Researcher", "Research Manager"],
  "Trading Team": ["Trader"],
  "Risk Management": ["Risky Analyst", "Neutral Analyst", "Safe Analyst"],
  "Portfolio Management": ["Portfolio Manager"],
};

const STATUS_COLORS: Record<AgentStatusType, string> = {
  pending: "bg-gray-200 text-gray-600",
  in_progress: "bg-blue-500 text-white animate-pulse",
  completed: "bg-green-500 text-white",
  error: "bg-red-500 text-white",
};

export default function AgentProgress({ agentStatuses }: AgentProgressProps) {
  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-xl font-bold mb-4">Agent Progress</h2>
      <div className="space-y-4">
        {Object.entries(TEAMS).map(([teamName, agents]) => (
          <div key={teamName} className="border-b pb-4 last:border-b-0">
            <h3 className="font-semibold text-sm text-gray-700 mb-2">{teamName}</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {agents.map((agent) => {
                const status = agentStatuses[agent] || "pending";
                return (
                  <div
                    key={agent}
                    className={`px-3 py-2 rounded text-sm text-center ${STATUS_COLORS[status]}`}
                  >
                    <div className="font-medium">{agent}</div>
                    <div className="text-xs mt-1 capitalize">{status.replace("_", " ")}</div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

