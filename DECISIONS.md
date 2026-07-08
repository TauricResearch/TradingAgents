# TradingAgents Pro — Decision Log (ADR style)

## ADR-0001: Contracts live at `tradingagents/contracts/`, not top-level `contracts/`

**Status:** accepted (Phase 0) · **Date:** 2026-07-07

The spec asked for a `contracts/` package. A top-level package would need its
own packaging entry and would squat a generic name on PyPI-style installs.
Placing it at `tradingagents/contracts/` keeps it inside the existing
`tradingagents*` setuptools include, imports as `tradingagents.contracts`,
and keeps the repo installable exactly as before.

## ADR-0002: Pydantic v2, frozen models, `extra="forbid"`, UTC-only timestamps

**Status:** accepted (Phase 0)

The base repo already depends on Pydantic v2 (via langchain-core) and uses it
for structured agent output, so no new dependency. Contracts are immutable
snapshots of what an agent/feed said at a point in time; freezing them
prevents any pipeline node from rewriting history. Unknown fields fail
loudly so schema drift between agents and consumers is caught at the
boundary. Naive datetimes are rejected globally — ambiguous timestamps in a
trading system are lookahead bugs.

## ADR-0003: Counterarguments reuse `AgentEvidence`

**Status:** accepted (Phase 0)

`TradeRecommendation.counterarguments` is `list[AgentEvidence]` rather than a
new `Counterargument` model. The losing side of a debate is still evidence —
it has a claim, direction, confidence, and sources — and reusing the type
means the same validation (no unsourced claims) applies to both sides.
Consolidation over duplication.

## ADR-0004: `risk_reward` is a computed field, never an input

**Status:** accepted (Phase 0)

Constraint 2 (deterministic math). The R:R ratio is derived in code from
entry, stop, and the size-weighted take-profit ladder, and the model always
overwrites the field with the recomputed value. A supplied value that
contradicts the levels is a validation error, so an LLM cannot assert a
ratio its own levels don't support. (A matching value is accepted so
serialized payloads re-validate — a pure Pydantic `computed_field` breaks
JSON round-trips under `extra="forbid"`.)

## ADR-0005: Live-mode safety is structural

**Status:** accepted (Phase 0)

`ProConfig(mode=live)` raises unless `live_trading_enabled=True`, and raises
if `require_human_approval=False`. There is no constructible configuration
for unattended live trading (Constraint 5). Kill switch and circuit-breaker
parameters live in `RiskLimits` now so Phase 9 wires against an existing
contract instead of inventing one.

## ADR-0006: Macro and on-chain metrics share one `MetricReading` shape

**Status:** accepted (Phase 0)

DXY, US10Y, CPI YoY, MVRV, SOPR, and exchange reserves are all
`(name, value, unit, as_of, source)` observations. One generic model instead
of per-domain clones; Phase 2 adapters populate `MarketSnapshot.macro` and
`.onchain` with the same type.

## ADR-0007: `ModelRouting` defaults mirror `DEFAULT_CONFIG`

**Status:** accepted (Phase 0)

A `ProConfig` with no overrides produces (via `to_legacy_config()`) exactly
the base framework's configuration, so Pro runs and stock runs share one
source of truth for model defaults and backward compatibility is testable.

## ADR-0008: Free-first data sourcing; paid feeds gated on sign-off

**Status:** accepted (Phase 2)

All Phase 2 adapters use free sources (Binance public, yfinance, FRED,
CoinMetrics Community, blockchain.com, alternative.me). Paid feeds
(Glassnode/CryptoQuant, Coinglass, whale tracking, tick-level gold data)
are catalogued in `docs/DATA_SOURCES.md` with costs and only become
adapters after explicit approval. Rationale: the free set already covers
every input Phase 3 agents need to be built and tested; paid data should
be justified by backtest evidence, not bought up front.

## ADR-0009: Ingestion adapters are typed classes, not `VENDOR_METHODS` entries

**Status:** accepted (Phase 2)

The base framework's vendor router returns markdown strings for LLM
prompts. The Pro snapshot layer needs typed data (`OHLCVBar`,
`MetricReading`) for deterministic math, so adapters implement small
protocols (`BarsFeed`/`QuoteFeed`/`MetricsFeed`) with injectable
transports and reuse the dataflows error taxonomy. The LLM-facing bridge
(a tool that renders a `MarketSnapshot` for prompts) arrives with the
Phase 3 agents. `VENDOR_METHODS` remains untouched for the stock workflow.

## ADR-0010: Feed failures degrade to `missing_feeds`, bars do not

**Status:** accepted (Phase 2)

`SnapshotBuilder` absorbs metric/quote feed failures into
`MarketSnapshot.missing_feeds` (agents must treat those as unknown), but a
bars failure raises: without price data there is no meaningful snapshot,
and fabricating one would violate the evidence discipline.

## ADR-0011: CoinMetrics Community for on-chain valuation; skip stockstats partial means

**Status:** accepted (Phase 2)

