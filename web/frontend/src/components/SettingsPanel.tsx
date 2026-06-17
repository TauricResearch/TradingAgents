import { useState, useEffect, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchConfig,
  saveConfig,
  fetchConfigDefaults,
  fetchCachedFreeKeys,
  fetchFreeLlmKeysStream,
  type AppConfig,
  type FreeLlmKey,
} from "../lib/api";

interface Props {
  open: boolean;
  onClose: () => void;
  theme: "dark" | "light";
  toggleTheme: () => void;
  autoRefreshEnabled: boolean;
  autoRefreshCountdown: number;
  onAutoRefreshToggle: () => void;
  onAutoRefreshNow?: () => void;
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
  TRADINGAGENTS_FREE_KEYS_ENABLED: "Fetch Free Keys on Startup",
};

const PROVIDER_OPTIONS = [
  "openai", "google", "anthropic", "xai", "deepseek",
  "dashscope", "zhipu", "minimax", "openrouter",
  "ollama", "openai_compatible", "bedrock",
];

export function SettingsPanel({ open, onClose, theme, toggleTheme, autoRefreshEnabled, autoRefreshCountdown, onAutoRefreshToggle, onAutoRefreshNow }: Props) {
  const qc = useQueryClient();
  const [dirty, setDirty] = useState<Partial<AppConfig>>({});
  const [saved, setSaved] = useState(false);
  const [freeKeys, setFreeKeys] = useState<FreeLlmKey[]>([]);
  const [freeKeysTotal, setFreeKeysTotal] = useState(0);
  const [freeKeysLoading, setFreeKeysLoading] = useState(false);
  const [freeKeysError, setFreeKeysError] = useState<string | null>(null);
  const [freeKeysCachedAt, setFreeKeysCachedAt] = useState<string | null>(null);

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

  const handleFetchFreeKeys = useCallback(async () => {
    setFreeKeysLoading(true);
    setFreeKeysError(null);
    setFreeKeys([]);
    setFreeKeysTotal(0);
    setFreeKeysCachedAt(null);

    let completed = false;

    await fetchFreeLlmKeysStream({
      onMeta: (meta) => {
        setFreeKeysTotal(meta.total);
      },
      onKeyResult: (key) => {
        setFreeKeys((prev) => [...prev, key]);
      },
      onDone: (keys) => {
        completed = true;
        setFreeKeys(keys);
        setFreeKeysLoading(false);
      },
      onError: (err) => {
        completed = true;
        setFreeKeysError(err);
        setFreeKeysLoading(false);
      },
    });

    // If the stream ended without a terminal event, release loading state.
    if (!completed) setFreeKeysLoading(false);
  }, []);

  const handleAutoRefreshNow = useCallback(async () => {
    onAutoRefreshNow?.();
    setFreeKeysLoading(true);
    setFreeKeysError(null);
    setFreeKeys([]);
    setFreeKeysTotal(0);
    setFreeKeysCachedAt(null);

    let completed = false;

    await fetchFreeLlmKeysStream({
      onMeta: (meta) => {
        setFreeKeysTotal(meta.total);
      },
      onKeyResult: (key) => {
        setFreeKeys((prev) => [...prev, key]);
      },
      onDone: (keys) => {
        completed = true;
        setFreeKeys(keys);
        setFreeKeysLoading(false);
      },
      onError: (err) => {
        completed = true;
        setFreeKeysError(err);
        setFreeKeysLoading(false);
      },
    });

    // If the stream ended without a terminal event, release loading state.
    if (!completed) setFreeKeysLoading(false);
  }, [onAutoRefreshNow]);

  const handleApplyFreeKey = useCallback(
    (entry: FreeLlmKey) => {
      const updates: Record<string, string> = {
        TRADINGAGENTS_LLM_PROVIDER: "openai_compatible",
        TRADINGAGENTS_LLM_BACKEND_URL: "https://aiapiv2.pekpik.com/v1",
        TRADINGAGENTS_DEEP_THINK_LLM: entry.model,
        TRADINGAGENTS_QUICK_THINK_LLM: entry.model,
        OPENAI_COMPATIBLE_API_KEY: entry.key,
      };
      setDirty(updates);
      mutation.mutate(updates);
    },
    [mutation],
  );

  useEffect(() => {
    if (!open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setDirty({});
      setSaved(false);
      setFreeKeys([]);
      setFreeKeysTotal(0);
      setFreeKeysError(null);
      setFreeKeysCachedAt(null);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    fetchCachedFreeKeys()
      .then((cache) => {
        if (cancelled || !cache) return;
        setFreeKeys(cache.keys);
        setFreeKeysTotal(cache.keys.length);
        setFreeKeysCachedAt(cache.saved_at);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [open]);

  if (!open) return null;

  return (
    <>
      <div
        className="drawer-overlay opacity-100 pointer-events-auto"
        onClick={onClose}
        aria-hidden
      />
      <div className="fixed inset-0 z-50 flex items-start justify-center pt-12 pb-8 overflow-y-auto">
        <div
          className="glass-panel w-full max-w-lg mx-4 animate-slide-up overflow-hidden"
          role="dialog"
          aria-label="Settings"
        >
          {/* Header */}
          <header className="flex items-center justify-between border-b border-slate-700/50 px-5 py-3">
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.075-.124l-1.217.456a1.125 1.125 0 0 1-1.37-.49l-1.296-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.296-2.247a1.125 1.125 0 0 1 1.37-.491l1.217.456c.355.133.75.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
              </svg>
              <h2 className="font-semibold text-slate-200 text-sm">Settings</h2>
            </div>
            <button
              onClick={onClose}
              aria-label="Close"
              className="p-1 hover:bg-slate-700/50 rounded-lg text-slate-500 hover:text-slate-300 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
              </svg>
            </button>
          </header>

          {/* Body */}
          <div className="p-5 space-y-5 max-h-[70vh] overflow-y-auto">
            {isLoading && (
              <div className="flex items-center justify-center py-8">
                <div className="w-5 h-5 rounded-full border-2 border-sky-500/30 border-t-sky-400 animate-spin" />
              </div>
            )}

            {!isLoading && config && (
              <>
                {/* ── Appearance ── */}
                <section>
                  <h3 className="section-header flex items-center gap-2 mb-3">
                    <svg className="w-3.5 h-3.5 text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2.25m6.364.386-1.591 1.591M21 12h-2.25m-.386 6.364-1.591-1.591M12 18.75V21m-4.773-4.227-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z" />
                    </svg>
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
                    <svg className="w-3.5 h-3.5 text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.455 2.456Z" />
                    </svg>
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

                {/* ── Free LLM Keys ── */}
                <section>
                  <h3 className="section-header flex items-center gap-2 mb-3">
                    <svg className="w-3.5 h-3.5 text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.455 2.456Z" />
                    </svg>
                    Free LLM Keys
                  </h3>
                  <div className="glass-panel p-3 space-y-3">
                    <p className="text-xs text-slate-500 leading-relaxed">
                      Fetch free API keys from{" "}
                      <a href="https://github.com/alistaitsacle/free-llm-api-keys" target="_blank" rel="noopener noreferrer" className="text-sky-400 hover:underline">alistaitsacle/free-llm-api-keys</a>.
                      Keys are tested automatically. Click a working key to apply &amp; save.
                    </p>

                    <button
                      onClick={autoRefreshEnabled && !freeKeysLoading ? handleAutoRefreshNow : handleFetchFreeKeys}
                      disabled={freeKeysLoading}
                      className="btn-primary text-xs w-full flex items-center justify-center gap-1.5 relative overflow-hidden"
                    >
                      {freeKeysLoading ? (
                        <>
                          <svg className="w-3 h-3 animate-spin" viewBox="0 0 24 24" fill="none">
                            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" className="opacity-25" />
                            <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                          </svg>
                          {autoRefreshEnabled
                            ? "Refreshing..."
                            : freeKeysTotal > 0
                              ? `Testing ${freeKeys.length}/${freeKeysTotal}...`
                              : "Testing keys..."}
                        </>
                      ) : autoRefreshEnabled ? (
                        <>
                          <div
                            className="absolute inset-0 rounded-lg transition-all duration-1000 ease-linear"
                            style={{
                              width: `${(autoRefreshCountdown / 600_000) * 100}%`,
                              background: "linear-gradient(90deg, rgba(56,189,248,0.12), rgba(56,189,248,0.22))",
                            }}
                          />
                          <span className="relative z-10 flex items-center gap-1.5">
                            <svg className="w-3 h-3 text-sky-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182" />
                            </svg>
                            Next refresh in {formatCountdown(autoRefreshCountdown)}
                          </span>
                        </>
                      ) : (
                        "Fetch Free Keys"
                      )}
                    </button>

                    <div className="flex items-center justify-between pt-1">
                      <span className="text-[10px] text-slate-500">Auto-refresh every 10m</span>
                      <button
                        onClick={onAutoRefreshToggle}
                        className={`relative w-9 h-4 rounded-full transition-colors ${
                          autoRefreshEnabled ? "bg-sky-500" : "bg-slate-600"
                        }`}
                        role="switch"
                        aria-checked={autoRefreshEnabled}
                      >
                        <span
                          className={`absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white shadow transition-transform ${
                            autoRefreshEnabled ? "translate-x-5" : "translate-x-0"
                          }`}
                        />
                      </button>
                    </div>

                    <div className="flex items-center justify-between">
                      <span className="text-[10px] text-slate-500">Fetch on startup</span>
                      <span className="text-[9px] text-slate-600 mr-auto ml-2">(auto-skipped for Ollama)</span>
                      <button
                        onClick={() => {
                          const v = current("TRADINGAGENTS_FREE_KEYS_ENABLED");
                          set("TRADINGAGENTS_FREE_KEYS_ENABLED", (!v || v === "false") ? "true" : "false");
                        }}
                        className={`relative w-9 h-4 rounded-full transition-colors ${
                          isFreeKeysEnabled(current("TRADINGAGENTS_FREE_KEYS_ENABLED")) ? "bg-sky-500" : "bg-slate-600"
                        }`}
                        role="switch"
                        aria-checked={isFreeKeysEnabled(current("TRADINGAGENTS_FREE_KEYS_ENABLED"))}
                      >
                        <span
                          className={`absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white shadow transition-transform ${
                            isFreeKeysEnabled(current("TRADINGAGENTS_FREE_KEYS_ENABLED")) ? "translate-x-5" : "translate-x-0"
                          }`}
                        />
                      </button>
                    </div>

                    {freeKeysError && (
                      <div className="text-xs text-red-400 bg-red-900/20 rounded-lg px-2.5 py-2">
                        {freeKeysError}
                      </div>
                    )}

                    {!freeKeysLoading && freeKeys.length === 0 && (
                      <div className="text-xs text-slate-500 text-center py-2">
                        No keys found in repo.
                      </div>
                    )}

                    {freeKeys.length > 0 && (
                      <div className="space-y-1 max-h-64 overflow-y-auto">
                        <div className="text-[10px] font-medium text-slate-600 uppercase tracking-wider px-1 flex items-center gap-2">
                          <span>{freeKeys.filter((k) => k.status === "working").length} working / {freeKeysTotal || freeKeys.length} total</span>
                          {freeKeysCachedAt && !freeKeysLoading && (
                            <span className="text-[9px] font-normal text-slate-500 bg-slate-800/50 px-1.5 py-0.5 rounded-full">
                              Cached {formatTimeAgo(freeKeysCachedAt)}
                            </span>
                          )}
                        </div>
                        {freeKeys.map((entry, i) => (
                          <FreeKeyRow
                            key={i}
                            entry={entry}
                            onApply={handleApplyFreeKey}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                </section>

                {/* ── Analysis ── */}
                <section>
                  <h3 className="section-header flex items-center gap-2 mb-3">
                    <svg className="w-3.5 h-3.5 text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3v11.25A2.25 2.25 0 0 0 6 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0 1 18 16.5h-2.25m-7.5 0h7.5m-7.5 0-1 3m8.5-3 1 3m0 0 .5 1.5m-.5-1.5h-9.5m0 0-.5 1.5m.75-9 3-3 2.148 2.148A12.061 12.061 0 0 1 16.5 7.605" />
                    </svg>
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
                    <svg className="w-3.5 h-3.5 text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" />
                    </svg>
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
                    <div className="text-xs text-slate-600 pt-1">
                      Changes are saved to <code className="text-slate-500 bg-slate-800 px-1 rounded">.env</code> and apply
                      to future runs. No server restart required.
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
              {saved && <span className="text-emerald-400">Saved ✓</span>}
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
                  <>
                    <svg className="inline w-3 h-3 mr-1.5 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" className="opacity-25" />
                      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                    </svg>
                    Saving…
                  </>
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
        className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500/30 font-mono tabular-nums"
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
        className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500/30"
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

/* ── Free Key Row ── */

const STATUS_CONFIG: Record<string, { dot: string; label: string }> = {
  working: { dot: "bg-emerald-400", label: "Working" },
  low_balance: { dot: "bg-amber-400", label: "Drained" },
  no_access: { dot: "bg-red-400", label: "No Access" },
  rate_limited: { dot: "bg-orange-400", label: "Rate Limited" },
  error: { dot: "bg-slate-500", label: "Error" },
  unknown: { dot: "bg-slate-500", label: "Unknown" },
};

function FreeKeyRow({
  entry,
  onApply,
}: {
  entry: FreeLlmKey;
  onApply: (e: FreeLlmKey) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const cfg = STATUS_CONFIG[entry.status] ?? STATUS_CONFIG.unknown;

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(entry.key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard may be unavailable
    }
  }, [entry.key]);

  return (
    <div
      className={`rounded-lg border px-2.5 py-2 text-xs transition-colors ${
        entry.status === "working"
          ? "border-emerald-700/40 bg-emerald-900/10"
          : "border-slate-700/30 bg-slate-800/30"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0 flex-1">
          <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${cfg.dot}`} />
          <span className="font-medium text-slate-300 truncate" title={entry.model}>
            {entry.provider}
          </span>
          <span className="text-slate-500 truncate hidden sm:inline" title={entry.model}>
            {entry.model}
          </span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {entry.status === "working" ? (
            <button
              onClick={() => onApply(entry)}
              className="text-[10px] font-medium text-emerald-400 hover:text-emerald-300 px-1.5 py-0.5 rounded hover:bg-emerald-900/20 transition-colors"
              title="Apply this key to config"
            >
              Apply
            </button>
          ) : (
            <span className="text-[10px] text-slate-600">{cfg.label}</span>
          )}
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-slate-600 hover:text-slate-400 transition-colors"
          >
            <svg
              className={`w-3 h-3 transition-transform ${expanded ? "rotate-180" : ""}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
            </svg>
          </button>
        </div>
      </div>

      {expanded && (
        <div className="mt-2 pt-2 border-t border-slate-700/30 space-y-1.5">
          <div className="flex items-center justify-between gap-2">
            <code className="text-[10px] font-mono text-slate-400 truncate">{entry.masked_key}</code>
            <button
              onClick={handleCopy}
              className="text-[10px] text-sky-400 hover:text-sky-300 shrink-0"
            >
              {copied ? "Copied!" : "Copy"}
            </button>
          </div>
          {entry.status === "working" && (
            <div className="flex gap-2 text-[10px] text-slate-500">
              <span>Budget: {entry.budget}</span>
              <span>Expires: {entry.expires}</span>
              <span>RPM: {entry.rate_limit}</span>
            </div>
          )}
          {entry.test_response && (
            <div className="text-[10px] text-emerald-500/70">
              Test: "{entry.test_response}"
            </div>
          )}
          {entry.error_message && (
            <div className="text-[10px] text-slate-500 truncate" title={entry.error_message}>
              {entry.error_message}
            </div>
          )}
          <div className="text-[10px] text-slate-600">
            <span className="font-mono">OPENAI_COMPATIBLE_API_KEY</span> = full key above
          </div>
        </div>
      )}
    </div>
  );
}

/** Treat empty/unset as "true" to match the backend default (free_keys_enabled: True). */
function isFreeKeysEnabled(v: string): boolean {
  return !v || v === "true" || v === "1";
}

function formatTimeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const min = Math.floor(diffMs / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function formatCountdown(ms: number): string {
  const totalSec = Math.ceil(ms / 1000);
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `${min}:${sec.toString().padStart(2, "0")}`;
}
