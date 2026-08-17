"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { DecisionBadge } from "@/components/DecisionBadge";
import { InfoTip } from "@/components/InfoTip";
import { inr } from "@/lib/format";
import { api } from "@/lib/api";

export default function DecisionPage() {
  const { id } = useParams<{ id: string }>();
  const query = useQuery({ queryKey: ["analysis", id], queryFn: () => api.getAnalysis(id) });
  const d = query.data?.decision;
  const levels = [
    ["Entry", d?.entry_price],
    ["Stop", d?.stop_loss],
    ["Target", d?.price_target],
  ] as const;
  const hasLevels = levels.some(([, value]) => value != null);
  return (
    <div className="mx-auto max-w-2xl">
      <div className="rounded-2xl border border-gold/40 bg-ink-800 p-8 text-center shadow-terminal">
        <p className="text-xs tracking-[0.28em] text-mist">AI DECISION</p>
        <div className="mt-6 flex justify-center">
          <DecisionBadge action={d?.action || query.data?.final_decision} size="lg" />
        </div>
        <p className="mt-6 text-5xl font-semibold tabular">
          {d?.confidence != null ? `${Math.round(d.confidence)}%` : "—"}
        </p>
        <p className="text-xs tracking-widest text-mist">CONFIDENCE</p>
        <div className="mt-6 grid grid-cols-2 gap-3 text-sm">
          <p>Risk <span className="text-white">{d?.risk_level || "—"}</span></p>
          <p>
            Horizon <span className="text-white">{d?.time_horizon || "—"}</span>
            <InfoTip text="Horizon, entry, stop and target appear only if the trader or portfolio manager actually produced them." />
          </p>
        </div>
        {hasLevels && (
          <div className="mt-4 grid grid-cols-3 gap-2 text-sm">
            {levels.map(([label, value]) => (
              <div key={label} className="rounded-md border border-line px-2 py-3">
                <p className="text-xs text-mist">{label}</p>
                <p className="tabular">{inr(value as number | null)}</p>
              </div>
            ))}
          </div>
        )}
        <p className="mt-6 text-left text-sm leading-7 text-mist">
          {d?.in_plain_language || d?.reason || "Decision text will appear when the Portfolio Manager finishes."}
        </p>
      </div>
      <div className="mt-4 flex justify-center gap-3 text-sm">
        <Link href={`/runs/${id}/agents`} className="text-gold">Agents</Link>
        <Link href={`/runs/${id}/debate`} className="text-gold">Debate</Link>
        {query.data && <Link href={`/analyze/${encodeURIComponent(query.data.symbol)}`} className="text-gold">Stock</Link>}
      </div>
    </div>
  );
}
