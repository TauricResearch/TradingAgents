"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { InfoTip } from "@/components/InfoTip";
import { api } from "@/lib/api";

export default function DebatePage() {
  const { id } = useParams<{ id: string }>();
  const query = useQuery({ queryKey: ["analysis", id], queryFn: () => api.getAnalysis(id) });
  const reports = (query.data?.payload?.reports || {}) as Record<string, string>;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">
        Bull / Bear debate
        <InfoTip text="These are the researchers' conclusions, not hidden reasoning traces." />
      </h1>
      <div className="grid gap-3 md:grid-cols-2">
        <article className="rounded-xl border border-gain/30 bg-ink-800 p-4">
          <h2 className="text-gain">BULL RESEARCHER</h2>
          <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-mist">{reports.bull || "Pending"}</p>
        </article>
        <article className="rounded-xl border border-loss/30 bg-ink-800 p-4">
          <h2 className="text-loss">BEAR RESEARCHER</h2>
          <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-mist">{reports.bear || "Pending"}</p>
        </article>
      </div>
      <article className="rounded-xl border border-line bg-ink-800 p-4">
        <h2>DEBATE SUMMARY</h2>
        <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-mist">{reports.research_manager || "Pending"}</p>
      </article>
    </div>
  );
}
