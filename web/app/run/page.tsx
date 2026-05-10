"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Runs, SettingsApi } from "@/lib/api";
import { runStreamUrl } from "@/lib/ws";
import type { RunCreateRequest, RunEvent } from "@/lib/types";
import { Markdown } from "@/components/Markdown";
import { BriefPanel } from "@/components/BriefPanel";
import { ChartComparison } from "@/components/ChartComparison";
import { ChatPanel } from "@/components/ChatPanel";
import { ExportPanel } from "@/components/ExportPanel";

const PROVIDERS = [
  { id: "openai", label: "OpenAI (GPT)" },
  { id: "anthropic", label: "Anthropic (Claude)" },
  { id: "google", label: "Google (Gemini)" },
  { id: "xai", label: "xAI (Grok)" },
  { id: "deepseek", label: "DeepSeek" },
  { id: "qwen", label: "Qwen" },
  { id: "glm", label: "GLM" },
  { id: "openrouter", label: "OpenRouter" },
  { id: "ollama", label: "Ollama (local)" },
] as const;

const DATA_VENDORS = ["yfinance", "alpha_vantage"] as const;

type SectionKey =
  | "market_report"
  | "sentiment_report"
  | "news_report"
  | "fundamentals_report"
  | "research_judge"
  | "trader_investment_plan"
  | "final_trade_decision";

const SECTION_TABS: { key: SectionKey; label: string }[] = [
  { key: "market_report", label: "Market" },
  { key: "sentiment_report", label: "Sentiment" },
  { key: "news_report", label: "News" },
  { key: "fundamentals_report", label: "Fundamentals" },
  { key: "research_judge", label: "Research Mgr" },
  { key: "trader_investment_plan", label: "Trader Plan" },
  { key: "final_trade_decision", label: "Final Decision" },
];

type RunUiState = {
  sections: Partial<Record<SectionKey, string>>;
  bull: string;
  bear: string;
  aggressive: string;
  conservative: string;
  neutral: string;
  log: string[];
  stats: { llm_calls: number; tool_calls: number; tokens_in: number; tokens_out: number };
  decision: string | null;
  error: string | null;
  warning: string | null;
  done: boolean;
};

const EMPTY_UI: RunUiState = {
  sections: {},
  bull: "",
  bear: "",
  aggressive: "",
  conservative: "",
  neutral: "",
  log: [],
  stats: { llm_calls: 0, tool_calls: 0, tokens_in: 0, tokens_out: 0 },
  decision: null,
  error: null,
  warning: null,
  done: false,
};

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function RunPage() {
  return (
    <Suspense fallback={<div className="text-muted">Loading run form...</div>}>
      <RunPageContent />
    </Suspense>
  );
}

