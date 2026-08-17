"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { InfoTip } from "@/components/InfoTip";
import { api } from "@/lib/api";

export default function AgentsPage() {
  const { id } = useParams<{ id: string }>();
  const query = useQuery({ queryKey: ["analysis", id], queryFn: () => api.getAnalysis(id) });
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">
        Agent desk
        <InfoTip text="Summaries only. Private chain-of-thought is not shown." />
      </h1>
      <div className="grid gap-3 md:grid-cols-2">
        {(query.data?.agents || []).map((agent) => (
          <article key={agent.agent_name} className="rounded-xl border border-line bg-ink-800 p-4">
            <div className="flex items-center justify-between">
              <h2 className="font-medium">{agent.agent_name}</h2>
              <span className="text-xs uppercase text-mist">{agent.status}</span>
            </div>
            <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-mist">
              {agent.summary || "Waiting for this agent to finish."}
            </p>
          </article>
        ))}
      </div>
    </div>
  );
}
