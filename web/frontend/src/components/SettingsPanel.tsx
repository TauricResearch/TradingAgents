import { useState, useEffect, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchConfig,
  saveConfig,
  fetchConfigDefaults,
  type AppConfig,
} from "../lib/api";
import {
  Settings, Sun, Moon, Sparkles, BarChart3, Shield, Info, Loader, X, Check
} from "lucide-react";

interface Props {
  open: boolean;
  onClose: () => void;
  theme: "dark" | "light";
  toggleTheme: () => void;
}

const LABELS: Record<keyof AppConfig, string> = {
  TRADINGAGENTS_LLM_PROVIDER: "LLM Provider",
  TRADINGAGENTS_DEEP_THINK_LLM: "Deep Think Model",
  TRADINGAGENTS_QUICK_THINK_LLM: "Quick Think Model",
  TRADINGAGENTS_LLM_BACKEND_URL: "Backend URL",
  TRADINGAGENTS_OUTPUT_LANGUAGE: "Output Language",
  TRADINGAGENTS_MAX_DEBATE_ROUNDS: "Max Debate Rounds",
  TRADINGAGENTS_MAX_RISK_ROUNDS: "Max Risk Rounds",
  TRADINGAGENTS_TEMPERATURE: "Temperature",
  TRADINGAGENTS_BENCHMARK_TICKER: "Benchmark Ticker",
  TRADINGAGENTS_CHECKPOINT_ENABLED: "Checkpoint Enabled",
  TRADINGAGENTS_LLM_CACHE_ENABLED: "LLM Cache Enabled",
  AUTH_DISABLED: "Disable OAuth (dev only)",
};

const PROVIDER_OPTIONS = [
  "openai", "google", "anthropic", "xai", "deepseek",
  "dashscope", "zhipu", "minimax", "openrouter",
  "ollama", "openai_compatible", "bedrock",
];

