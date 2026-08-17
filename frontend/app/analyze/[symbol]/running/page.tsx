"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { AgentRail } from "@/components/AgentRail";
import { InfoTip } from "@/components/InfoTip";
import { StateBlock } from "@/components/StateBlock";
import { api } from "@/lib/api";

export default function RunningPage() {
  const params = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(params.symbol);
  const id = useSearchParams().get("id");
  const router = useRouter();
  const query = useQuery({
    queryKey: ["analysis", id],
    queryFn: () => api.getAnalysis(id!),
    enabled: Boolean(id),
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      return status === "running" || status === "queued" ? 1500 : false;
    },
  });

  useEffect(() => {
    if (!id) return;
    const source = new EventSource(`/api/v1/analysis/${id}/events`);
    source.onmessage = () => query.refetch();
    source.addEventListener("agent_completed", () => query.refetch());
    source.addEventListener("agent_started", () => query.refetch());
    source.addEventListener("analysis_completed", () => {
      query.refetch();
      source.close();
      router.push(`/runs/${id}/decision`);
    });
    source.addEventListener("analysis_failed", () => {
      query.refetch();
      source.close();
    });
    return () => source.close();
  }, [id]);

  if (!id) return <StateBlock title="Missing run" message="Start analysis from the stock page." />;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-mist">LIVE DESK</p>
          <h1 className="text-2xl font-semibold">{symbol.replace(".NS", "")}</h1>
          <p className="text-sm text-mist">
            Status: {query.data?.status || "connecting"}
            <InfoTip text="Status updates come from backend graph events, not fake percentages." />
          </p>
        </div>
        <div className="flex gap-2">
          <button className="rounded-md border border-line px-3 py-2 text-sm" onClick={() => api.cancelAnalysis(id)}>
            Cancel
          </button>
          <Link href={`/analyze/${encodeURIComponent(symbol)}`} className="rounded-md border border-line px-3 py-2 text-sm">
            Stock
          </Link>
        </div>
      </div>
      {query.data?.status === "failed" && (
        <StateBlock
          title="Analysis failed."
          message={query.data.error_message || "The engine could not complete this run."}
          onRetry={() => router.push(`/analyze/${encodeURIComponent(symbol)}`)}
        />
      )}
      <AgentRail agents={query.data?.agents || []} />
    </div>
  );
}
