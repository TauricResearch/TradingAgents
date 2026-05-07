# TradingAgents Fork — TODOS

## Polymarket Phase A

### TODO: Polymarket backtesting harness
**What:** Script to run `propagate_market()` against already-resolved Polymarket
markets and measure accuracy vs. resolution outcomes.
**Why:** The 55% accuracy success criterion cannot be measured any other way.
Without this, Phase A quality is unverifiable at ship time.
**Context:** Gamma API exposes `resolved` markets with final YES/NO outcomes.
Sample 50-100 resolved markets, run the research pipeline, compare direction
to outcome. This is the only honest eval for Phase A.
Start: `tradingagents/scripts/backtest.py`
**Effort:** ~1 day (human) / ~30 min (CC)
**Depends on:** Phase A data layer + `propagate_market()` complete

---

### TODO: Gamma API retry/backoff
**What:** Add `tenacity` retry + exponential backoff to all Gamma REST calls
in `tradingagents/dataflows/polymarket_data.py`.
**Why:** Gamma rate limits are undocumented. Without retry logic, a 429 produces
a silent empty result or an exception dump with no user-visible message.
**Context:** `@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))`
covers the common case. Add a clear error log on final failure.
**Effort:** 15 min
**Depends on:** nothing (add at any point)

---

### TODO: Block negative-EV trades pre-fill
**What:** In `run_polymarket.py`, after the trader produces a direction, refuse
to fill if the trade is guaranteed to lose money even when the prediction is
correct, due to the 2% Polymarket fee on winning resolutions.
**Why:** Observed in the live Sonnet batch: BUY_NO on a 0.2 cent YES market
means buying NO at 99.8 cents. If NO wins, payout is $1.00 minus 2% fee =
$0.98 per contract. Cost was $1.00 per contract, guaranteed -$2 loss on a
100-contract buy even with a correct call. Sonnet's reasoning was structurally
sound but ignored fee math.
**Context:** Per contract, expected_pnl_if_win = (1.00 - vwap) - fee_per_contract.
If `(1.00 - vwap) <= fee_per_contract`, the trade is a guaranteed loser when
correct. Add an EV check after `simulate_fill`: if `(payout - filled_usd -
fee_estimate_if_win) <= 0`, log "NEGATIVE_EV_BLOCKED" and skip the fill log
entry. A more sophisticated version uses the bot's confidence vs. the market
price to compute true expected value, but the floor case (correct = loss) is
the fast obvious win.
**Effort:** 15 min
**Depends on:** nothing

---

## Polymarket Phase B

### TODO: Binary risk model (Kelly criterion sizing)
**What:** New position-sizing module for Polymarket binary contracts, replacing
the `stop_loss_pct`-based formula in `trade-poc/src/risk/engine.ts`.
**Why:** YES/NO contracts resolve at $1 or $0 — there is no stop-loss to set.
The existing `RISK_PER_TRADE_PCT / stop_loss_pct` formula produces nonsense.
**Context:** Kelly criterion: `f* = (b*p - q) / b`
- `p` = estimated YES probability (from `confidence` in `PolymarketDecision`)
- `q` = 1 - p
- `b` = (1 / yes_price_at_analysis) - 1
Cap at `MAX_POSITION_PCT`. Confidence threshold still applies.
Start: `trade-poc/src/risk/binary.ts`
**Effort:** ~0.5 day (human) / ~15 min (CC)
**Depends on:** Phase A `PolymarketDecision` schema (needs `confidence` + `yes_price_at_analysis`)
