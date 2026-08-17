"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { InfoTip } from "@/components/InfoTip";
import { api } from "@/lib/api";
import type { Settings } from "@/lib/types";

export default function SettingsPage() {
  const query = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [form, setForm] = useState<Settings | null>(null);
  useEffect(() => {
    if (query.data) setForm(query.data);
  }, [query.data]);
  const save = useMutation({ mutationFn: () => api.saveSettings(form || {}) });
  if (!form) return <p className="text-mist">Loading setup…</p>;

  function set<K extends keyof Settings>(key: K, value: Settings[K]) {
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <h1 className="text-2xl font-semibold">Setup</h1>
      <section className="rounded-xl border border-line bg-ink-800 p-4 space-y-3">
        <h2 className="text-sm text-mist">
          LLM
          <InfoTip text="API keys stay in the backend .env. The browser never receives provider secrets." />
        </h2>
        <Field label="Provider">
          <select value={form.llm_provider} onChange={(e) => set("llm_provider", e.target.value)} className="w-full rounded-md border border-line bg-ink-900 px-2 py-2">
            {["openai", "google", "anthropic", "ollama", "openrouter", "deepseek", "groq"].map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </Field>
        <Field label="Deep model">
          <input value={form.model} onChange={(e) => set("model", e.target.value)} className="w-full rounded-md border border-line bg-ink-900 px-2 py-2" />
        </Field>
        <Field label="Quick model">
          <input value={form.quick_model || ""} onChange={(e) => set("quick_model", e.target.value)} className="w-full rounded-md border border-line bg-ink-900 px-2 py-2" />
        </Field>
        <Field label="Temperature">
          <input type="number" step="0.1" value={form.temperature ?? ""} onChange={(e) => set("temperature", e.target.value === "" ? null : Number(e.target.value))} className="w-full rounded-md border border-line bg-ink-900 px-2 py-2" />
        </Field>
        <Field label="Research depth">
          <select value={form.research_depth} onChange={(e) => set("research_depth", e.target.value)} className="w-full rounded-md border border-line bg-ink-900 px-2 py-2">
            <option value="shallow">shallow</option>
            <option value="medium">medium</option>
            <option value="deep">deep</option>
          </select>
        </Field>
        <Field label="Debate rounds">
          <input type="number" min={1} max={5} value={form.debate_rounds ?? 1} onChange={(e) => set("debate_rounds", Number(e.target.value))} className="w-full rounded-md border border-line bg-ink-900 px-2 py-2" />
        </Field>
      </section>
      <section className="rounded-xl border border-line bg-ink-800 p-4 space-y-3">
        <h2 className="text-sm text-mist">Market data</h2>
        <Field label="Provider">
          <select value={form.market_data_provider} onChange={(e) => set("market_data_provider", e.target.value)} className="w-full rounded-md border border-line bg-ink-900 px-2 py-2">
            <option value="yahoo">yahoo</option>
            <option value="nse">nse (via yahoo until a broker feed is configured)</option>
          </select>
        </Field>
        <Field label="Refresh interval (seconds)">
          <input type="number" value={form.refresh_interval_seconds} onChange={(e) => set("refresh_interval_seconds", Number(e.target.value))} className="w-full rounded-md border border-line bg-ink-900 px-2 py-2" />
        </Field>
      </section>
      <section className="rounded-xl border border-line bg-ink-800 p-4 space-y-2">
        <h2 className="text-sm text-mist">Analysts</h2>
        <Toggle label="Technical" checked={form.enable_technical} onChange={(v) => set("enable_technical", v)} />
        <Toggle label="Fundamentals" checked={form.enable_fundamentals} onChange={(v) => set("enable_fundamentals", v)} />
        <Toggle label="Sentiment" checked={form.enable_sentiment} onChange={(v) => set("enable_sentiment", v)} />
        <Toggle label="News" checked={form.enable_news} onChange={(v) => set("enable_news", v)} />
      </section>
      <button onClick={() => save.mutate()} className="rounded-md bg-gold px-4 py-2 text-sm font-semibold text-ink-950">
        {save.isSuccess ? "Saved" : "Save setup"}
      </button>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="text-mist">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center justify-between text-sm">
      {label}
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
    </label>
  );
}
