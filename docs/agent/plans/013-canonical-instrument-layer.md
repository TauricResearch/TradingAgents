# Plan: Canonical Instrument Identity and Type Layer

**Status**: in_progress
**Branch**: codex/instrument-canonical-layer
**Principle**: Resolve instrument identity and type once, upstream, then route every downstream merge and execution path from that canonical object rather than from raw ticker strings.

## Problem

The current system still treats most securities as uppercase ticker strings. That is sufficient for simple equity analysis, but it breaks down when different instrument families share the same execution path.

The TSDD class of bug exposed the gap clearly:

- common stocks, ETFs, inverse ETFs, and leveraged ETFs can be merged together as if they were equivalent instruments
- scan candidates and holdings are deduplicated by ticker only
- downstream pipeline dispatch cannot reliably distinguish a stock deep dive from an ETF or future crypto path
- portfolio review only sees completed ticker analyses keyed by uppercase ticker strings

This is currently visible at the main seams:

- per-ticker pipeline entry in `agent_os/backend/services/langgraph_engine.py`
- scan and holdings merge in `agent_os/backend/services/langgraph_engine.py`
- holdings-to-candidates synthesis in `tradingagents/pipeline/macro_bridge.py`
- portfolio candidate completion matching in `tradingagents/graph/portfolio_setup.py`
- holdings data model in `tradingagents/portfolio/models.py`

The user also wants a future market-analysis node that tracks core benchmark instruments and main crypto symbols. That requirement makes simple ticker normalization insufficient. We need explicit classification.

## Goals

1. Build a canonical instrument layer upstream of pipeline execution.
2. Distinguish instrument identity from instrument classification.
3. Ensure ETFs, inverse ETFs, leveraged ETFs, common stocks, and future coin symbols cannot silently enter the wrong analysis path.
4. Make scan candidates, holdings, saved analyses, and portfolio review join on a stable canonical key.
5. Support future tracked universes for market benchmarks and crypto leaders without polluting `stocks_to_investigate`.

## Current Cut

The first implementation pass keeps the design intentionally small:

- holdings storage stays unchanged
- canonical classification happens in code at scan, holdings, pipeline, and portfolio merge boundaries
- scan summaries gain normalized `equity_candidates`, `tracked_market_instruments`, and `tracked_crypto_instruments`
- analysis artifacts gain canonical instrument metadata
- the current deep-dive queue accepts only canonical `common_stock` instruments
- ETFs and crypto symbols are classified and preserved in normalized state, but explicitly kept out of the stock-only path
- the deep-dive graph now also has a deterministic `Instrument Preflight` node as a second filter before analyst fan-out

## Non-Goals

- Do not implement the ETF-specific or crypto-specific analysis nodes yet.
- Do not redesign scanner prompts in this phase.
- Do not depend on live vendor classification at runtime for every request.
- Do not add legacy migration or compatibility handling for old artifacts in this phase.

## Core Decision

Introduce a canonical resolver that converts any raw symbol-like input into a normalized instrument object. Every upstream ingress point should call that resolver before merge, persistence, or execution.

The resolver must answer two different questions:

1. What exact instrument is this?
2. What class of instrument is it?

Those are related but not the same. Routing should depend on classification, while joins and persistence should depend on canonical identity.

## Canonical Instrument Model

Use two dimensions:

- `asset_class`: `equity`, `etf`, `index`, `crypto`, `cash_equivalent`, `unknown`
- `instrument_type`: `common_stock`, `sector_etf`, `broad_market_etf`, `inverse_etf`, `leveraged_etf`, `treasury_etf`, `commodity_etf`, `volatility_etf`, `coin`, `unknown`

Suggested canonical fields:

- `raw_symbol`
- `canonical_symbol`
- `display_symbol`
- `instrument_key`
- `asset_class`
- `instrument_type`
- `exchange_or_market`
- `quote_currency`
- `is_etf`
- `is_inverse`
- `is_leveraged`
- `classification_source`
- `classification_confidence`
- `source_context`

### Field semantics

- `instrument_key` is the stable join key used by scan merge, holdings merge, saved analysis lookup, and portfolio review.
- `canonical_symbol` is the normalized symbol representation for tool calls and persistence.
- `display_symbol` preserves the user-facing format when needed.
- `source_context` identifies where the symbol came from, for example `scan`, `holding`, `benchmark_registry`, or `crypto_registry`.

## Instrument Registry

Add a lightweight registry layer that can classify instruments without relying entirely on a live vendor round trip.

The registry should have four logical sources:

1. Holdings-derived instruments
2. Scan-derived instruments
3. Tracked market instruments
4. Tracked crypto instruments

### Tracked market instruments

These are not scan candidates. They are benchmark instruments used for market state and context.

Initial examples:

- `SPY`
- `QQQ`
- `IWM`
- `DIA`
- `TLT`
- `GLD`
- `UUP`
- `SGOV`
- optional volatility or breadth proxies later

### Tracked crypto instruments

