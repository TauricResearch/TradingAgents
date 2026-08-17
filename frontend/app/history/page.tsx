"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import { DecisionBadge } from "@/components/DecisionBadge";
import { InfoTip } from "@/components/InfoTip";
import { api } from "@/lib/api";

export default function HistoryPage() {
  const list = useQuery({ queryKey: ["history"], queryFn: () => api.listAnalysis() });
  const [decision, setDecision] = useState("ALL");
  const [band, setBand] = useState("ALL");
  const rows = useMemo(() => {
    return (list.data?.items || []).filter((item) => {
      if (decision !== "ALL" && (item.final_decision || "").toUpperCase() !== decision) return false;
      if (band === "HIGH" && (item.confidence || 0) < 75) return false;
      if (band === "MEDIUM" && ((item.confidence || 0) < 50 || (item.confidence || 0) >= 75)) return false;
      if (band === "LOW" && (item.confidence || 0) >= 50) return false;
      return true;
    });
  }, [list.data, decision, band]);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">
        Decision history
        <InfoTip text="Saved runs from this terminal. Actual outcome is filled on the Evaluation page when later prices exist." />
      </h1>
      <div className="flex flex-wrap gap-2">
        {["ALL", "BUY", "SELL", "HOLD"].map((item) => (
          <button key={item} onClick={() => setDecision(item)} className={`rounded-md border px-3 py-1 text-sm ${decision === item ? "border-gold text-gold" : "border-line text-mist"}`}>
            {item}
          </button>
        ))}
        {["ALL", "HIGH", "MEDIUM", "LOW"].map((item) => (
          <button key={item} onClick={() => setBand(item)} className={`rounded-md border px-3 py-1 text-sm ${band === item ? "border-gold text-gold" : "border-line text-mist"}`}>
            {item === "ALL" ? "All confidence" : `${item} confidence`}
          </button>
        ))}
      </div>
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full text-left text-sm">
          <thead className="bg-ink-800 text-mist">
            <tr>
              <th className="px-3 py-2">Date</th>
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2">Decision</th>
              <th className="px-3 py-2">Confidence</th>
              <th className="px-3 py-2">Risk</th>
              <th className="px-3 py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.analysis_id} className="border-t border-line">
                <td className="px-3 py-2">{row.analysis_date}</td>
                <td className="px-3 py-2">
                  <Link className="text-gold" href={`/runs/${row.analysis_id}`}>
                    {row.symbol}
                  </Link>
                </td>
                <td className="px-3 py-2">
                  <DecisionBadge action={row.final_decision} size="sm" />
                </td>
                <td className="px-3 py-2 tabular">{row.confidence != null ? `${Math.round(row.confidence)}%` : "—"}</td>
                <td className="px-3 py-2">{row.risk_level || "—"}</td>
                <td className="px-3 py-2 text-mist">{row.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
