import { useEffect, useMemo, useState } from "react";

type JobStatus = "queued" | "running" | "completed" | "failed";

type ProviderOption = {
  id: string;
  base_url: string;
  models: string[];
};

type OptionsResponse = {
  providers: ProviderOption[];
  analysts: string[];
  research_depths: number[];
};

type AnalysisJob = {
  id: string;
  status: JobStatus;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  request: {
    ticker: string;
    analysis_date: string;
    analysts: string[];
    research_depth: number;
    llm_provider: string;
    quick_think_llm?: string;
    deep_think_llm?: string;
    backend_url?: string;
    google_thinking_level?: string;
    openai_reasoning_effort?: string;
  };
  result?: {
    ticker: string;
    analysis_date: string;
    decision: string;
    final_trade_decision: string;
    investment_plan: string;
    reports: Record<string, string | null>;
  };
  error?: string;
};

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function App() {
  const [options, setOptions] = useState<OptionsResponse | null>(null);
  const [loadingOptions, setLoadingOptions] = useState(true);
  const [ticker, setTicker] = useState("SPY");
  const [analysisDate, setAnalysisDate] = useState(todayIso());
  const [researchDepth, setResearchDepth] = useState(1);
  const [provider, setProvider] = useState("google");
  const [selectedAnalysts, setSelectedAnalysts] = useState<string[]>([
    "market",
    "social",
    "news",
    "fundamentals",
  ]);
  const [quickThink, setQuickThink] = useState("");
  const [deepThink, setDeepThink] = useState("");
  const [googleThinkingLevel, setGoogleThinkingLevel] = useState("high");
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const providers = options?.providers ?? [];
  const providerMeta = useMemo(
    () => providers.find((item) => item.id === provider),
    [provider, providers]
  );

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const response = await fetch(`${API_BASE}/api/options`);
        const data: OptionsResponse = await response.json();
        if (!mounted) {
          return;
        }
        setOptions(data);
        const google = data.providers.find((item) => item.id === "google");
        if (google && google.models.length > 0) {
          setQuickThink(google.models[0]);
          setDeepThink(google.models[0]);
        }
      } finally {
        if (mounted) {
          setLoadingOptions(false);
        }
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!providerMeta?.models?.length) {
      return;
    }
    if (!providerMeta.models.includes(quickThink)) {
      setQuickThink(providerMeta.models[0]);
    }
    if (!providerMeta.models.includes(deepThink)) {
      setDeepThink(providerMeta.models[0]);
    }
  }, [providerMeta, quickThink, deepThink]);

  useEffect(() => {
    if (!job || (job.status !== "queued" && job.status !== "running")) {
      return;
    }
    const timer = setTimeout(async () => {
      const response = await fetch(`${API_BASE}/api/analysis/jobs/${job.id}`);
      const updated = (await response.json()) as AnalysisJob;
      setJob(updated);
    }, 2500);
    return () => clearTimeout(timer);
  }, [job]);

  const toggleAnalyst = (value: string) => {
    setSelectedAnalysts((current) => {
      if (current.includes(value)) {
        const next = current.filter((item) => item !== value);
        return next.length ? next : current;
      }
      return [...current, value];
    });
  };

  const submitJob = async () => {
    setIsSubmitting(true);
    setJob(null);
    try {
      const payload = {
        ticker,
        analysis_date: analysisDate,
        analysts: selectedAnalysts,
        research_depth: researchDepth,
        llm_provider: provider,
        backend_url: providerMeta?.base_url,
        quick_think_llm: quickThink,
        deep_think_llm: deepThink,
        google_thinking_level: provider === "google" ? googleThinkingLevel : null,
      };
      const response = await fetch(`${API_BASE}/api/analysis/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error(`Request failed (${response.status})`);
      }
      const created = (await response.json()) as AnalysisJob;
      setJob(created);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setJob({
        id: "n/a",
        status: "failed",
        created_at: new Date().toISOString(),
        request: {
          ticker,
          analysis_date: analysisDate,
          analysts: selectedAnalysts,
          research_depth: researchDepth,
          llm_provider: provider,
        },
        error: message,
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="shell">
      <header className="hero">
        <div>
          <h1>TradingAgents Web Console</h1>
          <p>
            Keep the current backend logic intact and orchestrate runs through HTTP APIs.
            Submit a job, monitor state transitions, and inspect the final decision package.
          </p>
        </div>
        <span className="badge">React + FastAPI</span>
      </header>

      <section className="grid">
        <aside className="panel stack">
          <h2>Run Setup</h2>

          <label>
            Ticker
            <input value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} />
          </label>

          <label>
            Analysis Date
            <input
              type="date"
              value={analysisDate}
              onChange={(e) => setAnalysisDate(e.target.value)}
            />
          </label>

          <label>
            Provider
            <select value={provider} onChange={(e) => setProvider(e.target.value)}>
              {providers.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.id}
                </option>
              ))}
            </select>
          </label>

          <label>
            Quick-Thinking Model
            <select value={quickThink} onChange={(e) => setQuickThink(e.target.value)}>
              {providerMeta?.models?.map((model) => (
                <option value={model} key={model}>
                  {model}
                </option>
              ))}
            </select>
          </label>

          <label>
            Deep-Thinking Model
            <select value={deepThink} onChange={(e) => setDeepThink(e.target.value)}>
              {providerMeta?.models?.map((model) => (
                <option value={model} key={model}>
                  {model}
                </option>
              ))}
            </select>
          </label>

          {provider === "google" && (
            <label>
              Gemini Thinking Mode
              <select
                value={googleThinkingLevel}
                onChange={(e) => setGoogleThinkingLevel(e.target.value)}
              >
                <option value="high">high</option>
                <option value="minimal">minimal</option>
              </select>
            </label>
          )}

          <label>
            Research Depth
            <div className="depth">
              {[1, 3, 5].map((depth) => (
                <button
                  key={depth}
                  type="button"
                  className={researchDepth === depth ? "active" : ""}
                  onClick={() => setResearchDepth(depth)}
                >
                  {depth === 1 ? "Shallow" : depth === 3 ? "Medium" : "Deep"}
                </button>
              ))}
            </div>
          </label>

          <div className="stack">
            <span className="mono">Analyst Team</span>
            <div className="checks">
              {(options?.analysts || []).map((analyst) => (
                <label key={analyst}>
                  <input
                    type="checkbox"
                    checked={selectedAnalysts.includes(analyst)}
                    onChange={() => toggleAnalyst(analyst)}
                  />
                  {analyst}
                </label>
              ))}
            </div>
          </div>

          <button className="run" type="button" onClick={submitJob} disabled={isSubmitting || loadingOptions}>
            {isSubmitting ? "Submitting..." : "Start Analysis Job"}
          </button>
        </aside>

        <article className="panel">
          <h3>Execution</h3>
          <p className="mono">API: {API_BASE}</p>

          {job ? (
            <>
              <div className="status">
                <span className={`dot ${job.status}`} />
                {job.status}
              </div>
              <p className="mono">Job ID: {job.id}</p>
              <p>
                {job.request.ticker} on {job.request.analysis_date} with {job.request.llm_provider}
              </p>

              {job.status === "failed" && (
                <div className="card error pre">{job.error || "Job failed"}</div>
              )}

              {job.result && (
                <div className="result">
                  <div className="card">
                    <h4>Decision</h4>
                    <div className="pre">{job.result.decision}</div>
                  </div>
                  <div className="card">
                    <h4>Final Trade Decision</h4>
                    <div className="pre">{String(job.result.final_trade_decision || "")}</div>
                  </div>
                  <div className="card">
                    <h4>Investment Plan</h4>
                    <div className="pre">{String(job.result.investment_plan || "")}</div>
                  </div>
                  {Object.entries(job.result.reports || {}).map(([key, value]) => (
                    <div className="card" key={key}>
                      <h4>{key}</h4>
                      <div className="pre">{String(value || "")}</div>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p>Submit a run to see live job status and result artifacts here.</p>
          )}
        </article>
      </section>
    </main>
  );
}
