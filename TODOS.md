# TradingAgents Fork — TODOS

## Polymarket Phase A

### DONE: Polymarket backtesting harness
Shipped 2026-05-08 as `scripts/backtest.py`. Pulls resolved markets from
gamma, runs `propagate_market()` against them, compares direction to
outcome. Includes `--end-date-max` for cross-domain testing.
Findings: `docs/PHASE_A_FINDINGS.md`.

### DONE: Block negative-EV trades pre-fill
Shipped 2026-05-08 (commit `d7ae4d9`). `is_economic_when_correct(fill)`
in `tradingagents/exchange/paper_fill.py`. Wired into `run_polymarket.py`
so guaranteed-loser trades log "NEGATIVE_EV_BLOCKED" and don't persist.

---

### TODO: Gamma API retry/backoff
**What:** Add `tenacity` retry + exponential backoff to all Gamma REST calls
in `tradingagents/dataflows/polymarket_data.py`.
**Why:** Gamma rate limits are undocumented. Without retry logic, a 429 produces
a silent empty result or an exception dump with no user-visible message.
**Context:** `@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))`
on transient failures only (network errors, 429, 5xx). Don't retry 4xx
client errors.
**Effort:** 15 min
**Depends on:** nothing

---

### TODO: Tighten bull/bear prompts to address drama bias
**What:** Modify the polymarket-mode bull/bear researcher prompts to push
back on cases where they reward "yes-it-happens" reasoning on dramatic
geopolitical events.
**Why:** Observed in cross-domain backtest (2026-05-08): both gpt-4o-mini
and Sonnet went BUY_YES on "Will another country conduct military action
against Iran by April 15?" (actual: NO). The bull researcher rewards
finding any news suggesting YES, even when prior probability is low.
The fix: add to the bull prompt "Be skeptical of dramatic outcomes
('war breaks out', 'leader assassinated', etc.), these are usually
correctly priced low. Argue YES only when you have specific recent
catalysts that move the probability above the historical base rate."
**Context:** Files: `tradingagents/agents/researchers/bull_researcher.py`,
`bear_researcher.py` (polymarket branch).
**Effort:** 20 min + 5-market backtest to confirm (~$0.10)
**Depends on:** nothing

---

## Polymarket Phase B

### TODO: Binary risk model (Kelly criterion sizing)
**What:** New position-sizing module for Polymarket binary contracts, replacing
the `stop_loss_pct`-based formula in `trade-poc/src/risk/engine.ts`.
**Why:** YES/NO contracts resolve at $1 or $0; there is no stop-loss to set.
The existing `RISK_PER_TRADE_PCT / stop_loss_pct` formula produces nonsense.
**Context:** Kelly criterion: `f* = (b*p - q) / b`
- `p` = estimated YES probability (from `confidence` in `PolymarketDecision`)
- `q` = 1 - p
- `b` = (1 / yes_price_at_analysis) - 1
Cap at `MAX_POSITION_PCT`. Confidence threshold still applies.
Start: `trade-poc/src/risk/binary.ts` or as Python in `tradingagents/exchange/`.
**Effort:** ~0.5 day (human) / ~15 min (CC)
**Depends on:** Phase A `PolymarketDecision` schema (already exists), regulatory
review for real-money execution, py-clob-client wallet integration.
