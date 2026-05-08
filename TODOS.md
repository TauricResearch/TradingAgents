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

### DONE: Drama-bias prompt fix
Shipped 2026-05-08 (commit `b1ee146`). Added BASE-RATE SKEPTICISM clause
to the trader synthesis prompt in `propagate_market()`. A/B test on the
same 10 cross-domain markets: 67% accuracy -> 88.9% accuracy. Surgical
flip on the two drama-bias markets (Iran military action, Trump
ceasefire end), no regressions on previously-correct calls.

Implementation lives in the trader prompt rather than the bull/bear
prompts: bull's job is to find the strongest YES case; weakening the
bull would degrade input quality. The trader is the right layer for
the calibration check.

---

### TODO: Investigate quote-prediction failure mode
**What:** Sonnet (and mini) wrongly predicted "Trump praise Allah by
Apr 15" as NO when actual was YES. Quote-prediction markets are a
distinct failure mode from drama-bias.
**Why:** The bot has no information advantage on whether a person
will say a specific word in a specific upcoming interview. It should
either default to base-rate (prior frequency Trump used the word) or
HOLD.
**Context:** Add a clause to the trader prompt: "for quote-prediction
markets ('will X say Y'), default to the historical frequency the
person has used the word in similar contexts. If you have no base
rate, prefer HOLD."
**Effort:** 15 min + same A/B 10-market test
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
