"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Planner } from "@/lib/api";
import type { SyncResult } from "@/lib/api";

/**
 * Two-step planner sync: dry-run → preview → apply.
 *
 * On the `/portfolio` page this sits at the top so the user always sees
 * "is the connection live?" + "click to pull holdings."
 */
export function PlannerSync({ onApplied }: { onApplied: () => void }) {
  const qc = useQueryClient();
  const status = useQuery({
    queryKey: ["planner-status"],
    queryFn: () => Planner.status(),
    refetchInterval: 60_000,
  });

  const [preview, setPreview] = useState<SyncResult | null>(null);

  const dryRun = useMutation({
    mutationFn: () => Planner.sync(true),
    onSuccess: setPreview,
  });
  const apply = useMutation({
    mutationFn: () => Planner.sync(false),
    onSuccess: (r) => {
      setPreview(r);
      qc.invalidateQueries({ queryKey: ["portfolio-summary"] });
      onApplied();
    },
  });

  const s = status.data;
  const indicator = !s
    ? <Badge color="muted">checking…</Badge>
    : !s.configured
      ? <Badge color="warning">not configured</Badge>
      : s.reachable
        ? <Badge color="success">reachable</Badge>
        : <Badge color="danger">unreachable</Badge>;

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 className="font-semibold">Sync from financial planner</h3>
          <div className="text-xs text-muted mt-1 flex items-center gap-2">
            {indicator}
            {s?.url && <code>{s.url}</code>}
          </div>
        </div>
        <div className="flex gap-2">
          <button
            className="btn"
            onClick={() => dryRun.mutate()}
            disabled={!s?.reachable || dryRun.isPending}
          >
            {dryRun.isPending ? "Previewing…" : "↻ Preview changes"}
          </button>
          <button
            className="btn btn-primary"
            onClick={() => apply.mutate()}
            disabled={!s?.reachable || apply.isPending || !preview || preview.diff.every(d => d.action === "unchanged")}
          >
            {apply.isPending ? "Syncing…" : "Apply"}
          </button>
        </div>
      </div>

      {s && !s.configured && (
        <div className="text-xs text-muted">
          Set <code>PLANNER_API_URL</code> and <code>PLANNER_API_KEY</code> on
          the API container's <code>.env</code>, then restart the api service.
          {s.error && <div className="mt-1 text-danger">{s.error}</div>}
        </div>
      )}

      {s && s.configured && !s.reachable && (
        <div className="text-xs text-danger">
          Configured but unreachable. {s.error}
        </div>
      )}

      {dryRun.isError && <div className="text-sm text-danger">{(dryRun.error as Error).message}</div>}
      {apply.isError && <div className="text-sm text-danger">{(apply.error as Error).message}</div>}

      {preview && <DiffTable r={preview} />}
    </div>
  );
}

function DiffTable({ r }: { r: SyncResult }) {
  const counts = r.diff.reduce(
    (acc, d) => { acc[d.action] = (acc[d.action] ?? 0) + 1; return acc; },
    {} as Record<string, number>,
  );
  return (
    <div>
      <div className="text-sm text-muted mb-2">
        Fetched <b>{r.fetched_holdings}</b> holdings across <b>{r.accounts}</b> account{r.accounts === 1 ? "" : "s"}.
        {" "}
        {!r.dry_run
          ? <>Applied <b>{r.applied}</b>, skipped <b>{r.skipped}</b>{r.errors.length ? `, ${r.errors.length} errors` : ""}.</>
          : <>{counts.create ?? 0} to create, {counts.update ?? 0} to update, {counts.unchanged ?? 0} unchanged.</>
        }
      </div>
      {r.errors.length > 0 && (
        <ul className="text-xs text-danger mb-2 space-y-0.5">
          {r.errors.map((e, i) => <li key={i}>{e}</li>)}
        </ul>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-muted">
              <th className="text-left py-1 px-2">Action</th>
              <th className="text-left py-1 px-2">Ticker</th>
              <th className="text-left py-1 px-2">Account</th>
              <th className="text-right py-1 px-2">Planner shares</th>
              <th className="text-right py-1 px-2">Existing shares</th>
              <th className="text-right py-1 px-2">Planner cost</th>
            </tr>
          </thead>
          <tbody>
            {r.diff.map((d, i) => (
              <tr key={i} className="border-t border-border">
                <td className="py-1 px-2">
                  <Badge color={d.action === "create" ? "success" : d.action === "update" ? "warning" : "muted"}>
                    {d.action}
                  </Badge>
                </td>
                <td className="py-1 px-2 font-semibold">{d.ticker}</td>
                <td className="py-1 px-2 text-muted">{d.account}</td>
                <td className="py-1 px-2 text-right tabular-nums">{d.planner_shares}</td>
                <td className="py-1 px-2 text-right tabular-nums">{d.existing_shares ?? "—"}</td>
                <td className="py-1 px-2 text-right tabular-nums">
                  {d.planner_cost_basis != null ? `$${d.planner_cost_basis.toFixed(2)}` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Badge({ children, color }: { children: React.ReactNode; color: "success" | "warning" | "danger" | "muted" }) {
  const map: Record<string, string> = {
    success: "bg-success/15 text-success",
    warning: "bg-warning/15 text-warning",
    danger:  "bg-danger/15 text-danger",
    muted:   "bg-muted/15 text-muted",
  };
  return <span className={`pill ${map[color]}`}>{children}</span>;
}