These are also not equity candidates. They are first-class tracked symbols for future market classification.

Initial examples:

- `BTC`
- `ETH`
- `SOL`
- `BNB`
- `XRP`

The registry should keep these universes separate from `stocks_to_investigate`.

## Architecture

### 1. Resolver layer

Add a new module responsible for:

- normalizing raw input symbols
- assigning a canonical identity
- classifying known ETFs and crypto symbols
- marking unknown symbols safely when confidence is low

The resolver should support:

- curated registry rules first
- metadata hints from holdings or scan payloads second
- optional vendor enrichment later

### 2. Canonical ingress points

These points must resolve instruments before any join or dispatch:

- scan candidate extraction from scan summary
- holdings-to-candidates conversion
- `run_auto()` scan and holdings merge
- `run_pipeline()` execution entry
- `run_portfolio()` saved-analysis merge and holdings price fetch

### 3. Canonical persistence

Persist canonical metadata alongside existing ticker fields in:

- scan summary artifacts
- analysis artifacts
- synthesized holding candidates
- portfolio-stage merged candidate objects

Migration rule:

- update active code paths to write and read canonical metadata directly
- no lazy backfill for old artifacts
- no compatibility layer for pre-canonical saved payloads

### 4. Routing

Execution routing should depend on classification:

- `common_stock` -> current equity deep-dive path
- ETF family -> ETF-specific path later, but for now block or guard against stock-only assumptions
- `coin` -> crypto path later
- `unknown` -> guarded fallback, never silently treated as common stock

## Data Flow Changes

### Current flow

- raw scan tickers -> uppercase strings
- raw holdings tickers -> uppercase strings
- merged ticker list -> pipeline dispatch
- saved analyses keyed by uppercase ticker
- portfolio review joins on uppercase ticker

### Target flow

- raw symbols -> canonical instrument objects
- canonical objects -> filtered into separate universes
- equity candidate instruments -> pipeline dispatch
- tracked market instruments -> future market-analysis node
- tracked crypto instruments -> future crypto market node
- saved analyses keyed by `instrument_key`
- portfolio review joins on `instrument_key`

## Merge Rules

### Equity candidate merge

Merge scan candidates and holdings on `instrument_key`, not `ticker.upper()`.

If a holding and scan candidate resolve to the same instrument:

- produce one canonical instrument entry
- keep provenance from both sources
- prefer richer metadata from scan payload for thesis fields
- preserve holding context so portfolio review knows it is an existing position

### Universe separation

Do not include tracked market instruments or tracked crypto instruments in `stocks_to_investigate`.

Instead, introduce separate normalized collections such as:

- `equity_candidates`
- `tracked_market_instruments`
- `tracked_crypto_instruments`

In the compatibility phase, `stocks_to_investigate` can remain, but it should be generated from `equity_candidates` only.

## Implementation Phases

### Phase 1: Canonical data model and resolver

- add canonical instrument dataclass or typed dict
- add a first-pass resolver and curated registry
- support at least common stocks, broad ETFs, inverse ETFs, leveraged ETFs, SGOV-like cash-equivalent ETFs, and top crypto symbols
- define `unknown` behavior explicitly

### Phase 2: Upstream adoption

- resolve scan candidates at extraction time
- resolve holdings before `candidates_from_holdings()`
- change `run_auto()` merge logic to work from canonical objects
- change `run_pipeline()` entry to accept a canonical instrument payload, while keeping raw ticker compatibility

### Phase 3: Persistence and portfolio merge

- save canonical metadata into scan and analysis artifacts
- change portfolio-stage saved-analysis lookup and completed-candidate matching to use `instrument_key`
- require the new canonical format for active development workflows

### Phase 4: Guarded routing

- add explicit classification-based dispatch
- keep current equity path for common stocks only
- return guarded skip or warning for ETF and crypto classes until dedicated paths exist

### Phase 5: Future nodes

Not part of this immediate change, but the canonical layer should make these trivial to add later:

- market benchmark tracking node
- crypto market tracker node
- ETF-specific analysis node

## Risks

### 1. False classification

If the resolver misclassifies a symbol, routing will still be wrong. The initial resolver must prefer `unknown` over unsafe certainty.

### 2. Backward compatibility

We are still in active development, so this phase should not spend time on old artifact compatibility or migration support.

### 3. Join drift

During rollout, some code may still join on ticker while new code joins on canonical key. The migration should be staged carefully to avoid split identity behavior.

### 4. Scope creep

This phase should stop at canonicalization and guarded routing. ETF and crypto analysis behavior can come later.

## Test Plan

The initial test set should be mostly unit tests. Live or integration tests are not needed for the first pass because the core risk is merge and routing logic, not vendor transport.

### Unit tests: resolver and classification

1. `common_stock` classification
   Input: `AAPL`
   Expect: `asset_class=equity`, `instrument_type=common_stock`, `is_etf=False`