CoinMetrics Community (free, keyless) provides MVRV/realized cap/active
addresses — the highest-value on-chain metrics — so no paid provider is
needed yet (SOPR/reserves are the gap; see ADR-0008). Separately, the
indicator engine enforces explicit per-indicator warm-up windows
(`min_bars`) because stockstats silently computes partial means
(`min_periods=1`) on short histories, which would hand agents a
plausible-looking but wrong SMA-200.

## ADR-0012: Gold session boundaries are fixed UTC approximations

**Status:** accepted (Phase 2)

ASIA 22:00–07:00, LONDON 07:00–12:00, NEW_YORK 12:00–21:00 (includes the
London/NY overlap), CLOSED 21:00–22:00 + weekend (Fri 21:00 → Sun 22:00),
all UTC with no DST shifting. Deliberately simple and deterministic;
session-sensitive strategies can refine later without changing the
contract enum.

## ADR-0013: Working repo relocated to `~/dev/TradingAgents`

**Status:** accepted (Phase 2) · **Date:** 2026-07-07

The original working copy at `~/Documents/TradingAgents` sits in an
iCloud-synced folder. Creating the project venv there triggered a sync
storm that left file vnodes wedged in uninterruptible kernel waits —
builds, lint, and tests froze. The repo was re-cloned to
`~/dev/TradingAgents` (same base commit `01477f9`, branch
`pro/phase-0-contracts`), all Pro files restored, and the venv moved to
`~/.venvs/tradingagents-pro`. The `docs/analysis/` Phase 1 documents
remain in the Documents copy and will be recovered once iCloud settles
(or regenerated). Rule going forward: no venvs or large artifact trees
inside iCloud-synced paths.

## ADR-0014: 59 evidence agents are one class plus configuration

**Status:** accepted (Phase 3)

The appendix roster (24 technical + 11 macro + 7 news/sentiment + 8 quant +
9 risk) is implemented as `AgentSpec` records driving a single
`EvidenceAgent` runtime, with one prompt template per team. Personas,
timeframes, and data selectors are data, not code. Executive roles are not
evidence agents — their charters live in `prompts/executive_team.md` and
they become Phase 4 graph nodes.

## ADR-0015: Attribution is attached by code; agents without inputs abstain

**Status:** accepted (Phase 3)

The same rendering pass that builds an agent's data block produces its
`data_refs` and `sources` — the LLM only returns claim/direction/confidence
via structured output. An agent therefore cannot cite data it wasn't shown.
If nothing it selected is available (or none of its declared `primary`
inputs rendered, e.g. Kelly without win statistics), the agent returns
None — abstention, recorded as absence, never a fabricated opinion. Specs
for inputs that don't exist yet (VWAP/ADX/Supertrend indicators, X/Twitter
feed) stay in the roster with a documented gap note and abstain at runtime.

## ADR-0016: Risk and quant numbers come from `pro/analytics`, passed as extra metrics

**Status:** accepted (Phase 3)

`tradingagents/pro/analytics/` computes sizing, Kelly, historical VaR/CVaR,
ATR stops/targets, realized volatility, trend fit, z-scores, and a
rule-based regime classifier. `compute_quant_metrics` / `compute_risk_metrics`
package them as named `MetricReading`s handed to agents via the
`extra_metrics` channel — the snapshot contract stays a market-data record,
and the pipeline (Phase 4) recomputes risk per proposal without rebuilding
snapshots. Default position-size cap is 100% of equity (no implicit leverage).

## ADR-0017: `NewsItem` added to `MarketSnapshot` (schema 0.2)

**Status:** accepted (Phase 3)

News/sentiment agents need per-item provenance for per-claim attribution
(Constraint 3), so `MarketSnapshot.news: list[NewsItem]` was added —
backward compatible (defaults to empty; 0.1 payloads still validate).
Typed news-feed adapters (Reddit, RSS wires, economic calendar) are the
flagged Phase 3.1 follow-up; until then callers inject items.

## ADR-0018: Pipeline gates are deterministic; LLM stages argue, code decides

**Status:** accepted (Phase 4)

The debate pipeline's rejection points are code: the risk gate compares
engine-computed VaR/CVaR against `RiskLimits` and fails closed when it has
nothing to check; the PM stage rejects a ruling with no supporting
evidence, recomputes side-correct levels, and lets the TradeRecommendation
contract's geometry validation act as the final gate; a critic-model
outage is a *fail*, not a pass-through. Every gate routes to one terminal
``rejected`` node and a rejected run ends with no recommendation
(Constraint 4). Votes are tallied in code (evidence direction × confidence,
ties resolve to HOLD); the judge sees the tally and must justify ruling
against it, but cannot alter it.

## ADR-0019: Execution node refuses live routing until Phase 6

**Status:** accepted (Phase 4)

Even a fully-approved recommendation cannot reach live execution: the
execution node accepts paper/backtest modes and unconditionally refuses
live mode with an explicit reason, because the human-approval graph node
(Constraint 5) is Phase 6 scope. The research artifact (recommendation)
survives; only routing is refused. This makes "live before human approval
exists" structurally impossible rather than configurationally unlikely.

