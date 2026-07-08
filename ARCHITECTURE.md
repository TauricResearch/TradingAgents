# TradingAgents Pro — Architecture

Living document. Updated at every phase checkpoint. The full Phase 1
HLD/LLD, per-agent walkthroughs, diagrams, and ranked improvement
recommendations live under `docs/analysis/` (authored in Phase 1; being
restored after an iCloud incident — see DECISIONS.md ADR-0013); this file
tracks how the Pro extension layers onto the base framework.

## Base framework (as found, v0.3.1)

- `tradingagents/agents/` — analyst, researcher, risk-debator, manager, and
  trader node factories; `agents/schemas.py` already provides Pydantic
  structured outputs for the three decision-making agents.
- `tradingagents/dataflows/` — vendor-routed data layer (yfinance,
  Alpha Vantage, FRED, Reddit, StockTwits, Polymarket) with symbol
  normalization that already maps `XAUUSD`→`GC=F` and `BTC-USD` crypto pairs.
- `tradingagents/graph/` — LangGraph assembly: setup, conditional logic,
  propagation, reflection, signal processing, checkpointing.
- `tradingagents/llm_clients/` — multi-provider LLM factory with a model
  catalog and capability flags.
- Config is a plain dict (`default_config.py::DEFAULT_CONFIG`) with
  env-var overrides; ~60-file pytest suite in `tests/`.

## Pro extension layers

### Phase 0 — `tradingagents/contracts/`

Typed, frozen Pydantic v2 models that every later phase communicates
through:

| Module | Contracts | Purpose |
|---|---|---|
| `base.py` | `ContractModel`, `SCHEMA_VERSION`, `utc_now` | Immutability, `extra="forbid"`, UTC-only timestamps |
| `enums.py` | `AssetClass`, `TradingMode`, `Direction`, `TradeAction`, `Timeframe`, `MarketRegime`, `TradingSession`, `AgentTeam`, `SourceType` | Shared vocabulary |
| `evidence.py` | `AgentEvidence`, `DataRef`, `SourceAttribution` | Every agent claim carries direction, confidence, timeframe, data refs, and attributed sources; refs must resolve to declared sources |
| `snapshot.py` | `MarketSnapshot`, `OHLCVBar`, `SpotQuote`, `IndicatorReading`, `MetricReading` | Deterministic input package handed to LLM agents; OHLC and quote consistency validated |
| `recommendation.py` | `TradeRecommendation`, `TakeProfitLevel`, `PositionSize`, `VoteBreakdown`, `AgentVote`, `HistoricalAnalog` | Pipeline output; side-aware level geometry validated; `risk_reward` derived in code |
| `config.py` | `ProConfig`, `RiskLimits`, `ModelRouting` | Paper-by-default; live mode structurally requires human approval; `to_legacy_config()` bridges to `DEFAULT_CONFIG` |

Data flow the contracts encode:

```
deterministic feeds/indicators ──> MarketSnapshot ──> LLM agents ──> AgentEvidence[]
        (typed Python code)          (frozen)            (interpret only)
                                                              │
                       debate → critique → reflection → judge → risk → PM
                                                              │
                                                    TradeRecommendation
                                            (computed R:R, votes, counterargs)
```

### Phase 2 — `tradingagents/pro/ingestion/`

Typed feed adapters behind three small protocols (`BarsFeed`, `QuoteFeed`,
`MetricsFeed`), each with an injectable HTTP transport or loader so tests
and backtests run offline. `SnapshotBuilder` composes them into a frozen
`MarketSnapshot`; feed failures land in `missing_feeds` (ADR-0010).

| Module | Provides |
|---|---|
| `base.py` | Protocols + `RequestsTransport` (429/418 → typed rate-limit error) |
| `binance.py` | BTC spot klines/quote/depth-imbalance + perp funding/OI (keyless) |
| `gold_feeds.py` | GC=F daily bars via the base cached loader; derived silver corr, DXY, US10Y |
| `fred_macro.py` | Typed FRED readings (CPI/PPI YoY server-side transforms, NFP, rates) |
| `onchain.py` | CoinMetrics Community (MVRV…), blockchain.com miner stats, Fear & Greed |
| `derived.py` | Pure math: correlations, order-book imbalance |
| `indicators.py` | stockstats-backed engine → `IndicatorReading` (explicit warm-up windows) |
| `sessions.py` | Deterministic XAU session classification (ADR-0012) |
| `builder.py` | `SnapshotBuilder` + `build_gold_pipeline` / `build_bitcoin_pipeline` |

