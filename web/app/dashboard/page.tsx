"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, Provider } from "../../lib/api";

type Model = { name: string; id: string };
type Quote = { ok: boolean; symbol?: string; price?: number; change?: number; pct?: number; up?: boolean };

const STEPS = ["Ticker", "Date", "Language", "Analysts", "Depth", "Provider", "Models", "Thinking", "Tables", "Confirm"];

function QuoteWidget({ ticker }: { ticker: string }) {
  const [q, setQ] = useState<Quote | null>(null);
  useEffect(() => {
    if (!ticker) return;
    let alive = true;
    async function poll() {
      try {
        const r = await api.quote(ticker);
        if (alive) setQ(r);
      } catch {
        if (alive) setQ({ ok: false });
      }
    }
    poll();
    const t = setInterval(poll, 30000);
    return () => { alive = false; clearInterval(t); };
  }, [ticker]);
  if (!q?.ok) return null;
  const color = q.up ? "#3fb950" : "#f85149";
  const arrow = q.up ? "▲" : "▼";
  return (
    <div style={{ border: "1px solid #e5e5e5", borderRadius: 8, padding: "6px 12px", textAlign: "right", background: "#fff", boxShadow: "0 2px 8px rgba(0,0,0,.08)" }}>
      <div style={{ fontSize: 12 }} className="dim">{q.symbol}</div>
      <div style={{ color, fontSize: 18 }}>
        {q.price?.toFixed(2)} {arrow} {q.change! > 0 ? "+" : ""}{q.change?.toFixed(2)} ({q.pct?.toFixed(2)}%)
      </div>
    </div>
  );
}

