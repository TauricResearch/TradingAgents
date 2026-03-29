# TradingAgents — Options Trading Module

## What This Is

An options trading analysis module for TradingAgents — a multi-agent AI system that uses LLM-powered agent teams to analyze financial markets. The new module adds a parallel options analysis team that evaluates options chains, Greeks, volatility surfaces, dealer positioning, and options flow to recommend specific multi-leg options strategies with transparent reasoning.

## Core Value

Agents produce actionable multi-leg options recommendations (with specific contracts AND alternative ranges) backed by transparent, educational reasoning that helps the user both trade and learn.

## Requirements

### Validated

These capabilities already exist in the codebase:

- ✓ Multi-agent LangGraph pipeline with sequential analyst teams — existing
- ✓ Investment debate (bull vs bear) with configurable rounds — existing
- ✓ Risk debate (aggressive/conservative/neutral) — existing
- ✓ Portfolio manager final decision synthesis — existing
- ✓ Vendor-abstracted data layer with pluggable providers (yfinance, Alpha Vantage) — existing
- ✓ BM25-based memory system for agent reflection/learning — existing
- ✓ LLM client factory supporting OpenAI, Anthropic, Google — existing
- ✓ CLI with Rich UI and interactive prompts — existing
- ✓ Signal processing with 5-tier rating scale — existing
- ✓ Options chain data retrieval via Tradier API (chains, expirations, strikes, Greeks, IV) — Validated in Phase 1: Tradier Data Layer
- ✓ Tradier registered as vendor in data routing layer with rate limit fallback — Validated in Phase 1: Tradier Data Layer

### Active

- [ ] Options chain data retrieval via **Tastytrade** API (DXLink WebSocket streaming Greeks, real-time quotes; the broker was formerly marketed as *Tastyworks*)
- [ ] Parallel options analyst team (runs alongside existing stock analysis)
- [ ] Volatility analysis agent — IV Rank, IV Percentile, volatility skew, VRP, IV surface
- [ ] Greeks analysis agent — Delta, Gamma, Theta, Vega + 2nd order (Charm, Vanna, Volga/Vomma)
- [ ] Options flow / unusual activity agent — volume vs OI, sweeps/blocks, smart money detection
- [ ] Gamma exposure (GEX) analysis agent — dealer positioning, gamma walls, flip zones, call/put walls
- [ ] Strategy selection agent — recommends multi-leg strategies based on IV environment and directional bias
- [ ] Position sizing and risk/reward agent — max profit/loss, breakeven, probability of profit
- [ ] Options debate phase — bull/bear debate on options thesis with configurable rounds
- [ ] Options portfolio manager — synthesizes all analysis into final recommendation
- [ ] Output: specific contract recommendations (strikes, expirations, legs) + alternative ranges
- [ ] Output: transparent reasoning chain showing why each strategy was selected
- [ ] **Tastytrade** methodology integration — 45 DTE entry, 21 DTE management (close or roll per rules engine), 50% profit target rules
- [ ] SpotGamma-style GEX calculation — net GEX across strikes, Vol Trigger, Call/Put Wall levels
- [ ] MenthorQ-style composite scoring — Options Score (0-5), regime classification (long/short gamma)

### Out of Scope

- Order execution / broker integration — this is analysis only, no live trading
- Real-time streaming dashboard — batch analysis via propagate(), not live monitoring
- Backtesting engine for options strategies — backtrader exists but options backtesting is a separate project
- Historical IV surface storage — would need ORATS subscription, defer to future
- 0DTE strategy support — requires real-time data infrastructure not yet in place
- Mobile/web UI — CLI and Python API only

## Context

- TradingAgents v0.2.2 is a mature multi-agent stock analysis framework built on LangGraph
- The existing architecture supports parallel agent teams — the options module plugs in as a new team
- Data layer already supports vendor routing with automatic fallback — Tradier and **Tastytrade** fit as new vendors
- Agent factory pattern (create_*() closures) is well-established and should be followed
- The codebase uses a 5-tier rating scale (BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL)
- Tradier provides Greeks via ORATS (institutional quality, hourly updates) — yfinance has NO Greeks
- **Tastytrade** API provides real-time streaming Greeks via DXLink WebSocket
- MenthorQ has no public API — their methodology must be replicated using raw options data
- SpotGamma API available at Alpha tier ($199+/mo) — methodology can be replicated from their published formulas
- **Tastytrade** rules engine (IVR thresholds, DTE rules, profit targets) provides a proven decision framework

## Constraints

- **Data providers**: Tradier (REST, 120 req/min, Greeks hourly) and **Tastytrade** (REST + DXLink WebSocket streaming) as primary options data sources
- **No 2nd-order Greeks from API**: Charm, Vanna, Volga must be calculated from 1st-order Greeks + Black-Scholes
- **Architecture**: Must follow existing patterns — agent factory functions, vendor routing, LangGraph StateGraph
- **Python**: >=3.11 (baseline for the options module and the community **tastytrade** SDK in Phase 10; aligns with `requires-python` in `pyproject.toml`)
- **LLM provider agnostic**: Options agents must work with any supported LLM provider via the client factory

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| New parallel team (not extending existing analysts) | Options analysis is domain-specific with unique data needs; clean separation allows independent development and optional activation | — Pending |
| Tradier + Tastytrade as data providers | Tradier provides ORATS-quality Greeks and IV; Tastytrade provides real-time streaming; both have Python-friendly APIs | Phase 1 ✓ (Tradier) |
| Replicate MenthorQ/SpotGamma methodology rather than subscribe | No public API from MenthorQ; SpotGamma API is expensive; core formulas (GEX, DEX, Vanna/Charm exposure) are documented and calculable | — Pending |
| Multi-leg strategy output | User explicitly wants spreads, straddles, iron condors, butterflies — not just single-leg calls/puts | — Pending |
| Dual output format (specific contracts + ranges) | Specific contracts as primary recommendation with alternative ranges for flexibility | — Pending |
| Tastytrade methodology as rules engine | Proven statistical edge: IVR-based strategy selection, 45 DTE entry, 21 DTE management, 50% profit targets with published win rates | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-29 after Phase 1 completion*
