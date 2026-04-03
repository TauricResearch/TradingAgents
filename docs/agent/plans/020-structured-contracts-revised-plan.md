# 020 Structured Contracts Revised Plan

## Purpose

This plan replaces the original sequencing in 017-019 with a more feasible rollout based on run artifacts and team review.

The key correction is simple:

- the main architectural risk is still prose re-write drift
- but the main production failure today is upstream validation and missing analyst output

So the revised plan fixes the blocking failure modes first, then introduces smaller structured contracts, then removes prose-first dependencies, and only after that runs the raw-context experiment.

Companion docs:

- [017 Structured Contracts and Raw Context Experiment](/Users/Ahmet/Repo/TradingAgents/docs/agent/plans/017-structured-contracts-and-raw-context-experiment.md)
- [018 Agent Handoff Matrix](/Users/Ahmet/Repo/TradingAgents/docs/agent/plans/018-agent-handoff-matrix.md)
- [019 Structured Contracts Implementation Checklist](/Users/Ahmet/Repo/TradingAgents/docs/agent/plans/019-structured-contracts-implementation-checklist.md)
- [021 Post-News Node Implementation Plan](/Users/Ahmet/Repo/TradingAgents/docs/agent/plans/021-post-news-node-implementation-plan.md)

## What Changes From 017-019

### 1. Fix the actual blockers before downstream contract work

The 2026-04-02 runs failed before the trader, risk, or PM path mattered.

So the first implementation phase must address:

- news validation thresholds and format rigidity
- instrument classification errors such as USO marked as non-ETF
- silent empty analyst outputs
- PM field ownership bug
- macro regime prose fallback

### 2. Use smaller contracts the LLM can reliably produce

Do not ask analysts to emit large claim lists with 10-12 fields per claim.

Instead use a two-tier model:

1. LLM emits a small summary-level structured contract
2. deterministic code extracts or injects claim-level details where needed

This keeps structured output feasible and reduces the chance that the contract system itself becomes a new abort source.

### 3. Add structured fields incrementally, not all at once

Do not add every new field across the whole graph in one phase.

Add only the fields required for the current phase, validate them, then expand.

### 4. Make the research packet degrade gracefully

The packet builder must work even when only one analyst produced content.

It should never collapse into an empty packet just because sentiment, fundamentals, or news are absent.

### 5. Move `include_raw_context` to the end

Do not run the A/B experiment until the pipeline can complete reliably.

That experiment requires a stable baseline with successful end-to-end runs.

## Revised Design Principles

### A. Structured where it matters, deterministic where possible

Use structured contracts for canonical node handoffs, but keep deterministic extraction for:

- scanner-derived catalyst dates
- numeric claim extraction from markdown tables or bullet lists
- analyst status and contribution accounting
- source validation against run-scoped evidence

### B. Preserve strong existing output formats

Do not force every analyst to produce fully JSON-native output immediately.

Examples:

- market analyst can keep its markdown table and add a small structured summary block
- trader can keep a readable plan while also emitting a compact structured object
- PM can build on the existing structured decision pattern already used by the PM decision agent

### C. Contracts must represent absence explicitly

Every analyst contract should include status metadata so downstream nodes can reason over missing or failed domains explicitly.

Minimum status fields:

- `status`: `completed | failed | empty | aborted`
- `claim_count`
- `abort_reason`
- `contract_version`

### D. Version compatibility must be explicit

During migration, downstream nodes must tolerate:

- missing structured fields
- prior contract versions
- mixed structured + prose state

Track prose fallback usage so it trends toward zero over time rather than disappearing blindly.

## Revised Contract Strategy

## Tier 1: Small LLM-produced summary contracts

These are the canonical structured outputs per node.

Example analyst pattern:

```python
class AnalystSummaryContract(BaseModel):
    ticker: str
    as_of_date: str
    status: Literal["completed", "failed", "empty", "aborted"]
    recommendation: str
    confidence: str
    key_points: list[str]
    key_metrics: dict[str, str | float | int]
    claim_count: int
    abort_reason: str = ""
    contract_version: str
```

Domain-specific analyst contracts may add a few extra fields, but should stay small.

Examples:

- market: `macro_regime`, `regime_score`, `trend_signal`, `key_levels`, `momentum`, `volatility`
- fundamentals: `valuation`, `profitability`, `balance_sheet`, `cash_flow`
- sentiment: `sentiment_bias`, `volume_signal`, `platform_signals`
- news: `top_events`, `source_count`, `critical_abort`

## Tier 2: Deterministic support data

These should be built by code, not delegated to the LLM where possible:

- parsed market table rows
- scanner-derived catalyst dates
- evidence-linked source references
- analyst contribution summary
- structured packet assembly

## Revised Phase Plan

## Phase 0: Stabilize the current pipeline

Goal:

reduce unnecessary aborts and make missing data visible before changing the graph architecture

### 0.1 Fix news validation

- relax ticker-relevance thresholds for ETFs and thin-news instruments
- stop relying on rigid prose citation formats
- validate against structured source fields and run-scoped evidence
- ensure valid partial news output is retained instead of hard-failing the report

### 0.2 Fix instrument classification

- correct ETF/common-stock classification errors
- ensure scanner filtering and validation thresholds use the correct instrument type
- stop ETF runs from inheriting irrelevant equity assumptions

### 0.3 Add analyst status accounting

- each analyst output should record `completed`, `failed`, `empty`, or `aborted`
- capture `claim_count` or equivalent contribution count
- surface missing domains to downstream nodes explicitly

### 0.4 Fix known graph bugs

- PM must use the real trader output, not `investment_plan`
- remove market macro-regime fallback from full prose report

### 0.5 Add artifact-backed baseline tests

Use:

- AAPL 2026-03-31 as the happy path fixture
- JPM 2026-04-02 as the abort-path and partial-data fixture
- USO 2026-04-02 as the ETF classification and validation fixture

Exit criteria:

- at least a small set of end-to-end runs completes again
- abort reasons reflect data issues, not formatting artifacts
- silent empty analysts are visible in artifacts and state

## Phase 1: Introduce the first minimal analyst contract

Goal:

prove the contract pattern on the easiest node before broad rollout

Start with the market analyst because it is already semi-structured.

### Market analyst contract

Keep:

- markdown report
- indicator table

Add:

- `market_report_structured`
- explicit `macro_regime`
- explicit `status`
- compact key metrics
- contract version

Do not add full claim objects yet.

Instead:

- parse the indicator table deterministically where needed
- keep numeric provenance derived from the table/report

Exit criteria:

- market node produces stable structured output on existing fixtures
- downstream consumers can read market structure without parsing full prose

## Phase 1.5: Build the deterministic research packet with graceful degradation

Goal:

replace summary-first as the canonical machine handoff without requiring every analyst to be structured on day one

Rules:

- always include scanner ground truth
- include structured analyst outputs when available
- include analyst status for missing/failed domains
- if fewer than 2 structured analyst outputs exist, degrade gracefully instead of emitting an empty packet

The packet should answer:

- which analysts contributed
- which analysts failed or were empty
- what the strongest available evidence is
- what data is missing

Exit criteria:

- `research_packet_structured` is never empty when any upstream signal exists
- packet provenance is explicit even in partial-data runs

## Phase 2: Add the highest-value downstream contracts

Goal:

formalize the nodes that already produce good output with relatively small structural deltas

### 2.1 Research manager

Add `investment_plan_structured` with:

- recommendation
- top bull evidence
- top bear evidence
- winning thesis
- rationale
- key risks
- status
- contract version

This should be a small delta from the current output, which already separates strongest bull and bear evidence.

### 2.2 Trader

Add `trader_plan_structured` with:

