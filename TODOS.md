# TradingAgents Fork — TODOS

## Next steps (recommended order)

The pipeline is calibrated, secure (prompt-injection + rate-limited),
and clean (single io_utils helper). Three open work items, in priority
order:

1. **Score the live Welsh/UK paper positions when they resolve.**
   Zero new code. Run `python scripts/score_fills.py --verbose` once
   the markets close in the next 24-72h and append the result to
   `docs/PHASE_A_FINDINGS.md`. This is the only fully look-ahead-free
   signal we can get without writing more code, since those events
   resolve AFTER the LLM training cutoff.

2. **Quote-prediction prompt fix** (Phase A polish).
   Trader prompt addition for "will X say Y" markets — default to the
   speaker's historical word frequency or HOLD. Re-run the same 10
   cross-domain markets as the drama-bias A/B. Effort: ~15 min CC,
   target: no regression on the 88.9% baseline + flip on Trump-Allah.
   See "TODO: Investigate quote-prediction failure mode" below.

3. **50-market balanced backtest** (Phase A statistical claim).
   Current 30-market sample is class-imbalanced (28 NO / 2 YES). Need
   a sample with at least 15-20 YES_WINS markets to claim BUY_YES
   discrimination beyond drama-bias. Use `--end-date-max 2026-03-01`
   and filter for `volume >= 5000` to avoid lottery-ticket markets.

4. **Phase B Kelly criterion sizing** (only after #1-3 land).
   See "Polymarket Phase B" section below. Blocked on regulatory call
   for jurisdiction (US persons cannot trade on Polymarket directly)
   and wallet integration via `py-clob-client`.

---

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

### DONE: Gamma API retry/backoff
Shipped 2026-05-08. `_http_get_with_retry()` in
`tradingagents/dataflows/polymarket_data.py` wraps Gamma REST calls with
tenacity retry on transient failures (network errors, 429, 5xx). 4xx
client errors are not retried.

---

### DONE: Prompt-injection sanitiser + daily call rate limiter
Shipped 2026-05-08 (commit `a1e8748`). `tradingagents/agents/utils/sanitize.py`
neutralises 7 classes of prompt-injection patterns in untrusted Exa news
text before it reaches the bull/bear/trader prompts.
`tradingagents/exchange/rate_limiter.py` caps daily LLM call volume
(default 100, override via `POLYMARKET_DAILY_CALL_LIMIT`) to bound
runaway-spend risk. State persisted at `~/.tradingagents/polymarket/rate_limit.json`.

---

### DONE: io_utils migration cleanup
Shipped 2026-05-08 (commit `b750ac0`, PR #1). All three Polymarket
scripts (`run_polymarket.py`, `score_fills.py`, `backtest.py`) now use
`tradingagents.exchange.io_utils.POLYMARKET_OUTPUT_DIR` and `append_jsonl`
instead of local copies. Net -15 lines, single source of truth for the
output dir and JSONL format.

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
