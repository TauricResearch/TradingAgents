# Roadmap: TradingAgents Options Module

## Overview

This roadmap delivers a parallel options analysis team for TradingAgents, building from data foundation through computation modules, agent wrappers, and full pipeline integration. The build order follows a strict dependency chain: raw data first (Tradier), then deterministic math modules (Greeks, GEX, volatility, strategies), then LLM agent wrappers that interpret pre-computed signals, then debate/synthesis and pipeline integration. **Tastytrade** streaming (Phase 10) is a final enhancement after the batch pipeline proves correct.

**Canonical requirement IDs** are defined in [.planning/REQUIREMENTS.md](REQUIREMENTS.md). Each phase’s **Requirements:** line lists those IDs; resolve definitions there.

### Requirement ID quick reference

| ID | Meaning |
|----|---------|
| DATA-01–08 | Options data retrieval, Greeks, routing, streaming |
| VOL-01–07 | IV metrics, Tastytrade rules, VRP |
| GEX-01–04 | Gamma exposure and regime |
| FLOW-01–02 | Unusual activity / flow |
| STRAT-01–06 | Strategy construction and reasoning |
| AGENT-01–10 | Options agents, debate, scoring |
| INT-01–05 | Pipeline, CLI, validation, pure math module |
| REL-01–02, VAL-01, OBS-01, CONFIG-01 | Reliability, validation, audit logging, configurable thresholds (see REQUIREMENTS.md) |

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3, …): Planned milestone work
- Decimal phases (2.1, 2.2): **Reserved for future urgent insertions** (marked INSERTED when used). They document ad-hoc work between integers and **do not imply missing integer phases**.

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Tradier Data Layer** - Options chain retrieval, 1st-order Greeks, IV, and vendor routing integration
- [ ] **Phase 2: Deterministic Math Core** - Pure Python module for 2nd-order Greeks and all non-LLM computation
- [ ] **Phase 3: Volatility Metrics** - IV Rank, IV Percentile, and Volatility Risk Premium calculations
- [ ] **Phase 4: GEX & Market Microstructure** - Gamma exposure, dealer positioning, walls, flow detection
- [ ] **Phase 5: Volatility Surface** - SVI parametric fitting across strikes and expirations
- [ ] **Phase 6: Strategy Construction** - Multi-leg strategy building, P/L profiles, PoP estimation
- [ ] **Phase 7: Tastytrade Rules Engine** - IVR-based strategy selection and position management rules
- [ ] **Phase 8: Options Agent Team** - LLM agent factories for all options analyst roles
- [ ] **Phase 9: Debate, Scoring & Pipeline Integration** - Options debate, portfolio manager, composite score, LangGraph integration, CLI
- [ ] **Phase 10: Tastytrade Streaming** - Real-time Greeks and quotes via DXLink WebSocket

## Phase Details

### Phase 1: Tradier Data Layer
**Goal**: System can retrieve and display complete options chain data with Greeks and IV for any ticker
**Depends on**: Nothing (first phase)
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-08
**Success Criteria** (what must be TRUE):
  1. User can request an options chain for any ticker and receive strikes, expirations, bid/ask, volume, and OI from Tradier
  2. User can see 1st-order Greeks (Delta, Gamma, Theta, Vega, Rho) displayed per contract with ORATS source timestamp
  3. User can see implied volatility per contract (bid_iv, mid_iv, ask_iv, smv_vol) from Tradier
  4. User can filter the options chain by DTE range (e.g., 30-60 DTE)
  5. Tradier is registered as a new vendor in the existing data routing layer following the established provider pattern
**Plans:** 2 plans
Plans:
- [x] 01-01-PLAN.md -- Tradier common module and vendor module with typed dataclasses and chain retrieval
- [x] 01-02-PLAN.md -- Vendor routing integration, @tool functions, and comprehensive unit tests

