# Requirements: TradingAgents Options Module

**Defined:** 2026-03-29
**Core Value:** Agents produce actionable multi-leg options recommendations with transparent, educational reasoning

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Data Foundation

- [ ] **DATA-01**: System can retrieve full options chain (strikes, expirations, bid/ask, volume, OI) via Tradier API
- [ ] **DATA-02**: System can retrieve options expirations and available strikes for any ticker via Tradier API
- [ ] **DATA-03**: System displays 1st-order Greeks (Delta, Gamma, Theta, Vega, Rho) from ORATS via Tradier
- [ ] **DATA-04**: System displays implied volatility per contract (bid_iv, mid_iv, ask_iv, smv_vol)
- [ ] **DATA-05**: System can filter options chains by DTE range (e.g., 30-60 DTE for income strategies)
- [ ] **DATA-06**: System calculates 2nd-order Greeks (Charm, Vanna, Volga/Vomma) via blackscholes library
- [ ] **DATA-07**: System can retrieve real-time streaming Greeks and quotes via Tastyworks DXLink WebSocket
- [ ] **DATA-08**: System integrates Tradier and Tastyworks as new vendors in the existing data routing layer

### Volatility Analysis

- [ ] **VOL-01**: System calculates IV Rank using 52-week IV high/low for any ticker
- [ ] **VOL-02**: System calculates IV Percentile using 252-day lookback of IV readings
- [ ] **VOL-03**: System estimates Probability of Profit (PoP) for each recommended strategy
- [ ] **VOL-04**: System constructs volatility surface via SVI parametric fitting across strikes and expirations
- [ ] **VOL-05**: System implements TastyTrade rules engine: IVR-based strategy selection (IVR >= 50% = sell premium, IVR < 30% = buy premium)
- [ ] **VOL-06**: System implements TastyTrade position management rules: 45 DTE entry, 21 DTE management, 50% profit target, 2x credit stop-loss
- [ ] **VOL-07**: System calculates Volatility Risk Premium (VRP) by comparing IV to historical/realized volatility

### Dealer Positioning & Flow

- [ ] **GEX-01**: System computes Net Gamma Exposure (GEX) across all strikes from open interest data
- [ ] **GEX-02**: System identifies Call Wall and Put Wall levels (max positive/negative gamma strikes)
- [ ] **GEX-03**: System identifies Gamma Flip zone (where cumulative GEX changes sign) and Vol Trigger level
- [ ] **GEX-04**: System classifies market regime as positive gamma (mean-reverting) or negative gamma (trending)
- [ ] **FLOW-01**: System detects unusual options activity by comparing volume to historical average and open interest
- [ ] **FLOW-02**: System classifies flow direction (bullish/bearish) based on trade side, strike location, and OI changes

### Strategy & Output

- [ ] **STRAT-01**: System recommends multi-leg options strategies (verticals, iron condors, straddles, strangles, butterflies, jade lizards, diagonals, calendars)
- [ ] **STRAT-02**: System selects strategy type based on IV environment (high IV = credit strategies, low IV = debit strategies) and directional bias
- [ ] **STRAT-03**: System outputs specific contract recommendations with exact strikes, expirations, and leg quantities
- [ ] **STRAT-04**: System outputs alternative strike/expiration ranges when exact contracts are illiquid or close to thresholds
- [ ] **STRAT-05**: System calculates max profit, max loss, and breakeven points for each recommended strategy
- [ ] **STRAT-06**: System provides transparent reasoning chain showing why each strategy was selected (educational)

### Agent Pipeline

- [ ] **AGENT-01**: Volatility analysis agent evaluates IV Rank, IV Percentile, VRP, vol surface, and skew
- [ ] **AGENT-02**: Greeks analysis agent evaluates 1st and 2nd-order Greeks and their implications for position risk
- [ ] **AGENT-03**: Options flow / unusual activity agent identifies smart money signals and flow direction
- [ ] **AGENT-04**: Gamma exposure agent analyzes dealer positioning, gamma walls, regime, and structural levels
- [ ] **AGENT-05**: Strategy selection agent recommends specific multi-leg strategies based on all analysis inputs
- [ ] **AGENT-06**: Position sizing agent calculates risk/reward profiles (max P/L, breakevens, PoP) for recommended strategies
- [ ] **AGENT-07**: Options debate phase runs bull/bear debate on the options thesis with configurable rounds
- [ ] **AGENT-08**: Options portfolio manager synthesizes all analysis and debate into final recommendation with reasoning
- [ ] **AGENT-09**: All options agents follow existing create_*() factory pattern and write to shared AgentState
- [ ] **AGENT-10**: Composite Options Score (0-5) computed from IV rank, GEX regime, flow signals, and vol skew

