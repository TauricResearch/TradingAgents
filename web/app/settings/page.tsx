"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SettingsApi } from "@/lib/api";
import { OllamaConfig } from "@/components/OllamaConfig";

export default function SettingsPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["settings"], queryFn: () => SettingsApi.get() });

  // Local edits — only the keys NOT in env. env-set keys are read-only.
  const [keyEdits, setKeyEdits] = useState<Record<string, string>>({});
  // Defaults form state
  const [defaults, setDefaults] = useState<Record<string, any>>({});

  useEffect(() => {
    if (q.data?.defaults) setDefaults(q.data.defaults);
  }, [q.data]);

  const saveKeys = useMutation({
    mutationFn: () => SettingsApi.update({ api_keys: keyEdits }),
    onSuccess: () => { setKeyEdits({}); qc.invalidateQueries({ queryKey: ["settings"] }); },
  });
  const saveDefaults = useMutation({
    mutationFn: () => SettingsApi.update({ defaults }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });

  if (q.isLoading) return <div className="text-muted">Loading settings…</div>;
  const data = q.data;
  if (!data) return <div className="text-danger">Could not load settings.</div>;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-muted text-sm">
          Stored locally at <code>{data.config_path}</code> (chmod 0600). Never transmitted off
          the host.
        </p>
      </header>

      {/* ---- API keys ---- */}
      <section>
        <h2 className="text-lg font-semibold mb-2">API keys</h2>
        <p className="text-xs text-muted mb-3">
          Keys present in the process environment (e.g. via <code>.env</code>) always win and show
          as <strong>env</strong>. Otherwise, set them here.
        </p>
        <div className="card">
          <div className="grid grid-cols-1 gap-2">
            {data.api_keys.map((k) => {
              const editing = !k.set_in_env;
              return (
                <div
                  key={k.env_name}
                  className="flex items-center gap-3 py-1.5 border-b border-border last:border-0"
                >
                  <div className="w-44 shrink-0">
                    <div className="text-sm font-medium">{k.label}</div>
                    <code className="text-xs text-muted">{k.env_name}</code>
                  </div>
                  <input
                    type="password"
                    className="input flex-1"
                    placeholder={
                      k.set_in_env
                        ? "•••• (from environment)"
                        : k.set_in_config
                          ? "•••• (saved)"
                          : "(not set)"
                    }
                    disabled={!editing}
                    value={keyEdits[k.env_name] ?? ""}
                    onChange={(e) => setKeyEdits({ ...keyEdits, [k.env_name]: e.target.value })}
                  />
                  <span className={`pill ${k.set_in_env ? "bg-success/15 text-success" : k.set_in_config ? "bg-accent/15 text-accent" : "bg-muted/15 text-muted"}`}>
                    {k.set_in_env ? "env" : k.set_in_config ? "saved" : "empty"}
                  </span>
                </div>
              );
            })}
          </div>
          <div className="flex justify-end mt-3">
            <button
              className="btn btn-primary"
              onClick={() => saveKeys.mutate()}
              disabled={Object.keys(keyEdits).length === 0 || saveKeys.isPending}
            >
              {saveKeys.isPending ? "Saving…" : "Save API keys"}
            </button>
          </div>
        </div>
      </section>

      {/* ---- Defaults ---- */}
      {/* ---- Ollama (local models) ---- */}
      <section>
        <h2 className="text-lg font-semibold mb-2">Ollama (local models)</h2>
        <p className="text-xs text-muted mb-3">
          Point at an Ollama server on your LAN to run analyses entirely
          locally. The API container reaches the host via{" "}
          <code>host.docker.internal</code> if Ollama runs on the same NAS;
          otherwise put the explicit IP/hostname.
        </p>
        <div className="card">
          <OllamaConfig
            currentUrl={(defaults.ollama_base_url as string) || ""}
            onSaved={() => qc.invalidateQueries({ queryKey: ["settings"] })}
          />
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-2">Default run configuration</h2>
        <p className="text-xs text-muted mb-3">
          Pre-fills the <strong>Run</strong> page form. Override per-run there.
        </p>
        <div className="card grid grid-cols-3 gap-3">
          <DefaultField name="llm_provider" label="Provider" defaults={defaults} setDefaults={setDefaults} />
          <DefaultField name="deep_think_llm" label="Deep-think model" defaults={defaults} setDefaults={setDefaults} />
          <DefaultField name="quick_think_llm" label="Quick-think model" defaults={defaults} setDefaults={setDefaults} />
          <NumberField name="max_debate_rounds" label="Bull/Bear rounds" min={1} max={5} defaults={defaults} setDefaults={setDefaults} />
          <NumberField name="max_risk_discuss_rounds" label="Risk rounds" min={1} max={5} defaults={defaults} setDefaults={setDefaults} />
          <DefaultField name="output_language" label="Output language" defaults={defaults} setDefaults={setDefaults} />
          <div className="col-span-3 flex justify-end">
            <button className="btn btn-primary" onClick={() => saveDefaults.mutate()} disabled={saveDefaults.isPending}>
              {saveDefaults.isPending ? "Saving…" : "Save defaults"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

function DefaultField({
  name, label, defaults, setDefaults,
}: { name: string; label: string; defaults: Record<string, any>; setDefaults: (d: Record<string, any>) => void }) {
  return (
    <div>
      <label className="label">{label}</label>
      <input
        className="input w-full"
        value={defaults[name] ?? ""}
        onChange={(e) => setDefaults({ ...defaults, [name]: e.target.value })}
      />
    </div>
  );
}

function NumberField({
  name, label, min, max, defaults, setDefaults,
}: { name: string; label: string; min: number; max: number; defaults: Record<string, any>; setDefaults: (d: Record<string, any>) => void }) {
  return (
    <div>
      <label className="label">{label}</label>
      <input
        type="number"
        min={min}
        max={max}
        className="input w-full"
        value={defaults[name] ?? min}
        onChange={(e) => setDefaults({ ...defaults, [name]: Number(e.target.value) })}
      />
    </div>
  );
}
