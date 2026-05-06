"use client";

import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { SettingsApi } from "@/lib/api";

const SUGGESTIONS = [
  { label: "Same NAS host (Docker host gateway)", value: "http://host.docker.internal:11434/v1" },
  { label: "Other server on LAN (replace IP)",     value: "http://192.168.2.X:11434/v1" },
];

export function OllamaConfig({
  currentUrl,
  onSaved,
}: {
  currentUrl: string;
  onSaved: (url: string, models: { name: string }[]) => void;
}) {
  const qc = useQueryClient();
  const [url, setUrl] = useState(currentUrl);
  const [models, setModels] = useState<Array<{ name: string; parameter_size?: string; family?: string; size?: number }>>([]);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [statusKind, setStatusKind] = useState<"success" | "danger" | null>(null);

  useEffect(() => { setUrl(currentUrl); }, [currentUrl]);

  const test = useMutation({
    mutationFn: (target: string) => SettingsApi.ollamaModels(target || undefined),
    onSuccess: (data) => {
      setModels(data.models);
      setStatusKind("success");
      setStatusMsg(`Connected. Found ${data.count} model${data.count === 1 ? "" : "s"}.`);
    },
    onError: (e: any) => {
      setStatusKind("danger");
      setStatusMsg(e?.message || "connection failed");
      setModels([]);
    },
  });

  const save = useMutation({
    mutationFn: () => SettingsApi.update({ defaults: { ollama_base_url: url.trim() } }),
    onSuccess: async () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      // Re-detect after save so the model list is fresh.
      try {
        const res = await SettingsApi.ollamaModels(url.trim() || undefined);
        setModels(res.models);
        setStatusKind("success");
        setStatusMsg(`Saved. Found ${res.count} model${res.count === 1 ? "" : "s"}.`);
        onSaved(url.trim(), res.models);
      } catch (e: any) {
        setStatusKind("danger");
        setStatusMsg(`Saved, but ${e?.message || "couldn't list models"}`);
      }
    },
  });

  return (
    <div className="space-y-3">
      <div className="flex items-end gap-2">
        <div className="flex-1">
          <label className="label">Ollama base URL</label>
          <input
            className="input w-full"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="http://host.docker.internal:11434/v1"
          />
        </div>
        <button
          type="button"
          className="btn"
          onClick={() => test.mutate(url.trim())}
          disabled={!url.trim() || test.isPending}
        >
          {test.isPending ? "Testing…" : "Test connection"}
        </button>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => save.mutate()}
          disabled={save.isPending || url.trim() === currentUrl.trim()}
        >
          {save.isPending ? "Saving…" : "Save"}
        </button>
      </div>

      {/* Quick-fill suggestions */}
      <div className="flex flex-wrap gap-2 text-xs">
        {SUGGESTIONS.map((s) => (
          <button
            key={s.value}
            type="button"
            className="btn text-xs"
            onClick={() => setUrl(s.value)}
          >
            {s.label}
          </button>
        ))}
      </div>

      {statusMsg && (
        <div className={`text-sm ${statusKind === "success" ? "text-success" : "text-danger"}`}>
          {statusMsg}
        </div>
      )}

      {models.length > 0 && (
        <div>
          <div className="text-xs uppercase tracking-wider text-muted mb-1">
            Detected models ({models.length})
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {models.map((m) => (
              <div key={m.name} className="border border-border rounded p-2 text-sm">
                <div className="font-medium">{m.name}</div>
                <div className="text-xs text-muted">
                  {[m.family, m.parameter_size, m.size ? `${(m.size / 1024 / 1024 / 1024).toFixed(1)} GB` : null]
                    .filter(Boolean)
                    .join(" · ")}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