### Phase 2: Deterministic Math Core
**Goal**: All deterministic financial math lives in a pure Python module with comprehensive tests, never as LLM tool calls
**Depends on**: Phase 1
**Requirements**: DATA-06, INT-05
**Success Criteria** (what must be TRUE):
  1. System calculates 2nd-order Greeks (Charm, Vanna, Volga/Vomma) via blackscholes library and returns correct values for known test cases
  2. A standalone pure Python module exists for all deterministic math (Black-Scholes, Greeks, GEX formulas, P/L calculations) with no LLM dependencies
  3. Every public function in the math module has unit tests with known analytical values
**Plans**: TBD

### Phase 3: Volatility Metrics
**Goal**: System can assess the implied volatility environment for any ticker to inform premium selling vs buying decisions
**Depends on**: Phase 1
**Requirements**: VOL-01, VOL-02, VOL-07
**Success Criteria** (what must be TRUE):
  1. System calculates IV Rank using 52-week IV high/low and returns a percentage that matches manual calculation
  2. System calculates IV Percentile using 252-day lookback of IV readings
  3. System calculates Volatility Risk Premium (VRP) by comparing current IV to realized/historical volatility
  4. All three metrics are deterministic Python functions with unit tests (not LLM computed)
**Plans**: TBD

### Phase 4: GEX & Market Microstructure
**Goal**: System can analyze dealer positioning and detect unusual options flow to identify structural support/resistance levels
**Depends on**: Phase 1
**Requirements**: GEX-01, GEX-02, GEX-03, GEX-04, FLOW-01, FLOW-02
**Success Criteria** (what must be TRUE):
  1. System computes Net Gamma Exposure (GEX) across all strikes with documented sign convention and unit tests confirming positive GEX above spot for typical equities
  2. System identifies Call Wall and Put Wall levels (max positive/negative gamma strikes) from the GEX profile
  3. System identifies Gamma Flip zone and Vol Trigger level where cumulative GEX changes sign
  4. System classifies market regime as positive gamma (mean-reverting) or negative gamma (trending)
  5. System detects unusual options activity by comparing current volume to historical average and open interest, classifying flow as bullish or bearish
**Plans**: TBD

### Phase 5: Volatility Surface
**Goal**: System can construct a full implied volatility surface via SVI parametric fitting for skew and term structure analysis
**Depends on**: Phase 1, Phase 3
**Requirements**: VOL-04
**Success Criteria** (what must be TRUE):
  1. System fits SVI parameters across strikes and expirations using scipy optimization with Gatheral no-butterfly-arbitrage constraints
  2. System gracefully falls back to linear interpolation when fewer than 5 liquid strikes exist for an expiration
  3. System filters illiquid strikes (OI < 100, spread > 30% of mid) before calibration to prevent garbage fits
**Plans**: TBD

### Phase 6: Strategy Construction
**Goal**: System can construct multi-leg options strategies with complete risk/reward profiles for any volatility and directional environment
**Depends on**: Phase 2, Phase 3
**Requirements**: STRAT-01, STRAT-02, STRAT-03, STRAT-04, STRAT-05, STRAT-06, VOL-03
**Success Criteria** (what must be TRUE):
  1. System constructs multi-leg strategies (verticals, iron condors, straddles, strangles, butterflies, jade lizards, diagonals, calendars) from actual chain data
  2. System selects strategy type based on IV environment (high IV = credit strategies, low IV = debit strategies) and directional bias
  3. System outputs specific contract recommendations with exact strikes, expirations, and leg quantities drawn only from available chain contracts
  4. System outputs alternative strike/expiration ranges when primary recommendations are illiquid or near thresholds
  5. System calculates max profit, max loss, breakeven points, and Probability of Profit for each strategy using deterministic math
**Plans**: TBD

### Phase 7: Tastytrade Rules Engine
**Goal**: System applies proven Tastytrade methodology rules to guide strategy selection and position management timing
**Depends on**: Phase 3, Phase 6
**Requirements**: VOL-05, VOL-06
**Success Criteria** (what must be TRUE):
  1. System applies IVR-based strategy selection rules (IVR >= 50% = sell premium, IVR < 30% = buy premium) and recommends appropriate strategy class
  2. System applies position management rules: 45 DTE entry targeting, 21 DTE management trigger, 50% profit target, 2x credit stop-loss
  3. Rules engine outputs are deterministic given the same IV Rank and DTE inputs (no LLM variance)
