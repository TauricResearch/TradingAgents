"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Briefs } from "@/lib/api";
import type { Brief } from "@/lib/types";

export function BriefPanel({ runId }: { runId: string }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["brief", runId],
    queryFn: () => Briefs.get(runId),
    enabled: !!runId,
  });
  const generate = useMutation({
    mutationFn: (force: boolean) => Briefs.generate(runId, force),
    onSuccess: (data) => {
      qc.setQueryData(["brief", runId], { ...data, cached: true });
    },
  });

  const brief = q.data?.brief ?? null;

  if (q.isLoading) {
    return <div className="text-sm text-muted">Loading brief…</div>;
  }

  if (!brief) {
    return (
      <div className="card">
        <div className="text-sm text-muted mb-3">
          Distill the analysis into a plain-English action plan with timeframe,
          stop-loss, and trigger points.
        </div>
        <button
          className="btn btn-primary"
          onClick={() => generate.mutate(false)}
          disabled={generate.isPending}
        >
          {generate.isPending ? "Generating…" : "✨ Generate brief"}
        </button>
        {generate.isError && (
          <div className="text-sm text-danger mt-2">
            {(generate.error as Error).message}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="card space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-3xl font-bold tracking-tight">{brief.decision}</div>
          <div className="text-sm leading-relaxed mt-1">{brief.tldr}</div>
        </div>
        <button
          className="btn text-xs"
          onClick={() => generate.mutate(true)}
          disabled={generate.isPending}
          title="Regenerate the brief"
        >
          🔄 Regenerate
        </button>
      </div>

      <div className="grid sm:grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <Field label="Timeframe" value={brief.timeframe} />
        <Field label="Position size" value={brief.position_size} />
        <Field label="Entry" value={brief.entry_strategy} />
        <Field label="Stop loss" value={brief.stop_loss} />
        <Field label="Take profit" value={brief.take_profit} />
      </div>

      <div>
        <div className="font-semibold text-sm mb-1">Trigger points</div>
        <ul className="text-sm space-y-1">
          {brief.triggers.map((t, i) => (
            <li key={i}>
              <span className="text-warning">If</span> {t.condition}{" "}
              <span className="text-accent">→</span> {t.action}
            </li>
          ))}
        </ul>
      </div>

      <div>
        <div className="font-semibold text-sm mb-1">Key risks</div>
        <ul className="text-sm space-y-1 list-disc list-inside text-muted">
          {brief.key_risks.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      </div>

      <div className="text-sm border-t border-border pt-3">
        <span className="text-muted">vs S&amp;P 500: </span>
        {brief.benchmark_view}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-muted">{label}</div>
      <div>{value}</div>
    </div>
  );
}
