# PR32: DeepSeek/OpenAI-compatible multi-agent research

PR32 adds an optional provider-neutral LLM research layer over normalized
records. The legacy TradingAgents graph and deterministic workflow stay intact.

## Server-side configuration

“DeepSeek V4 Pro” is not hard-coded as a model identifier. Configure the exact
model ID supplied by the account:

```powershell
$env:TRADINGAGENTS_RESEARCH_LLM_PROVIDER = "deepseek"
$env:TRADINGAGENTS_RESEARCH_LLM_MODEL = "<exact model id from DeepSeek>"
$env:DEEPSEEK_API_KEY = "<server-side key>"
```

For compatibility with the local workstation, `Deepseek Token-TA` is accepted as a legacy server-side alias for `DEEPSEEK_API_KEY`. When either key is present and provider/model are omitted, the research adapter selects `deepseek` and `deepseek-v4-pro`.

The existing DeepSeek adapter uses the OpenAI-compatible endpoint
`https://api.deepseek.com`. `TRADINGAGENTS_RESEARCH_LLM_BASE_URL` can override
the endpoint. The cockpit receives readiness, provider, and model only; keys
are never serialized into HTML, requests, jobs, or responses.

## Orchestration and safety

Four specialists (fundamentals, market, game/news/approvals, valuation) feed a
single-round Bull/Bear debate and Research Manager synthesis. Successful stages
are `AgentOutputEnvelope` records with provider, model, prompt version,
evidence, latency, and usage when available. Out-of-context citations are
rejected; a failed role degrades explicitly while remaining roles continue.

The manager emits an `InvestmentThesis`, never a `TradeSignal`. LLM output
cannot approve sizing or bypass deterministic risk review. Select **多智能体研究**
in the cockpit; missing configuration fails cleanly before model calls.


## Deterministic research brief

Before any LLM stage, the workflow renders a read-only deterministic brief from the same normalized price, fundamental, and news records. It contains deterministic analyst outputs, the deterministic thesis, and the preliminary Markdown report. Multi-agent prompt v2 receives this brief with the raw normalized records while retaining the evidence whitelist. The report is capped at 24,000 characters; audit metadata records its included length, truncation status, and deterministic output count.

## DeepSeek output resilience and technical features

Prompt v3 normalizes common OpenAI-compatible structured-output variations before enforcing the stable contracts: numeric or percentage confidence values, scalar list fields, oversized text, and excessive bullet counts. Evidence IDs remain strictly restricted to the normalized evidence whitelist.

The market analyst receives deterministic features computed from normalized OHLCV bars rather than being asked to perform arithmetic: 5/20/60-day returns, 5/20/60-day moving averages, close-to-SMA20 distance, 20-day annualized volatility, 60-day maximum drawdown, RSI(14), 5-day versus 20-day volume ratio, and a deterministic trend state. Audit metadata records the bar and feature counts.
## DeepSeek JSON-mode protocol

Prompt v4 overrides structured output to `json_mode` inside the research adapter for DeepSeek only. DeepSeek V4 rejects forced `tool_choice`, so function-calling could legitimately return a normal answer without invoking the schema tool. JSON mode forces a content JSON object and the compact Pydantic schema is included in the prompt. This does not change the legacy TradingAgents client behavior or other providers.
## Game-company research context

Prompt v5 adds point-in-time game-company records to the normalized research context: curated live and pipeline products, dated/ongoing catalysts, exact legal-entity NPPA approval matches, and the explainable game opportunity radar. Every curated source and exact approval is converted to the standard evidence whitelist. Review-required brand matches and facts unavailable by the run's as-of date are excluded. The opportunity score is labeled as screening context only and cannot become a trade signal.

## P0 production safeguards

Prompt v6 uses forward-adjusted A-share closes for all deterministic technical features. The Tushare adapter merges `daily` with `adj_factor` by trade date and normalizes each close to the latest available factor. If the adjustment endpoint is unavailable, raw bars remain usable but are explicitly labeled `raw_unadjusted`; reports and the cockpit show adjustment coverage instead of silently treating raw prices as adjusted.

Every model call is bounded and the research worker is released even if an SDK call never returns. Configure the server-side budgets when needed:

```powershell
$env:TRADINGAGENTS_RESEARCH_LLM_CALL_TIMEOUT = "90"
$env:TRADINGAGENTS_RESEARCH_LLM_MAX_RETRIES = "1"
$env:TRADINGAGENTS_RESEARCH_LLM_RETRY_BACKOFF = "0.5"
$env:TRADINGAGENTS_RESEARCH_LLM_TOTAL_TIMEOUT = "480"
```

Only transient connection, rate-limit, and gateway errors are retried. A hard call timeout opens a circuit for the remaining stages in that run, producing explicit degraded envelopes without issuing duplicate calls. API keys are never included in error details or audit records.

Archived bundles now include a run-level audit with the selected mode, data provider, provider/model, sanitized endpoint identifier, prompt and technical-feature versions, normalized-input SHA-256 fingerprint, price-adjustment coverage, successful/degraded stage counts, latency, and usage totals when supplied by the provider.
