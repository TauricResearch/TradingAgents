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