Source selection and paid-feed status: [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

### Phase 3 — `tradingagents/pro/agents/` + `tradingagents/pro/analytics/`

One `EvidenceAgent` runtime, 59 config-driven specs (ADR-0014):

| Module | Provides |
|---|---|
| `agents/specs.py` | `AgentSpec`: persona + snapshot selectors + `primary` inputs |
| `agents/rendering.py` | Snapshot slice → prompt block + code-attached DataRefs/sources (ADR-0015) |
| `agents/base.py` | `EvidenceAgent` (structured output → `AgentEvidence`, abstains on missing data), `build_team`, `run_agents` |
| `agents/roster.py` | 59 specs: 24 technical, 11 macro, 7 news/sentiment, 8 quant, 9 risk |
| `agents/metrics.py` | `compute_quant_metrics` / `compute_risk_metrics` → named `MetricReading`s (ADR-0016) |
| `agents/prompts/*.md` | Versioned team templates + executive charters (Phase 4 nodes) |
| `analytics/features.py` | Realized vol, trend slope/R², z-score, rule-based regime classifier |
| `analytics/risk.py` | Fixed-risk sizing, Kelly (capped), historical VaR/CVaR, ATR stops/targets |

Evidence flow: `MarketSnapshot` (+ engine extras) → rendering → LLM
(claim/direction/confidence only) → `AgentEvidence` with attribution the
agent was actually shown. Known input gaps (VWAP/ADX/Supertrend, X/Twitter)
abstain by design and are noted per spec.

### Phase 4 — `tradingagents/pro/pipeline/`

The debate pipeline as a LangGraph `StateGraph` (ADR-0018/0019):

```
gather ──> technical bull ⇄ bear ──> macro bull ⇄ bear ──> sentiment
  │            (bounded rounds)          (bounded rounds)        │
  │                                                       risk gate (code)
  │ (no evidence)                                                │
  ▼                                                           critic
rejected ◀──── any gate ──────────── reflection ──> judge ──> portfolio mgr
  │                                                              │
  ▼                                                          execution
 END ◀────────────────────────────────────────── (paper OK; live refused)
```

| Module | Provides |
|---|---|
| `schemas.py` | Structured outputs: `DebateTurn`, `CriticReport`, `ReflectionNote`, `JudgeVerdict` |
| `votes.py` | Deterministic vote accounting + confidence-weighted consensus (ties → HOLD) |
| `gates.py` | `risk_gate`: VaR/CVaR vs limits, level availability; fails closed |
| `nodes.py` | All node implementations; PM builds the `TradeRecommendation` from engine numbers only |
| `graph.py` | Graph assembly, `run_pipeline` / `stream_pipeline`, `PipelineState` |
| `prompts/*.md` | Versioned debate/sentiment/critic/reflection/judge templates |

Phase 6 enhancements (ADR-0022): `prepare` fans out into five parallel
team nodes merged by a state reducer (optional intra-team thread pool);
empty-evidence debate stages are skipped dynamically; a `human_approval`
interrupt node gates live execution (live builds require a checkpointer);
structured calls retry with a bounded budget; `stream_pipeline` yields
per-node updates.

### Phase 5 — `tradingagents/pro/memory/`

Typed memory with semantic retrieval (ADR-0020/0021):

| Module | Provides |
|---|---|
| `records.py` | `MemoryRecord` + kinds: trade, outcome, regime, reflection, strategy, mistake, winning_pattern |
| `store.py` | Append-only JSONL audit trail (crash-safe appends, corrupt-line tolerant) |
| `embedding.py` | Injectable `EmbeddingFn`; deterministic hashing embedder default |
| `index.py` / `qdrant_index.py` | `VectorIndex` protocol: in-memory cosine default, optional Qdrant (`pip install "tradingagents[qdrant]"`) |
| `graph.py` | Weighted knowledge graph + seeded gold/BTC market relationships |
| `memory.py` | `ProMemory` facade: record/close trades (derives lessons), analogs, lessons, win-stats, relations block |

Pipeline integration: gather injects historical analogs + lessons +
relations into the debate context and win statistics into the risk engine
(waking the Kelly agent); reflection notes and accepted trades are written
back; the PM attaches analogs to `TradeRecommendation.historical_analogs`.
Rejected runs write nothing.

### Phase 7 — `tradingagents/pro/backtest/`

Backtests run the identical pipeline graph (ADR-0023/0024):

| Module | Provides |
|---|---|
| `data.py` | `BarReplay`: per-step snapshots, lookahead-safe by construction |
| `costs.py` | Side-aware slippage, commission, liquidity participation cap |
| `broker.py` | `SimBroker`: stop-before-TP intrabar policy, TP-ladder partials, mark-to-market equity |
| `engine.py` | `BacktestEngine`: decide on close, fill next open, equity-aware sizing, `memory.close_trade` on exits |
| `metrics.py` | Sharpe, Sortino, max drawdown, win rate, profit factor, expectancy (Phase 8 objectives) |
| `llm_cache.py` | `CachingLLM` record/replay/auto with JSONL persistence (fidelity: ADR-0023) |
| `walkforward.py` | Rolling windows; stability evaluation until Phase 8 adds fitted params |
| `montecarlo.py` | Seeded trade-P&L bootstrap: final-equity/drawdown percentiles, P(loss) |

### Later phases (planned)
- Phases 5–11: memory, graph enhancements, backtesting, RL, execution,
  dashboard, production engineering.

## Compatibility stance

The Pro layer is additive. `tradingagents/contracts/` and
`tradingagents/pro/` import nothing from the framework at module import
time (the legacy-config bridge and OHLCV loader import lazily), so the
original stock workflow and its tests are untouched.
