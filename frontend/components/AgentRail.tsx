"use client";

import type { AgentResult } from "@/lib/types";

const DEFAULT_AGENTS = [
  "Market Analyst",
  "Sentiment Analyst",
  "News Analyst",
  "Fundamentals Analyst",
  "Bull Researcher",
  "Bear Researcher",
  "Research Manager",
  "Trader",
  "Aggressive Analyst",
  "Neutral Analyst",
  "Conservative Analyst",
  "Portfolio Manager",
];

function mark(status: string) {
  if (status === "completed") return { glyph: "✓", label: "COMPLETE", className: "text-gain" };
  if (status === "running") return { glyph: "●", label: "RUNNING", className: "text-gold animate-pulse" };
  if (status === "failed") return { glyph: "!", label: "FAILED", className: "text-loss" };
  return { glyph: "○", label: "WAITING", className: "text-mist" };
}

export function AgentRail({ agents }: { agents: AgentResult[] }) {
  const byName = Object.fromEntries(agents.map((a) => [a.agent_name, a]));
  return (
    <ol className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
      {DEFAULT_AGENTS.map((name) => {
        const status = byName[name]?.status || "waiting";
        const meta = mark(status);
        return (
          <li key={name} className="flex items-center justify-between rounded-lg border border-line bg-ink-800 px-3 py-2">
            <span className="text-sm">{name}</span>
            <span className={`text-xs font-medium ${meta.className}`}>
              {meta.glyph} {meta.label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