2. `broad_market_etf` classification
   Input: `SPY`
   Expect: `asset_class=etf`, `instrument_type=broad_market_etf`, `is_etf=True`

3. `sector_etf` classification
   Input: `XLF`
   Expect: `asset_class=etf`, `instrument_type=sector_etf`

4. `inverse_etf` classification
   Input: `SH`
   Expect: `instrument_type=inverse_etf`, `is_inverse=True`

5. `leveraged_etf` classification
   Input: `TQQQ`
   Expect: `instrument_type=leveraged_etf`, `is_leveraged=True`

6. `leveraged_inverse_etf` classification
   Input: `SQQQ`
   Expect: `instrument_type=leveraged_etf` or a more specific inverse-leveraged subtype if we define it, plus `is_inverse=True`, `is_leveraged=True`

7. `cash_equivalent_etf` classification
   Input: `SGOV`
   Expect: `asset_class=cash_equivalent` or `asset_class=etf` with `instrument_type=treasury_etf`, depending on the final enum choice

8. `coin` classification
   Input: `BTC`
   Expect: `asset_class=crypto`, `instrument_type=coin`

9. `unknown` fallback classification
   Input: a symbol absent from the registry
   Expect: `instrument_type=unknown`, safe fallback fields, no crash

10. symbol normalization preserves exchange-qualified names
    Input: `.TO`, `.L`, `.HK`, or `.T` examples
    Expect: suffix preserved in `canonical_symbol`

### Unit tests: merge behavior

11. scan and holdings merge deduplicates on canonical key
    Scan candidate: `SPY`
    Holding: `SPY`
    Expect: one merged instrument, two provenance sources

12. scan and holdings merge keeps separate instruments with similar names
    Input: `SPY` and `SPYG`
    Expect: two distinct canonical keys

13. holdings candidate synthesis carries canonical metadata
    Holding input should produce a candidate with `instrument_key`, `asset_class`, and `instrument_type`

14. scan extraction produces canonical equity candidates only
    If scan payload contains mixed tracked instruments later, `equity_candidates` should exclude market and crypto trackers

15. portfolio completed-candidate matching uses canonical key
    Saved analysis for canonical instrument should match the completed candidate even if legacy `ticker` casing differs

### Unit tests: routing behavior

16. pipeline dispatch accepts common stock
    Input: canonical `AAPL`
    Expect: routed to current equity deep-dive path

17. pipeline dispatch guards ETF before stock-only path
    Input: canonical `SPY`
    Expect: explicit guarded handling, not silent stock deep dive

18. pipeline dispatch guards inverse ETF before stock-only path
    Input: canonical `SQQQ`
    Expect: explicit guarded handling

19. pipeline dispatch guards coin before stock-only path
    Input: canonical `BTC`
    Expect: explicit guarded handling or future-node placeholder

20. `run_auto()` separates equity candidates from tracked market instruments
    Expect: benchmark instruments do not inflate the deep-dive queue

21. `run_auto()` separates equity candidates from tracked crypto instruments
    Expect: coin symbols do not enter stock pipeline queue

### Unit tests: regression coverage for the TSDD bug class

22. inverse ETF from holdings does not enter common stock path
    Input: holding `SQQQ`
    Expect: classification is inverse/leverage aware and routing is guarded

23. ETF from scan output does not get treated as common stock
    Input: scan candidate `SPY`
    Expect: non-stock classification persists through merge and dispatch

24. completed analysis lookup uses canonical identity
    Saved analysis produced by the new canonical flow matches portfolio review and rerun lookup paths

### Integration-style tests inside the offline suite

25. end-to-end offline orchestration with mocked resolver inputs
    Simulate scan summary plus holdings with `AAPL`, `SPY`, `SQQQ`, and `BTC`
    Expect:
    - `AAPL` enters equity queue
    - `SPY` is excluded from stock-only queue
    - `SQQQ` is excluded from stock-only queue
    - `BTC` is excluded from stock-only queue
    - tracked universes remain available in normalized state

## Proposed Test Files

- `tests/unit/test_instrument_resolver.py`
- `tests/unit/test_instrument_registry.py`
- `tests/unit/test_langgraph_engine_instrument_routing.py`
- `tests/unit/test_macro_bridge_instrument_merge.py`
- `tests/portfolio/test_portfolio_setup_instrument_matching.py`

## Acceptance Criteria

- No raw ticker-only merge remains at the scan/holdings/pipeline boundary for new code paths.
- Common stocks, ETFs, inverse ETFs, leveraged ETFs, and top tracked coin symbols are classified deterministically.
- Portfolio review can join completed analyses through canonical identity, not just uppercase ticker text.
- Benchmark instruments and tracked coin symbols are represented separately from `stocks_to_investigate`.
- Unknown instruments fail safe and do not silently enter the common-stock path.
- The implementation does not include legacy backfill or compatibility logic for old pre-canonical artifacts.

## Next Step

Implement Phase 1 first: add the canonical instrument model, curated registry, resolver, and unit tests before modifying the engine merge paths.