function TickerCombo({
  tickers, value, onPick,
}: {
  tickers: string[];
  value: string;
  onPick: (t: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(value);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => setText(value), [value]);
  useEffect(() => {
    function close(e: MouseEvent) {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const q = text.trim().toLowerCase();
  // Empty search shows every registered ticker (recent first, then popular);
  // filtered search caps at a scrollable page.
  const list = (q ? tickers.filter((t) => t.toLowerCase().includes(q)).slice(0, 30) : tickers).slice(0, 60);
  const showCustom = text.trim() && !tickers.some((t) => t.toLowerCase() === text.trim().toLowerCase());
  return (
    <div ref={box} style={{ position: "relative" }}>
      <input
        type="text"
        value={text}
        placeholder="Search or type a symbol…"
        onChange={(e) => { setText(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && text.trim()) { onPick(text.trim().toUpperCase()); setOpen(false); }
        }}
        style={{ width: "100%" }}
      />
      {open && (
        <div style={{
          position: "absolute", zIndex: 10, left: 0, right: 0, maxHeight: 240, overflowY: "auto",
          background: "#ffffff", border: "1px solid #e5e5e5", borderRadius: 8, marginTop: 2,
          boxShadow: "0 8px 24px rgba(0,0,0,.15)",
        }}>
          {showCustom && (
            <div
              onClick={() => { onPick(text.trim().toUpperCase()); setOpen(false); }}
              style={{ padding: "6px 10px", cursor: "pointer", color: "#ea580c", fontWeight: "bold" }}
            >
              Use “{text.trim().toUpperCase()}”
            </div>
          )}
          {list.map((t) => (
            <div
              key={t}
              onClick={() => { onPick(t); setOpen(false); }}
              style={{ padding: "6px 10px", cursor: "pointer" }}
              onMouseEnter={(e) => ((e.target as HTMLElement).style.background = "#fff3eb")}
              onMouseLeave={(e) => ((e.target as HTMLElement).style.background = "transparent")}
            >
              {t}
            </div>
          ))}
          {!list.length && !showCustom && <div className="dim" style={{ padding: "6px 10px" }}>No matches</div>}
        </div>
      )}
    </div>
  );
}

export default function Dashboard() {
  const router = useRouter();
  const [opts, setOpts] = useState<any>(null);
  const [error, setError] = useState("");
  const [step, setStep] = useState(0);
  const [ticker, setTicker] = useState("");
  const [tickerOk, setTickerOk] = useState(false);
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [language, setLanguage] = useState("English");
  const [analysts, setAnalysts] = useState<string[]>(["market", "social", "news"]);
  const [depth, setDepth] = useState(3);
  const [provider, setProvider] = useState("openai");
  const [quick, setQuick] = useState("");
  const [deep, setDeep] = useState("");
  const [models, setModels] = useState<{ quick: Model[]; deep: Model[] }>({ quick: [], deep: [] });
  const [modelsLoading, setModelsLoading] = useState(false);
  const [effort, setEffort] = useState("medium");
  const [tableModel, setTableModel] = useState("");
  const [catalog, setCatalog] = useState("");
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    api.options().then((o) => {
      setOpts(o);
      setCatalog(o.opencode?.current || o.opencode?.fullUrl || "");
    }).catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!provider) return;
    setModelsLoading(true);
    setModels({ quick: [], deep: [] });
    setQuick("");
    setDeep("");
    Promise.all([api.models(provider, "quick"), api.models(provider, "deep")])
      .then(([q, d]) => {
        setModels({ quick: q.models, deep: d.models });
        setQuick(q.models.find((m: Model) => m.id !== "custom")?.id || "");
        const deepDefault = d.models.find((m: Model) => m.id !== "custom")?.id || "";
        setDeep(deepDefault);
        setTableModel((v) => v || deepDefault);
      })
      .catch(() => {})
      .finally(() => setModelsLoading(false));
  }, [provider]);

  if (!opts) return <p className="dim">{error || "Loading options from the API…"}</p>;

  const providers: Provider[] = opts.providers;
  const showEffort = ["openai", "nvidia", "anthropic", "google"].includes(provider);
  const tickers: string[] = [...(opts.recentTickers || []), ...(opts.popularTickers || [])]
    .filter((t, i, a) => a.indexOf(t) === i);
  // Thinking step exists only for providers with a knob; otherwise skipped.
  const steps = showEffort ? STEPS : STEPS.filter((s) => s !== "Thinking");
  const current = steps[step];

  function toggleAnalyst(a: string) {
    setAnalysts((prev) => (prev.includes(a) ? prev.filter((x) => x !== a) : [...prev, a]));
  }

  function canNext(): string {
    if (current === "Ticker" && !tickerOk) return "Pick a ticker to continue";
    if (current === "Date" && !/^\d{4}-\d{2}-\d{2}$/.test(date)) return "Enter a valid YYYY-MM-DD date";
    if (current === "Analysts" && !analysts.length) return "Select at least one analyst";
    if (current === "Models" && modelsLoading) return "Waiting for models…";
    if (current === "Models" && provider === "azure" && (!quick.trim() || !deep.trim()))
      return "Enter both deployment names";
    if (current === "Models" && provider !== "azure" && (!quick || !deep)) return "Pick both models";
    if (current === "Tables" && !tableModel.trim()) return "Pick a table model";
    return "";
  }

  async function start() {
    setError("");
    setStarting(true);
    try {
      if (provider === "opencode" && catalog) {
        await api.saveKey("OPENCODE_BASE_URL", catalog);
      }
      const payload: Record<string, unknown> = {
        ticker,
        analysis_date: date,
        analysts,
        research_depth: depth,
        llm_provider: provider,
        shallow_thinker: quick,
        deep_thinker: deep,
        table_model: tableModel,
        output_language: language,
      };
      if (provider === "openai" || provider === "nvidia") {
        payload[provider === "openai" ? "openai_reasoning_effort" : "nvidia_reasoning_effort"] = effort;
      }
      if (provider === "anthropic") payload["anthropic_effort"] = effort;
      if (provider === "google") payload["google_thinking_level"] = effort === "medium" ? "high" : effort;
      const r = await api.startRun(payload);
      router.push(`/live?run=${r.id}`);
    } catch (e: any) {
      setError(e.data?.error || String(e.message || e));
      setStarting(false);
    }
  }

  const block = canNext();

  return (
    <div className="wizard">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
        <div>
          <h1>New analysis</h1>
          <div className="steps">
            {steps.map((s, i) => (
              <span key={s} className={`stepdot${i < step ? " done" : ""}${i === step ? " now" : ""}`}>
                {i + 1}. {s}
              </span>
            ))}
          </div>
        </div>
        {tickerOk && <QuoteWidget ticker={ticker} />}
      </div>
      {error && <p className="err">{error}</p>}

      {current === "Ticker" && (
        <div className="panel" style={{ maxWidth: 520 }}>
          <h2>Select ticker</h2>
          <TickerCombo
            tickers={tickers}
            value={ticker}
            onPick={(t) => { setTicker(t); setTickerOk(true); }}
          />
          <p className="dim">Recent + popular symbols, or type any valid symbol.</p>
        </div>
      )}

      {current === "Date" && (
        <div className="panel" style={{ maxWidth: 520 }}>
          <h2>Analysis date</h2>
          <label className="field">
            YYYY-MM-DD (defaults to today; weekends fall back to Friday data)
            <input type="text" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
        </div>
      )}

      {current === "Language" && (
        <div className="panel" style={{ maxWidth: 520 }}>
          <h2>Output language</h2>
          <label className="field">
            Report language
            <select value={language} onChange={(e) => setLanguage(e.target.value)}>
              {opts.languages.map((l: string) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </label>
        </div>
      )}

      {current === "Analysts" && (
        <div className="panel" style={{ maxWidth: 520 }}>
          <h2>Analyst team</h2>
          {opts.analysts.map(([label, value]: [string, string]) => (
            <label key={value} style={{ display: "block", marginBottom: 6 }}>
              <input type="checkbox" checked={analysts.includes(value)} onChange={() => toggleAnalyst(value)} /> {label}
            </label>
          ))}
        </div>
      )}

      {current === "Depth" && (
        <div className="panel" style={{ maxWidth: 520 }}>
          <h2>Research depth</h2>
          {opts.depths.map((d: { label: string; value: number; detail: string }) => (
            <label key={d.value} style={{ display: "block", marginBottom: 10 }}>
              <input type="radio" checked={depth === d.value} onChange={() => setDepth(d.value)} />{" "}
              <b>{d.label}</b>
              <div className="dim" style={{ marginLeft: 22 }}>{d.detail}</div>
            </label>
          ))}
        </div>
      )}

      {current === "Provider" && (
        <div className="panel" style={{ maxWidth: 520 }}>
          <h2>LLM provider</h2>
          <label className="field">
            Provider
            <select value={provider} onChange={(e) => setProvider(e.target.value)}>
              {providers.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.display}{p.keySet ? " (configured)" : ""}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {current === "Models" && (
        <div className="panel" style={{ maxWidth: 520 }}>
          <h2>Thinking models</h2>
          {provider === "opencode" && (
            <label className="field">
              Zen catalog
              <select value={catalog} onChange={(e) => setCatalog(e.target.value)}>
                <option value={opts.opencode?.fullUrl}>Full — zen/v1 (free + paid, recommended)</option>
                <option value={opts.opencode?.legacyUrl}>Legacy — zen/go/v1 (older catalog)</option>
              </select>
            </label>
          )}
          {modelsLoading && (
            <>
              <p className="dim">Loading {provider} models…</p>
              <div className="shimmer" style={{ height: 34, marginBottom: 10 }} />
              <div className="shimmer" style={{ height: 34 }} />
            </>
          )}
          {!modelsLoading && provider === "azure" && (
            <>
              <label className="field">
                Quick-thinking deployment name
                <input type="text" placeholder="e.g. gpt-5-mini-deploy" value={quick} onChange={(e) => setQuick(e.target.value)} />
              </label>
              <label className="field">
                Deep-thinking deployment name
                <input type="text" placeholder="e.g. gpt-5-deploy" value={deep} onChange={(e) => setDeep(e.target.value)} />
              </label>
            </>
          )}
          {!modelsLoading && provider !== "azure" && (
            <>
              <label className="field">
                Quick-thinking model
                <select value={quick} onChange={(e) => setQuick(e.target.value)}>
                  {models.quick.map((m) => (
                    <option key={m.id} value={m.id}>{m.name}</option>
                  ))}
                </select>
              </label>
              <label className="field">
                Deep-thinking model
                <select value={deep} onChange={(e) => setDeep(e.target.value)}>
                  {models.deep.map((m) => (
                    <option key={m.id} value={m.id}>{m.name}</option>
                  ))}
                </select>
              </label>
            </>
          )}
        </div>
      )}

      {current === "Thinking" && (
        <div className="panel" style={{ maxWidth: 520 }}>
          <h2>Reasoning effort</h2>
          <label className="field">
            Effort level
            <select value={effort} onChange={(e) => setEffort(e.target.value)}>
              <option value="low">Low (faster)</option>
              <option value="medium">Medium (default)</option>
              <option value="high">High (more thorough)</option>
            </select>
          </label>
        </div>
      )}

      {current === "Tables" && (
        <div className="panel" style={{ maxWidth: 520 }}>
          <h2>Tables model</h2>
          <p className="dim">Extracts clean tables from each report section at the end of the run.</p>
          {provider === "azure" ? (
            <label className="field">
              Table deployment name
              <input type="text" placeholder="e.g. gpt-5-deploy" value={tableModel} onChange={(e) => setTableModel(e.target.value)} />
            </label>
          ) : (
            <label className="field">
              Table model
              <select value={tableModel} onChange={(e) => setTableModel(e.target.value)} disabled={modelsLoading}>
                {modelsLoading && <option>Loading…</option>}
                {models.deep.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>
            </label>
          )}
        </div>
      )}

      {current === "Confirm" && (
        <div className="panel" style={{ maxWidth: 520 }}>
          <h2>Confirm</h2>
          <table className="grid"><tbody>
            <tr><td>Ticker</td><td>{ticker}</td></tr>
            <tr><td>Date</td><td>{date}</td></tr>
            <tr><td>Language</td><td>{language}</td></tr>
            <tr><td>Analysts</td><td>{analysts.join(", ")}</td></tr>
            <tr><td>Depth</td><td>{opts.depths.find((d: any) => d.value === depth)?.label}</td></tr>
            <tr><td>Provider</td><td>{providers.find((p) => p.key === provider)?.display}</td></tr>
            <tr><td>Quick</td><td>{quick}</td></tr>
            <tr><td>Deep</td><td>{deep}</td></tr>
            <tr><td>Tables</td><td>{tableModel}</td></tr>
            {showEffort && <tr><td>Effort</td><td>{effort}</td></tr>}
          </tbody></table>
        </div>
      )}

      <div style={{ marginTop: 12 }}>
        {step > 0 && <button className="ghost" onClick={() => setStep(step - 1)}>← Back</button>}{" "}
        {current !== "Confirm" ? (
          <button className="primary" disabled={!!block} onClick={() => setStep(step + 1)}>Next →</button>
        ) : (
          <button className="primary" disabled={starting} onClick={start}>
            {starting ? "Starting…" : "Start analysis"}
          </button>
        )}
        {block && current !== "Confirm" && <span className="warn" style={{ marginLeft: 12 }}>{block}</span>}
      </div>
    </div>
  );
}