## ADR-0020: Qdrant over Milvus; dependency-free default index

**Status:** accepted (Phase 5)

Qdrant is the chosen vector DB when one is needed: it runs embedded/local
(no service for dev), is a single binary in prod, and has first-class
payload filtering. Milvus's distributed architecture (etcd + object store
+ workers) is unjustified at this project's memory scale. But neither is
required to *run*: the default is an exact-cosine in-memory index over the
JSONL store (thousands of records is nothing), with `QdrantIndex` behind
the optional `qdrant` extra implementing the same `VectorIndex` protocol.
Embeddings are likewise injectable — the default deterministic hashing
embedder keeps tests/backtests offline; production plugs a real embedding
callable without touching other code. The knowledge graph is a weighted
adjacency list, not a graph database, for the same reason.

## ADR-0021: Append-only memory with derived lesson records

**Status:** accepted (Phase 5)

Pro memory is a separate JSONL audit trail (the base framework's markdown
log is untouched). Records are never rewritten: closing a trade appends an
OUTCOME record referencing the TRADE record, plus a derived MISTAKE or
WINNING_PATTERN lesson. Only closed trades become historical analogs; win
statistics for Kelly require a minimum sample (5 closed trades) and both
wins and losses — a Kelly fraction fabricated from a degenerate history is
worse than none.

## ADR-0022: Parallel teams via reducer channel; live mode requires a checkpointer

**Status:** accepted (Phase 6)

Evidence gathering fans out from ``prepare`` into five team nodes that
LangGraph executes in one superstep; their writes merge through a reducer
on the ``evidence_by_team`` channel, and a fixed team iteration order keeps
votes deterministic regardless of branch completion order. Intra-team
agent calls can additionally run on a thread pool (``agent_workers``).
Debate stages whose team produced no evidence are skipped dynamically.

The human-approval gate is a LangGraph ``interrupt()``: a live run pauses
after the Portfolio Manager and only ``Command(resume={"approved": True})``
reaches execution — a decline is a recorded rejection. Because interrupts
need persistence, ``build_pro_pipeline`` refuses to build a live-mode
pipeline without a checkpointer (fail closed, Constraint 5). Structured
LLM calls get a bounded retry budget (``llm_retries``); streaming exposes
per-node updates for the Phase 10 dashboard.

## ADR-0023: Backtests run the live pipeline with a record/replay LLM cache

**Status:** accepted (Phase 7)

The backtest engine invokes the same compiled graph as live/paper — no
"backtest-only strategy" divergence. LLM cost is handled by ``CachingLLM``
(auto/record/replay keyed on ``sha256(schema + prompt)``, JSONL-persisted).
**Fidelity tradeoff:** a cache hit requires a byte-identical prompt, so
any change to prompts, roster, or data rendering invalidates the cache;
``replay`` mode raises on a miss rather than silently mixing fresh model
output into a run that claims to be reproducible. Per-run equity flows
through pipeline state, so sizing responds to drawdowns exactly as live.

## ADR-0024: Conservative simulation defaults

**Status:** accepted (Phase 7)

No lookahead by construction (decide on bar *i*'s close from bars <= *i*,
fill at bar *i+1*'s open); when a bar touches both the stop and a
take-profit, the stop fills first (pessimistic); slippage is side-aware
against the trader; orders cannot exceed a participation fraction of the
fill bar's volume — the excess is dropped, not filled. Walk-forward is
labelled *stability evaluation* until Phase 8 introduces fitted
parameters; Monte Carlo bootstraps trade P&L (costs embedded), seeded and
deterministic. v1 simulates one position at a time; multi-asset portfolio
simulation arrives with Phase 9 reconciliation. Tick-level simulation
awaits the paid microstructure feeds (docs/DATA_SOURCES.md).

## ADR-0025: Tabular RL first; PPO/SAC/DQN behind a policy protocol

**Status:** accepted (Phase 8) — deliberate deviation from the spec's
PPO/SAC/DQN list, flagged for sign-off.

The shipped policy is tabular action-value learning over a discretized
deterministic state space (regime × trend × volatility × z-score buckets —
Constraint 2: never raw LLM output), trained on full-feedback offline
transitions and evaluated with the Phase 7 objectives. Rationale: deep RL
adds a PyTorch/gymnasium dependency, GPU-shaped CI, and non-determinism,
while the current data (daily bars, one asset at a time) cannot feed a
policy network enough samples to beat a well-regularized table. The
``PolicyProtocol`` seam means a PPO/SAC/DQN implementation drops in
additively when backtest evidence justifies the dependency.

Advisory-only is structural: the advisor emits ``RL_Q_*`` MetricReadings
consumed by the roster's ``reinforcement_learning`` evidence agent — one
voice and one vote, subject to every gate. Undertrained states
(< min_visits) yield no advice; the agent abstains rather than whisper
noise. There is no code path from a policy output to execution that skips
the judge.