function RunPageContent() {
  const qc = useQueryClient();
  const searchParams = useSearchParams();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => SettingsApi.get() });
  const defaults = settings.data?.defaults ?? {};
  const initializedFromDefaults = useRef(false);

  const [form, setForm] = useState<RunCreateRequest>({
    ticker: "NVDA",
    trade_date: todayIso(),
    llm_provider: "anthropic",
    deep_think_llm: "claude-sonnet-4-6",
    quick_think_llm: "claude-haiku-4-5",
    backend_url: null,
    max_debate_rounds: 1,
    max_risk_discuss_rounds: 1,
    data_vendors: {
      core_stock_apis: "yfinance",
      technical_indicators: "yfinance",
      fundamental_data: "yfinance",
      news_data: "yfinance",
    },
  });

  // Pull saved defaults once they load.
  useEffect(() => {
    if (!settings.data || initializedFromDefaults.current) return;
    initializedFromDefaults.current = true;
    const tickerFromUrl = searchParams.get("ticker")?.trim().toUpperCase();
    setForm((f) => ({
      ...f,
      ticker: tickerFromUrl || f.ticker,
      llm_provider: defaults.llm_provider ?? f.llm_provider,
      deep_think_llm: defaults.deep_think_llm ?? f.deep_think_llm,
      quick_think_llm: defaults.quick_think_llm ?? f.quick_think_llm,
      backend_url: defaults.backend_url || null,
      max_debate_rounds: defaults.max_debate_rounds ?? f.max_debate_rounds,
      max_risk_discuss_rounds: defaults.max_risk_discuss_rounds ?? f.max_risk_discuss_rounds,
      data_vendors: { ...f.data_vendors, ...(defaults.data_vendors ?? {}) },
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings.data]);

  const [runId, setRunId] = useState<string | null>(null);
  const [activeRun, setActiveRun] = useState<RunCreateRequest | null>(null);
  const [ui, setUi] = useState<RunUiState>(EMPTY_UI);
  const [activeTab, setActiveTab] = useState<SectionKey | "debate" | "risk" | "log">(
    "market_report",
  );
  const wsRef = useRef<WebSocket | null>(null);

  const create = useMutation({
    mutationFn: (req: RunCreateRequest) => Runs.create(req),
    onMutate: (req) => {
      setUi(EMPTY_UI);
      setRunId(null);
      setActiveRun(req);
      setActiveTab("market_report");
    },
    onSuccess: (r, req) => {
      setActiveRun(req);
      setRunId(r.run_id);
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
  });

  const cancel = useMutation({
    mutationFn: () => (runId ? Runs.cancel(runId) : Promise.resolve({ cancelled: false })),
    onSuccess: () => {
      wsRef.current?.close();
      setUi((u) => ({ ...u, error: "Cancelled by user." }));
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
  });

  // Manage the WebSocket lifecycle.
  useEffect(() => {
    if (!runId || ui.done || ui.error) return;
    const ws = new WebSocket(runStreamUrl(runId));
    wsRef.current = ws;

    ws.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data) as RunEvent;
        applyEvent(ev);
      } catch {
        // skip malformed
      }
    };
    ws.onerror = () => {
      setUi((u) => ({ ...u, error: "WebSocket error — check the API server" }));
    };
    return () => {
      ws.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  function applyEvent(ev: RunEvent) {
    setUi((u) => {
      const next = { ...u };
      const data = ev.data ?? {};
      switch (ev.type) {
        case "section":
          next.sections = { ...u.sections, [data.key as SectionKey]: data.content };
          break;
        case "debate":
          if (data.side === "bull") next.bull = data.content;
          if (data.side === "bear") next.bear = data.content;
          break;
        case "risk":
          if (data.side === "aggressive") next.aggressive = data.content;
          if (data.side === "conservative") next.conservative = data.content;
          if (data.side === "neutral") next.neutral = data.content;
          break;
        case "stats":
          next.stats = {
            llm_calls: data.llm_calls ?? u.stats.llm_calls,
            tool_calls: data.tool_calls ?? u.stats.tool_calls,
            tokens_in: data.tokens_in ?? u.stats.tokens_in,
            tokens_out: data.tokens_out ?? u.stats.tokens_out,
          };
          break;
        case "chunk":
          next.log = [...u.log, `[${data.role ?? "?"}] ${data.content ?? ""}`].slice(-200);
          break;
        case "tool_start":
          next.log = [...u.log, `[tool→${data.tool}] ${data.input ?? ""}`].slice(-200);
          break;
        case "tool_end":
          next.log = [...u.log, `[tool←] ${data.preview ?? ""}`].slice(-200);
          break;
        case "warning":
          next.warning = data.message ?? "";
          break;
        case "error":
          next.error = data.message ?? "unknown error";
          break;
        case "done":
          next.decision = data.decision ?? null;
          next.done = true;
          // Fresh runs may now have a brief, exports etc. — invalidate all caches for this run.
          qc.invalidateQueries({ queryKey: ["runs"] });
          break;
      }
      return next;
    });
  }

  const isStreaming = !!runId && !ui.done && !ui.error;
  const displayedRun = activeRun ?? form;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Run analysis</h1>
        <p className="text-muted text-sm">
          Pick ticker, date, provider, model, and depth. Streams agent output live.
        </p>
      </header>

      {/* ---- Form ---- */}
      <form
        className="card grid grid-cols-1 md:grid-cols-3 gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate(form);
        }}
      >
        <div>
          <label className="label">Ticker</label>
          <input
            className="input w-full"
            value={form.ticker}
            onChange={(e) => setForm({ ...form, ticker: e.target.value.toUpperCase() })}
            disabled={isStreaming}
            required
          />
        </div>
        <div>
          <label className="label">Trade date</label>
          <input
            type="date"
            className="input w-full"
            value={form.trade_date}
            onChange={(e) => setForm({ ...form, trade_date: e.target.value })}
            disabled={isStreaming}
            required
          />
        </div>
        <div>
          <label className="label">Provider</label>
          <select
            className="input w-full"
            value={form.llm_provider}
            onChange={(e) => setForm({ ...form, llm_provider: e.target.value })}
            disabled={isStreaming}
          >
            {PROVIDERS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
        <ModelField
          label="Deep-think model"
          value={form.deep_think_llm}
          onChange={(v) => setForm({ ...form, deep_think_llm: v })}
          provider={form.llm_provider}
          disabled={isStreaming}
        />
        <ModelField
          label="Quick-think model"
          value={form.quick_think_llm}
          onChange={(v) => setForm({ ...form, quick_think_llm: v })}
          provider={form.llm_provider}
          disabled={isStreaming}
        />
        <div className="col-span-full">
          <label className="label">Custom base URL</label>
          <input
            className="input w-full"
            placeholder="https://your-openai-compatible-endpoint/v1"
            value={form.backend_url ?? ""}
            onChange={(e) =>
              setForm({ ...form, backend_url: e.target.value.trim() || null })
            }
            disabled={isStreaming}
          />
        </div>
        <div>
          <label className="label">Bull/Bear rounds</label>
          <input
            type="number"
            min={1}
            max={5}
            className="input w-full"
            value={form.max_debate_rounds}
            onChange={(e) =>
              setForm({ ...form, max_debate_rounds: Number(e.target.value) })
            }
            disabled={isStreaming}
          />
        </div>
        <div>
          <label className="label">Risk rounds</label>
          <input
            type="number"
            min={1}
            max={5}
            className="input w-full"
            value={form.max_risk_discuss_rounds}
            onChange={(e) =>
              setForm({ ...form, max_risk_discuss_rounds: Number(e.target.value) })
            }
            disabled={isStreaming}
          />
        </div>
        <div className="col-span-full">
          <div className="text-sm font-semibold mb-2">Data vendors</div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <VendorField
              label="Stock data"
              value={form.data_vendors.core_stock_apis}
              disabled={isStreaming}
              onChange={(v) =>
                setForm({
                  ...form,
                  data_vendors: { ...form.data_vendors, core_stock_apis: v },
                })
              }
            />
            <VendorField
              label="Technical"
              value={form.data_vendors.technical_indicators}
              disabled={isStreaming}
              onChange={(v) =>
                setForm({
                  ...form,
                  data_vendors: { ...form.data_vendors, technical_indicators: v },
                })
              }
            />
            <VendorField
              label="Fundamentals"
              value={form.data_vendors.fundamental_data}
              disabled={isStreaming}
              onChange={(v) =>
                setForm({
                  ...form,
                  data_vendors: { ...form.data_vendors, fundamental_data: v },
                })
              }
            />
            <VendorField
              label="News"
              value={form.data_vendors.news_data}
              disabled={isStreaming}
              onChange={(v) =>
                setForm({
                  ...form,
                  data_vendors: { ...form.data_vendors, news_data: v },
                })
              }
            />
          </div>
        </div>
        <div className="col-span-full flex justify-end gap-2">
          {isStreaming && (
            <button
              type="button"
              className="btn btn-danger"
              onClick={() => cancel.mutate()}
              disabled={cancel.isPending}
            >
              {cancel.isPending ? "Cancelling..." : "Cancel run"}
            </button>
          )}
          <button
            type="submit"
            className="btn btn-primary"
            disabled={isStreaming || create.isPending}
          >
            {isStreaming ? "Streaming…" : "▶ Analyze"}
          </button>
        </div>
        {create.isError && (
          <div className="col-span-full text-sm text-danger">
            {(create.error as Error).message}
          </div>
        )}
        {cancel.isError && (
          <div className="col-span-full text-sm text-danger">
            {(cancel.error as Error).message}
          </div>
        )}
      </form>

      {/* ---- Status ---- */}
      {runId && (
        <div className="card flex items-center justify-between text-sm">
          <div>
            {ui.error ? (
              <span className="text-danger">⚠ {ui.error}</span>
            ) : ui.done ? (
              <span className="text-success">
                ✓ Decision: <strong>{ui.decision ?? "—"}</strong>
              </span>
            ) : (
              <span className="text-accent">● Streaming {displayedRun.ticker} …</span>
            )}
            {ui.warning && (
              <span className="ml-3 text-warning">{ui.warning}</span>
            )}
          </div>
          <div className="text-muted">
            LLM {ui.stats.llm_calls} · Tool {ui.stats.tool_calls} · Tokens{" "}
            {ui.stats.tokens_in.toLocaleString()}↑ / {ui.stats.tokens_out.toLocaleString()}↓
          </div>
        </div>
      )}

      {/* ---- Tabs (during + after run) ---- */}
      {runId && (
        <div>
          <div className="flex flex-wrap gap-1 border-b border-border mb-3">
            {SECTION_TABS.map((t) => (
              <TabBtn
                key={t.key}
                active={activeTab === t.key}
                done={!!ui.sections[t.key]}
                onClick={() => setActiveTab(t.key)}
              >
                {t.label}
              </TabBtn>
            ))}
            <TabBtn
              active={activeTab === "debate"}
              done={!!ui.bull || !!ui.bear}
              onClick={() => setActiveTab("debate")}
            >
              Bull vs Bear
            </TabBtn>
            <TabBtn
              active={activeTab === "risk"}
              done={!!(ui.aggressive || ui.conservative || ui.neutral)}
              onClick={() => setActiveTab("risk")}
            >
              Risk Debate
            </TabBtn>
            <TabBtn active={activeTab === "log"} done={ui.log.length > 0} onClick={() => setActiveTab("log")}>
              Live Log
            </TabBtn>
          </div>

          <div className="card">
            {activeTab === "debate" ? (
              <div className="grid sm:grid-cols-2 gap-6">
                <div>
                  <h3 className="font-semibold mb-2">Bull</h3>
                  <Markdown>{ui.bull}</Markdown>
                </div>
                <div>
                  <h3 className="font-semibold mb-2">Bear</h3>
                  <Markdown>{ui.bear}</Markdown>
                </div>
              </div>
            ) : activeTab === "risk" ? (
              <div className="space-y-4">
                <div>
                  <h3 className="font-semibold mb-2">Aggressive</h3>
                  <Markdown>{ui.aggressive}</Markdown>
                </div>
                <div>
                  <h3 className="font-semibold mb-2">Conservative</h3>
                  <Markdown>{ui.conservative}</Markdown>
                </div>
                <div>
                  <h3 className="font-semibold mb-2">Neutral</h3>
                  <Markdown>{ui.neutral}</Markdown>
                </div>
              </div>
            ) : activeTab === "log" ? (
              <pre className="text-xs whitespace-pre-wrap max-h-96 overflow-y-auto font-mono">
                {ui.log.slice(-100).join("\n") || "(no events yet)"}
              </pre>
            ) : (
              <Markdown>{ui.sections[activeTab as SectionKey]}</Markdown>
            )}
          </div>
        </div>
      )}

      {/* ---- After-run panels ---- */}
      {runId && ui.done && (
        <>
          <section>
            <h2 className="text-lg font-semibold mb-3">Plain-English brief</h2>
            <BriefPanel runId={runId} />
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-3">vs S&amp;P 500 / Nasdaq-100</h2>
            <ChartComparison ticker={displayedRun.ticker} tradeDate={displayedRun.trade_date} />
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-3">Files</h2>
            <ExportPanel runId={runId} />
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-3">Chat about this run</h2>
            <ChatPanel runId={runId} />
          </section>
        </>
      )}
    </div>
  );
}

/**
 * Model field. For ollama provider we fetch the live model list from the
 * server so the user picks from what's actually installed; for everyone
 * else we just show a free text input (the framework's catalog has dozens
 * of named models per provider — not worth maintaining a UI list).
 */
function ModelField({
  label,
  value,
  onChange,
  provider,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  provider: string;
  disabled?: boolean;
}) {
  const isOllama = provider === "ollama";
  const ollamaModels = useQuery({
    queryKey: ["ollama-models"],
    queryFn: () => SettingsApi.ollamaModels(),
    enabled: isOllama,
    retry: false,
  });

  if (isOllama) {
    const list = ollamaModels.data?.models ?? [];
    return (
      <div>
        <label className="label">{label}</label>
        {ollamaModels.isError && (
          <div className="text-xs text-danger mb-1">
            Couldn't reach Ollama. Configure URL on the Settings page.
          </div>
        )}
        <select
          className="input w-full"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
        >
          {value && !list.find((m) => m.name === value) && (
            <option value={value}>{value} (not installed)</option>
          )}
          {list.length === 0 && !ollamaModels.isLoading && (
            <option value="">{ollamaModels.isError ? "Set URL in Settings" : "No models found"}</option>
          )}
          {list.map((m) => (
            <option key={m.name} value={m.name}>
              {m.name}
              {m.parameter_size ? ` (${m.parameter_size})` : ""}
            </option>
          ))}
        </select>
      </div>
    );
  }
  return (
    <div>
      <label className="label">{label}</label>
      <input
        className="input w-full"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        required
      />
    </div>
  );
}

function VendorField({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      <select
        className="input w-full"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      >
        {DATA_VENDORS.map((vendor) => (
          <option key={vendor} value={vendor}>
            {vendor}
          </option>
        ))}
      </select>
    </div>
  );
}


function TabBtn({
  active,
  done,
  onClick,
  children,
}: {
  active: boolean;
  done: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 text-sm border-b-2 transition-colors ${
        active
          ? "border-accent text-accent"
          : "border-transparent text-muted hover:text-fg"
      }`}
    >
      {done && <span className="mr-1 text-success">✓</span>}
      {children}
    </button>
  );
}