export function SettingsPanel({ open, onClose, theme, toggleTheme }: Props) {
  const qc = useQueryClient();
  const [dirty, setDirty] = useState<Partial<AppConfig>>({});
  const [saved, setSaved] = useState(false);
  const [appVersion, setAppVersion] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["app-config"],
    queryFn: fetchConfig,
    enabled: open,
    staleTime: 30_000,
  });

  const mutation = useMutation({
    mutationFn: (updates: Partial<AppConfig>) => saveConfig(updates),
    onSuccess: () => {
      setSaved(true);
      setDirty({});
      qc.invalidateQueries({ queryKey: ["app-config"] });
      qc.invalidateQueries({ queryKey: ["config-models"] });
      setTimeout(() => setSaved(false), 2000);
    },
  });

  const config = data?.config;

  const set = useCallback((key: keyof AppConfig, val: string) => {
    setDirty((prev) => ({ ...prev, [key]: val }));
  }, []);

  const current = (key: keyof AppConfig): string =>
    key in dirty ? dirty[key]! : (config?.[key] ?? "");

  const handleSave = useCallback(() => {
    if (Object.keys(dirty).length === 0) return;
    mutation.mutate(dirty);
  }, [dirty, mutation]);

  const handleResetLlmDefaults = useCallback(async () => {
    try {
      const { defaults } = await fetchConfigDefaults();
      setDirty(defaults);
      mutation.mutate(defaults);
    } catch {
      // If the defaults endpoint fails, silently do nothing.
    }
  }, [mutation]);

  useEffect(() => {
    if (open) {
      fetch("/api/version")
        .then((r) => r.json())
        .then((d) => setAppVersion(d.version ?? ""))
        .catch(() => setAppVersion("unknown"));
    }
  }, [open]);

  useEffect(() => {
    if (!open) {
      setDirty({});
      setSaved(false);
    }
  }, [open]);

  if (!open) return null;

  return (
    <>
      <div
        className="drawer-overlay opacity-100 pointer-events-auto"
        onClick={onClose}
        aria-hidden
      />
      <div className="fixed inset-0 z-50 flex items-start justify-center pt-8 md:pt-12 pb-8 overflow-y-auto">
        <div
          className="glass-panel w-full max-w-lg mx-2 md:mx-4 animate-slide-up overflow-hidden"
          role="dialog"
          aria-label="Settings"
        >
          {/* Header */}
          <header className="flex items-center justify-between border-b border-slate-700/50 px-5 py-3">
            <div className="flex items-center gap-2">
              <Settings className="w-4 h-4 text-sky-400" />
              <h2 className="font-semibold text-slate-200 text-sm">Settings</h2>
            </div>
            <button
              onClick={onClose}
              aria-label="Close"
              className="p-1 hover:bg-slate-700/50 rounded-lg text-slate-500 hover:text-slate-300 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </header>

          {/* Body */}
          <div className="p-5 space-y-5 max-h-[70vh] overflow-y-auto">
            {isLoading && (
              <div className="flex items-center justify-center py-8">
                <Loader className="w-5 h-5 animate-spin text-sky-400" />
              </div>
            )}

            {!isLoading && config && (
              <>
                {/* ── Appearance ── */}
                <section>
                  <h3 className="section-header flex items-center gap-2 mb-3">
                    {theme === "dark" ? <Moon className="w-3.5 h-3.5 text-sky-400" /> : <Sun className="w-3.5 h-3.5 text-sky-400" />}
                    Appearance
                  </h3>
                  <div className="glass-panel p-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-sm font-medium text-slate-300">Dark Mode</div>
                        <div className="text-xs text-slate-500">Toggle dark/light theme</div>
                      </div>
                      <button
                        onClick={toggleTheme}
                        className={`relative w-10 h-5 rounded-full transition-colors ${
                          theme === "dark" ? "bg-sky-500" : "bg-slate-600"
                        }`}
                        role="switch"
                        aria-checked={theme === "dark"}
                      >
                        <span
                          className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${
                            theme === "dark" ? "translate-x-5" : "translate-x-0"
                          }`}
                        />
                      </button>
                    </div>
                  </div>
                </section>

                {/* ── LLM Configuration ── */}
                <section>
                  <h3 className="section-header flex items-center gap-2 mb-3">
                    <Sparkles className="w-3.5 h-3.5 text-sky-400" />
                    LLM Configuration
                  </h3>
                  <div className="glass-panel p-3 space-y-3">
                    <ConfigSelect
                      label={LABELS.TRADINGAGENTS_LLM_PROVIDER}
                      value={current("TRADINGAGENTS_LLM_PROVIDER")}
                      options={PROVIDER_OPTIONS}
                      onChange={(v) => set("TRADINGAGENTS_LLM_PROVIDER", v)}
                    />
                    <ConfigInput
                      label={LABELS.TRADINGAGENTS_DEEP_THINK_LLM}
                      value={current("TRADINGAGENTS_DEEP_THINK_LLM")}
                      onChange={(v) => set("TRADINGAGENTS_DEEP_THINK_LLM", v)}
                    />
                    <ConfigInput
                      label={LABELS.TRADINGAGENTS_QUICK_THINK_LLM}
                      value={current("TRADINGAGENTS_QUICK_THINK_LLM")}
                      onChange={(v) => set("TRADINGAGENTS_QUICK_THINK_LLM", v)}
                    />
                    <ConfigInput
                      label={LABELS.TRADINGAGENTS_TEMPERATURE}
                      value={current("TRADINGAGENTS_TEMPERATURE")}
                      onChange={(v) => set("TRADINGAGENTS_TEMPERATURE", v)}
                      placeholder="e.g. 0.0 (leave empty for default)"
                    />
                    <ConfigInput
                      label={LABELS.TRADINGAGENTS_LLM_BACKEND_URL}
                      value={current("TRADINGAGENTS_LLM_BACKEND_URL")}
                      onChange={(v) => set("TRADINGAGENTS_LLM_BACKEND_URL", v)}
                      placeholder="https://api.openai.com/v1"
                    />
                    <button
                      onClick={handleResetLlmDefaults}
                      disabled={mutation.isPending}
                      className="w-full mt-1 text-[11px] font-medium text-slate-500 hover:text-sky-400 border border-slate-700/50 hover:border-sky-500/30 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-40"
                    >
                      Reset to Defaults
                    </button>
                  </div>
                </section>

                {/* ── Analysis ── */}
                <section>
                  <h3 className="section-header flex items-center gap-2 mb-3">
                    <BarChart3 className="w-3.5 h-3.5 text-sky-400" />
                    Analysis
                  </h3>
                  <div className="glass-panel p-3 space-y-3">
                    <ConfigInput
                      label={LABELS.TRADINGAGENTS_OUTPUT_LANGUAGE}
                      value={current("TRADINGAGENTS_OUTPUT_LANGUAGE")}
                      onChange={(v) => set("TRADINGAGENTS_OUTPUT_LANGUAGE", v)}
                    />
                    <ConfigInput
                      label={LABELS.TRADINGAGENTS_MAX_DEBATE_ROUNDS}
                      value={current("TRADINGAGENTS_MAX_DEBATE_ROUNDS")}
                      onChange={(v) => set("TRADINGAGENTS_MAX_DEBATE_ROUNDS", v)}
                      type="number"
                    />
                    <ConfigInput
                      label={LABELS.TRADINGAGENTS_MAX_RISK_ROUNDS}
                      value={current("TRADINGAGENTS_MAX_RISK_ROUNDS")}
                      onChange={(v) => set("TRADINGAGENTS_MAX_RISK_ROUNDS", v)}
                      type="number"
                    />
                    <ConfigInput
                      label={LABELS.TRADINGAGENTS_BENCHMARK_TICKER}
                      value={current("TRADINGAGENTS_BENCHMARK_TICKER")}
                      onChange={(v) => set("TRADINGAGENTS_BENCHMARK_TICKER", v)}
                      placeholder="e.g. SPY (leave empty for auto)"
                    />
                  </div>
                </section>

                {/* ── Advanced ── */}
                <section>
                  <h3 className="section-header flex items-center gap-2 mb-3">
                    <Shield className="w-3.5 h-3.5 text-sky-400" />
                    Advanced
                  </h3>
                  <div className="glass-panel p-3 space-y-3">
                    <ConfigToggle
                      label={LABELS.TRADINGAGENTS_CHECKPOINT_ENABLED}
                      value={current("TRADINGAGENTS_CHECKPOINT_ENABLED")}
                      onChange={(v) => set("TRADINGAGENTS_CHECKPOINT_ENABLED", v)}
                    />
                    <ConfigToggle
                      label={LABELS.TRADINGAGENTS_LLM_CACHE_ENABLED}
                      value={current("TRADINGAGENTS_LLM_CACHE_ENABLED")}
                      onChange={(v) => set("TRADINGAGENTS_LLM_CACHE_ENABLED", v)}
                    />
                    <ConfigToggle
                      label={LABELS.AUTH_DISABLED}
                      value={current("AUTH_DISABLED")}
                      onChange={(v) => set("AUTH_DISABLED", v)}
                    />
                    <div className="text-xs text-slate-600 pt-1">
                      Changes are saved to <code className="text-slate-500 bg-slate-800 px-1 rounded">.env</code> and apply
                      to future runs. No server restart required.
                    </div>
                  </div>
                </section>

                {/* ── About ── */}
                <section>
                  <h3 className="section-header flex items-center gap-2 mb-3">
                    <Info className="w-3.5 h-3.5 text-sky-400" />
                    About
                  </h3>
                  <div className="glass-panel p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-slate-300">Version</span>
                      <span className="text-sm font-mono text-slate-400 bg-slate-800/50 px-2 py-0.5 rounded border border-slate-700/50">
                        v{appVersion || "..."}
                      </span>
                    </div>
                    <div className="text-xs text-slate-600">
                      Source: <code className="text-slate-500 bg-slate-800 px-1 rounded">VERSION</code> file at repo root
                    </div>
                  </div>
                </section>
              </>
            )}

            {!isLoading && !config && (
              <div className="text-center py-6 text-sm text-slate-500">
                Could not load configuration.
              </div>
            )}
          </div>

          {/* Footer */}
          <footer className="border-t border-slate-700/50 px-5 py-3 flex items-center justify-between">
            <span className="text-xs text-slate-600">
              {saved && (
                <span className="inline-flex items-center gap-1 text-emerald-400">
                  <Check className="w-3 h-3" /> Saved
                </span>
              )}
            </span>
            <div className="flex items-center gap-2">
              <button onClick={onClose} className="btn-secondary text-xs">
                Close
              </button>
              <button
                onClick={handleSave}
                disabled={Object.keys(dirty).length === 0 || mutation.isPending}
                className="btn-primary text-xs"
              >
                {mutation.isPending ? (
                  <span className="inline-flex items-center gap-1.5">
                    <Loader className="w-3 h-3 animate-spin" />
                    Saving...
                  </span>
                ) : "Save"}
              </button>
            </div>
          </footer>
        </div>
      </div>
    </>
  );
}

/* ── sub-components ── */

function ConfigInput({
  label,
  value,
  onChange,
  type,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
}) {
  return (
    <label className="flex flex-col gap-0.5">
      <span className="text-[10px] font-medium text-slate-600 uppercase tracking-wider">{label}</span>
      <input
        type={type ?? "text"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500/30 font-mono tabular-nums transition-colors"
      />
    </label>
  );
}

function ConfigSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-0.5">
      <span className="text-[10px] font-medium text-slate-600 uppercase tracking-wider">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500/30 transition-colors"
      >
        {options.map((opt) => (
          <option key={opt} value={opt}>{opt}</option>
        ))}
      </select>
    </label>
  );
}

function ConfigToggle({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  const checked = value.toLowerCase() === "true" || value === "1";
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm font-medium text-slate-300">{label}</span>
      <button
        onClick={() => onChange(checked ? "false" : "true")}
        className={`relative w-10 h-5 rounded-full transition-colors ${
          checked ? "bg-sky-500" : "bg-slate-600"
        }`}
        role="switch"
        aria-checked={checked}
      >
        <span
          className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${
            checked ? "translate-x-5" : "translate-x-0"
          }`}
        />
      </button>
    </div>
  );
}