### Integration

- [ ] **INT-01**: Options analysis team runs as parallel section in the LangGraph StateGraph alongside existing stock analysis
- [ ] **INT-02**: Options agents are configurable and optional (can be enabled/disabled like existing analysts)
- [ ] **INT-03**: CLI updated to support options analysis mode with interactive options-specific prompts
- [ ] **INT-04**: Deterministic validation layer checks strategy structural validity, risk limits, and liquidity before output
- [ ] **INT-05**: All deterministic math (Black-Scholes, GEX, 2nd-order Greeks, P/L) in pure Python module, not LLM tool calls

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Enhanced Data

- **EDATA-01**: Historical IV surface storage for backtesting and regime comparison
- **EDATA-02**: 0DTE strategy analysis with sub-minute data refresh
- **EDATA-03**: Multi-ticker batch analysis for portfolio-level options scanning

### Advanced Analytics

- **ADV-01**: Portfolio-level Greeks aggregation across multiple positions
- **ADV-02**: Custom volatility models (Heston, local vol) for exotic pricing
- **ADV-03**: Options backtesting engine with historical vol surfaces and fill simulation

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Order execution / broker integration | Analysis-only mandate; regulatory complexity |
| Real-time streaming dashboard | Batch `propagate()` architecture; streaming is for data freshness only |
| 0DTE strategy support | Requires real-time infrastructure not yet in place |
| Historical IV surface database | Requires ORATS subscription or building own historical DB |
| Options backtesting engine | Separate domain requiring historical vol surfaces and fill simulation |
| Custom vol models (Heston, local vol) | Over-engineering; SVI sufficient for equity options |
| Portfolio-level Greeks aggregation | No position state in analysis-only module |
| Mobile/web UI | CLI and Python API only |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 1 | Pending |
| DATA-02 | Phase 1 | Pending |
| DATA-03 | Phase 1 | Pending |
| DATA-04 | Phase 1 | Pending |
| DATA-05 | Phase 1 | Pending |
| DATA-06 | Phase 2 | Pending |
| DATA-07 | Phase 10 | Pending |
| DATA-08 | Phase 1 | Pending |
| VOL-01 | Phase 3 | Pending |
| VOL-02 | Phase 3 | Pending |
| VOL-03 | Phase 6 | Pending |
| VOL-04 | Phase 5 | Pending |
| VOL-05 | Phase 7 | Pending |
| VOL-06 | Phase 7 | Pending |
| VOL-07 | Phase 3 | Pending |
| GEX-01 | Phase 4 | Pending |
| GEX-02 | Phase 4 | Pending |
| GEX-03 | Phase 4 | Pending |
| GEX-04 | Phase 4 | Pending |
| FLOW-01 | Phase 4 | Pending |
| FLOW-02 | Phase 4 | Pending |
| STRAT-01 | Phase 6 | Pending |
| STRAT-02 | Phase 6 | Pending |
| STRAT-03 | Phase 6 | Pending |
| STRAT-04 | Phase 6 | Pending |
| STRAT-05 | Phase 6 | Pending |
| STRAT-06 | Phase 6 | Pending |
| AGENT-01 | Phase 8 | Pending |
| AGENT-02 | Phase 8 | Pending |
| AGENT-03 | Phase 8 | Pending |
| AGENT-04 | Phase 8 | Pending |
| AGENT-05 | Phase 8 | Pending |
| AGENT-06 | Phase 8 | Pending |
| AGENT-07 | Phase 9 | Pending |
| AGENT-08 | Phase 9 | Pending |
| AGENT-09 | Phase 8 | Pending |
| AGENT-10 | Phase 8 | Pending |
| INT-01 | Phase 9 | Pending |
| INT-02 | Phase 9 | Pending |
| INT-03 | Phase 9 | Pending |
| INT-04 | Phase 9 | Pending |
| INT-05 | Phase 2 | Pending |

**Coverage:**
- v1 requirements: 42 total
- Mapped to phases: 42
- Unmapped: 0

---
*Requirements defined: 2026-03-29*
*Last updated: 2026-03-29 after roadmap creation*