**Plans**: TBD

### Phase 8: Options Agent Team
**Goal**: Each options analysis domain has a dedicated LLM agent that interprets pre-computed signals and writes structured analysis to shared state
**Depends on**: Phase 2, Phase 3, Phase 4, Phase 5, Phase 6, Phase 7
**Requirements**: AGENT-01, AGENT-02, AGENT-03, AGENT-04, AGENT-05, AGENT-06, AGENT-09, AGENT-10
**Success Criteria** (what must be TRUE):
  1. Volatility agent interprets IV Rank, IV Percentile, VRP, vol surface, and skew and writes a structured volatility assessment to AgentState
  2. Greeks agent interprets 1st and 2nd-order Greeks and writes risk implications to AgentState
  3. Flow agent interprets unusual activity signals and writes smart money assessment to AgentState
  4. GEX agent interprets dealer positioning, gamma walls, regime, and structural levels and writes to AgentState
  5. Strategy agent recommends specific multi-leg strategies based on all analysis inputs and writes to AgentState
  6. Position sizing agent calculates risk/reward profiles and writes max P/L, breakevens, and PoP to AgentState
  7. All agents follow the existing create_*() factory pattern and composite Options Score (0-5) is computed from IV rank, GEX regime, flow signals, and vol skew
**Plans**: TBD

### Phase 9: Debate, Scoring & Pipeline Integration
**Goal**: Options analysis runs end-to-end as a parallel team in the LangGraph pipeline with debate, synthesis, and CLI support
**Depends on**: Phase 8
**Requirements**: AGENT-07, AGENT-08, INT-01, INT-02, INT-03, INT-04
**Success Criteria** (what must be TRUE):
  1. Options debate phase runs bull/bear debate on the options thesis with configurable rounds, producing a structured debate transcript
  2. Options portfolio manager synthesizes all agent analysis and debate into a final recommendation with transparent reasoning chain
  3. Options analysis team runs as a parallel section in the LangGraph StateGraph alongside existing stock analysis
  4. Options agents are configurable and optional (can be enabled/disabled like existing analysts)
  5. CLI supports options analysis mode with interactive options-specific prompts
  6. Deterministic validation layer checks strategy structural validity, risk limits, and liquidity before final output
**Plans**: TBD
**UI hint**: yes

### Phase 10: Tastytrade Streaming
**Goal**: System can receive real-time streaming Greeks and quotes via Tastytrade for sub-minute data freshness
**Depends on**: Phase 1, Phase 9
**Requirements**: DATA-07
**Success Criteria** (what must be TRUE):
  1. System connects to Tastytrade DXLink WebSocket and receives real-time streaming Greeks and quotes
  2. Streaming data integrates into the existing vendor routing layer as an alternative to Tradier's hourly ORATS refresh
  3. System gracefully falls back to Tradier REST data when WebSocket connection is unavailable
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10

**Parallelization:** After **Phase 1** completes, **Phases 2, 3, and 4** may run in parallel (each depends only on Phase 1). **Phase 5** is **not** in that parallel group: it **must follow Phase 3** (and Phase 1) because volatility-surface work depends on volatility metrics from Phase 3. Do not schedule Phase 5 concurrently with Phase 3. Phase 6 depends on Phases 2+3. Phase 7 depends on Phases 3+6. Phase 8 depends on all computation phases (2–7).

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Tradier Data Layer | 0/2 | Planning complete | - |
| 2. Deterministic Math Core | 0/TBD | Not started | - |
| 3. Volatility Metrics | 0/TBD | Not started | - |
| 4. GEX & Market Microstructure | 0/TBD | Not started | - |
| 5. Volatility Surface | 0/TBD | Not started | - |
| 6. Strategy Construction | 0/TBD | Not started | - |
| 7. Tastytrade Rules Engine | 0/TBD | Not started | - |
| 8. Options Agent Team | 0/TBD | Not started | - |
| 9. Debate, Scoring & Pipeline Integration | 0/TBD | Not started | - |
| 10. Tastytrade Streaming | 0/TBD | Not started | - |
