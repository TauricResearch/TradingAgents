# Koral Equities — First Research-Cycle Audit

**Date:** 21 October 2026 close / reports generated later that evening

**Status:** Research evidence; **not** an execution approval. Original source reports: `NVDA 2026-10-21 Overweight` (23 pages) and `META 2026-10-21 Overweight` (23 pages). The existing £10,000 GBP paper ledger is unchanged by this document.

## Definitions

- **Buy:** directional recommendation to increase/establish exposure; execution may still be conditional.
- **Overweight:** target an allocation **above a named neutral/standard portfolio weight**, not an instruction to buy next open.
- **Hold:** maintain target exposure.
- **Underweight:** target allocation below the reference weight, not automatically an instruction to short or liquidate entirely.
- **Sell:** lower or exit exposure based on an actual portfolio instruction.

A production contract must specify a reference allocation, trigger and sizing. Rating strings alone are not executable instructions.

## NVDA audit (report pp. 18–23)

- 21 Oct close was **$221.97**.
- Research and portfolio managers favoured a measured **Overweight** based on reported operating growth, liquidity and longer-term trend, while recognising weak near-term momentum and unconfirmed news-to-revenue causality.
- **Portfolio manager (p. 23): do not buy the unconfirmed rebound immediately**. Wait for a close **above $226.87** and follow-through, ideally a second confirming close. Begin roughly half a standard allocation and add increments subject to conditions.
- Risk-review reference: **$212.16**; a break below **$214.13** prompts reassessment. Time horizon: through next results.
- **Simulation mismatch:** `run_agents` queues `Overweight` as `BUY` at the next opening regardless of the condition. At the initial $221.97 close, its default stop is `221.97 × 0.92 = $204.21`, not the research risk reference.

## META audit (report pp. 18–23)

- 21 Oct close was **$697.52**; the report's news/sentiment agents discussed a Q3 revenue beat, after-hours reactions, reported legal exposure, capital expenditure and possible share issuance. It **did not** have verified detailed Q3 earnings-release figures/reconciliation; it called for further validation.
- **Portfolio manager (p. 23): no immediate purchase at the close.** After price reclaims **$716.08**, begin at most a quarter of a standard allocation, with further confirmation around **$725.59** and improvements in momentum/data quality.
- Risk-review reference: **$687.85**. Holding horizon: **3–6 months**.
- **Simulation mismatch:** current `Overweight` label queues `BUY` next open with stop `697.52 × 0.92 = $641.72`, disregarding the research entry gate, staged sizing, and the research's explicit risk level. The paper engine's default time exit after 20 sessions also differs from the 3–6-month research horizon.
- Special concerns: post-earnings gap/published-price timing; source-provenance gaps; unusually large reported legal matter; discrepancies between financial statement and headline snapshot series.

## Decision

**Do not approve label-only paper recommendations as faithful execution of the investment committee.** The first-cycle ratings and queued orders are evidence of a working pipeline, not a validated strategy. Do not connect real money.

### Required remedy (separate version, not silently applied to existing portfolio)

1. Agents emit a validated structured `TradeIntent`: ticker, decision-as-of, side, absolute target position/neutral weight, entry type, trigger, confirmation bars, expiry, stop reference, holding horizon, confidence/data limitations and unique ID.
2. Deterministic engine rejects missing, contradictory or contingent-but-unresolved instructions; no direct `Overweight → BUY` shortcut.
3. Queue conditional intents rather than market orders; evaluate only on eligible, completed future data. No same-day/post-earnings lookahead or retroactive fills.
4. Independent stop-gap modelling, sector/cluster allocation limits, compatible earnings blackout policy and a cash/exposure ledger.
5. Maintain an immutable baseline run and add the corrected strategy as a separate pre-registered experiment, with validation before adoption.
6. Before any subsequent scan processes the currently queued NVDA/META orders, review/cancel them through an auditable operator action; **this audit does not cancel orders or change an existing paper account**.

Attribution and original framework licence are preserved in `UPSTREAM_ATTRIBUTION.md` and `LICENSE`.
