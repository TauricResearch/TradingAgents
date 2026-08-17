"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AgentRail } from "@/components/AgentRail";
import { DecisionBadge } from "@/components/DecisionBadge";
import { InfoTip } from "@/components/InfoTip";
import { StateBlock } from "@/components/StateBlock";
import { api } from "@/lib/api";

export default function RunHome() {
  const { id } = useParams<{ id: string }>();
  const query = useQuery({ queryKey: ["analysis", id], queryFn: () => api.getAnalysis(id) });
  if (query.isError) {
    return <StateBlock title="Could not load analysis" message={(query.error as Error).message} onRetry={() => query.refetch()} />;
  }
  const row = query.data;
  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs text-mist">{row?.analysis_date} · {row?.provider} / {row?.model}</p>
          <h1 className="text-3xl font-semibold">{row?.symbol.replace(".NS", "")}</h1>
        </div>
        <div className="flex gap-2 text-sm">
          <Link className="rounded-md border border-line px-3 py-1.5" href={`/runs/${id}/agents`}>Agents</Link>
          <Link className="rounded-md border border-line px-3 py-1.5" href={`/runs/${id}/debate`}>Debate</Link>
          <Link className="rounded-md border border-gold/40 px-3 py-1.5 text-gold" href={`/runs/${id}/decision`}>Decision</Link>
          {row && (
            <Link className="rounded-md border border-line px-3 py-1.5" href={`/analyze/${encodeURIComponent(row.symbol)}`}>
              Stock
            </Link>
          )}
        </div>
      </header>
      <div className="flex items-center gap-3">
        <DecisionBadge action={row?.final_decision} />
        <span className="text-mist">
          Confidence {row?.confidence != null ? `${Math.round(row.confidence)}%` : "not reported"}
          <InfoTip text="Confidence is omitted unless the engine produced it." />
        </span>
      </div>
      <AgentRail agents={row?.agents || []} />
    </div>
  );
}
