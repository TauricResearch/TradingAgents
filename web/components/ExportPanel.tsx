"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Exports } from "@/lib/api";
import type { ExportFile } from "@/lib/types";

const LABELS: Record<ExportFile["ext"], string> = {
  json: "JSON archive",
  md: "Markdown",
  html: "Standalone HTML",
  pdf: "PDF",
};

const HELP: Record<ExportFile["ext"], string> = {
  json: "Richest format — drop into Claude.ai for follow-up Q&A.",
  md: "Plain-text report — paste anywhere.",
  html: "Self-contained interactive report — emailable, viewable offline.",
  pdf: "Print-friendly archive document.",
};

export function ExportPanel({ runId }: { runId: string }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["exports", runId],
    queryFn: () => Exports.list(runId),
  });
  const regen = useMutation({
    mutationFn: () => Exports.regenerate(runId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["exports", runId] }),
  });

  const files = q.data ?? [];

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold">Files for this run</h3>
          <p className="text-xs text-muted">
            Auto-generated to <code>~/.tradingagents/exports/&lt;TICKER&gt;/</code>.
            Re-export creates fresh timestamped files; previous exports are kept.
          </p>
        </div>
        <button
          className="btn text-xs"
          onClick={() => regen.mutate()}
          disabled={regen.isPending}
        >
          {regen.isPending ? "Re-exporting…" : "🔄 Re-export all"}
        </button>
      </div>

      {q.isLoading && <div className="text-sm text-muted">Loading file list…</div>}
      <div className="space-y-1.5">
        {files.map((f) => (
          <div
            key={f.ext}
            className="flex items-center gap-3 text-sm py-1.5 border-b border-border last:border-0"
          >
            <div className="font-medium w-32">{LABELS[f.ext]}</div>
            <div className="flex-1 text-xs text-muted truncate" title={f.path}>
              {f.path}
            </div>
            <div className="text-xs text-muted w-16 text-right">
              {fmtSize(f.size_bytes)}
            </div>
            <a
              href={Exports.downloadUrl(runId, f.ext)}
              download={f.filename}
              className="btn text-xs"
              title={HELP[f.ext]}
            >
              ⬇ {f.ext}
            </a>
          </div>
        ))}
      </div>
    </div>
  );
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