- action
- entry
- stop-loss
- take-profit
- size
- time horizon
- risk controls
- catalyst dates
- status
- contract version

Important:

- catalyst dates must be injected from scanner/economic calendar state
- the trader should never invent dates

Exit criteria:

- research manager and trader outputs are machine-readable
- structured trader dates always trace to deterministic state

## Phase 3: Expand analyst coverage incrementally

Goal:

bring remaining analysts into the contract system one at a time

Recommended order:

1. news
2. fundamentals
3. sentiment

Notes:

- news already has the strongest case for structure because validation is source-driven
- fundamentals and sentiment must handle empty/failure status cleanly
- do not block the rest of the graph if one analyst remains prose-only during migration

Exit criteria:

- at least 3 analyst domains produce usable structured outputs on happy-path fixtures
- packet assembly no longer depends primarily on prose summaries

## Phase 4: Structured risk path

Goal:

remove the largest remaining prose-to-prose drift chain

Add:

- structured round outputs for risk debators
- `risk_synthesis_structured`

Keep:

- debate prose as presentation only during migration

Simplify where possible:

- if a debate node only paraphrases existing structured state, mark it as a removal candidate

Exit criteria:

- risk synthesis operates on structured trader and evidence state
- debate history is not required as the canonical machine input

## Phase 5: Portfolio manager structured decision

Goal:

make the final decision traceable to structured upstream state

Add:

- `final_trade_decision_structured`

This should build on the existing PM structured decision pattern rather than inventing a new large schema.

Exit criteria:

- final action and risk controls are linked to structured upstream inputs
- saved artifacts preserve both machine-readable and human-readable views

## Phase 6: Remove prose-first dependencies

Goal:

clean up the graph only after structured contracts are proven

Candidates:

- `research_packet_summary` as canonical input
- prose-first fallback logic in summary helpers
- debate history as required machine input
- nodes whose only job is to paraphrase structured state

Exit criteria:

- each removed field or node has a stable structured replacement
- graph complexity decreases materially

## Phase 7: Run the `include_raw_context` experiment

Prerequisite:

- at least 5 successful end-to-end baseline runs

Only after the graph is stable:

- add `include_raw_context`
- append bounded ticker-scoped filtered raw evidence
- compare baseline vs raw-augmented runs for grounding and usefulness

Keep default:

- `include_raw_context=False`

Success gate:

- quality improves without blowing up prompt size or runtime

## Implementation Checklist

### Immediate next coding steps

1. fix news validation and source-threshold behavior
2. fix ETF instrument classification and downstream usage
3. add analyst status fields for every analyst result
4. fix PM trader-plan field ownership
5. remove macro-regime prose fallback
6. add AAPL/JPM/USO artifact-backed regression fixtures
7. implement `market_report_structured`
8. implement `research_packet_structured` with graceful degradation
9. implement `investment_plan_structured`
10. implement `trader_plan_structured` with deterministic catalyst injection

### Explicit non-goals for the first pass

- do not convert every analyst to large per-claim JSON
- do not add all structured fields in one migration
- do not remove prose fields before downstream readers are updated
- do not run the raw-context A/B experiment before the baseline pipeline is stable

## Validation Strategy

For each phase, verify both:

1. contract correctness
2. business-path behavior

Business-path checks:

- happy path still reaches PM
- abort path still aborts when it should
- partial-data path degrades gracefully instead of collapsing

Required fixture set:

- AAPL 2026-03-31: happy path
- JPM 2026-04-02: partial-data and prior abort path
- USO 2026-04-02: ETF and validation path

## Final Recommendation

Do not frame this as "structured contracts everywhere" as the first move.

The practical rollout is:

1. stop invalid aborts
2. expose missing analyst state explicitly
3. add one minimal analyst contract
4. build a deterministic packet that can survive partial data
5. structure the manager and trader path
6. then clean up the deeper debate and PM chain
7. only then run the raw-context experiment
