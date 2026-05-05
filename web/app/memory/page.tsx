"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Memory } from "@/lib/api";
import { Markdown } from "@/components/Markdown";

export default function MemoryPage() {
  const q = useQuery({ queryKey: ["memory"], queryFn: () => Memory.get() });
  const [view, setView] = useState<"all" | "resolved" | "pending">("all");

  if (q.isLoading) return <div className="text-muted">Loading memory…</div>;
  const data = q.data;
  if (!data) return <div className="text-danger">Could not load memory log.</div>;

  let entries = data.entries;
  if (view === "resolved") entries = entries.filter((e) => e.resolved);
  if (view === "pending") entries = entries.filter((e) => !e.resolved);

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-bold">Decision memory</h1>
        <p className="text-muted text-sm">
          Rolling decision log with realised return reflections vs SPY. Sourced from{" "}
          <code>{data.path}</code>.
        </p>
      </header>

      <div className="grid grid-cols-3 gap-3 max-w-md">
        <Stat label="Total" value={data.total} />
        <Stat label="Resolved" value={data.resolved_count} />
        <Stat label="Pending" value={data.pending_count} />
      </div>

      <div className="flex gap-1 border-b border-border pb-2">
        {(["all", "resolved", "pending"] as const).map((v) => (
          <button
            key={v}
            onClick={() => setView(v)}
            className={`px-3 py-1 text-sm rounded-t-md ${
              view === v ? "bg-surface text-fg" : "text-muted hover:text-fg"
            }`}
          >
            {v}
          </button>
        ))}
      </div>

      {entries.length === 0 ? (
        <div className="card text-sm text-muted">No entries yet.</div>
      ) : (
        <div className="space-y-3">
          {entries.map((e, i) => (
            <div
              key={i}
              className={`card ${e.resolved ? "" : "border-warning/40"}`}
            >
              <Markdown>{e.raw}</Markdown>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="card text-center">
      <div className="text-xs text-muted">{label}</div>
      <div className="text-2xl font-semibold">{value}</div>
    </div>
  );
}
