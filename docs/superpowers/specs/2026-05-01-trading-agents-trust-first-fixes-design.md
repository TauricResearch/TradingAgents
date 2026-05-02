# Trading Agents — Trust-First Fixes Design

**Date:** 2026-05-01
**Source incident:** run `01KQHDVJB2R19S4D7Z7Z6DP9F7` (2026-05-01 daily) — failed at `pm_decision_postcheck` with cash adequacy violation; review surfaced silent correctness bugs (regime drift, RM hallucinations) and observability gaps (truncated decision payload, broken telemetry counters).

## Goal

Land six fixes across two parallel streams that, together, make the daily flow:

1. **Trust its outputs** — analytical layers cannot drift from canonical inputs (regime), and downstream layers cannot fabricate numbers that contradict upstream layers (RM ↔ fundamentals).
2. **Survive its failures** — when a postcheck rejects a decision, the decision is persisted and inspectable; cash-floor violations are auto-rescaled deterministically rather than hard-failing.
3. **Be debuggable** — full decision payloads in event log, accurate per-run telemetry counters.
4. **Be cheaper** — PM latency under 2 minutes (currently ~9).

Prioritization lens: **trust-first**. Silent correctness bugs are more dangerous than hard failures; address them first.

## Non-goals

- Re-architecting the analyst chain or graph topology beyond a single new `rescale_buys` node.
- Changing the fundamentals analyst output shape (stays markdown; the consistency guard parses what's there).
- Reconciling the multi-source macro regime computation itself; we just route the canonical brief everywhere.
- General PM prompt rewrite beyond the constraints needed for #1 and #6.

## Decisions

| # | Decision | Choice |
|---|---|---|
| Q1 | Priority lens | Trust-first (B): correctness before observability before perf |
| Q2 | Regime propagation | B then A: ship fail-loud assertion first, follow up with canonical routing |
| Q3 | RM↔fundamentals guard action | A with C fallback: re-prompt RM once on contradiction, hard-fail on second offense; low-confidence claims downgrade to flag-only |
| Q4 | Cash ceiling enforcement | B: prompt ceiling for the LLM's benefit + new deterministic `rescale_buys` node between `cash_sweep` and `pm_decision_postcheck` |

## PR map

Two streams, seven PRs. Streams are independent; within a stream, PRs are sequential.

**Stream A — Correctness:**
- PR-A1: Regime drift assertion (#2a)
- PR-A2: RM↔fundamentals numeric guard (#3)
- PR-A3: Canonical regime routing (#2b)

**Stream B — Safety & observability:**
- PR-B1: Decision snapshot + lift event-log truncation (#4)
- PR-B2: Cash ceiling in prompt + `rescale_buys` node (#1)
- PR-B3: run_log aggregator fix (#5)
- PR-B4: PM latency (#6)

**Suggested merge order (solo dev):** B1 → B3 → A1 → B2 → A2 → A3 → B4. Rationale: observability first so the next failure is debuggable, then run-killer, then correctness, then perf. PR-B2 lands before PR-B4 so the latency work targets the final prompt shape.

## Per-PR specifications

### PR-B1 — Decision snapshot + lift event truncation

**Scope.** Persist `portfolio_decision_snapshot.json` from inside `make_pm_decision` before returning state, so postcheck failures don't black-box the decision. Lift the ~300-char message-length cap that's clipping the PM result in the event log.

**Files.**
- `tradingagents/graph/portfolio_setup.py` — at the end of the `make_pm_decision` node body, write the decision JSON to `<run_path>/portfolio_decision_snapshot.json` using the existing report-store handle. Write must happen before any return path that could fail downstream.
- `agent_os/backend/services/event_mapper.py` — locate the message-length cap; whitelist `make_pm_decision` `result` events (or remove the cap for any `result` event whose payload is structured JSON).

**Acceptance test.** Reproduce the postcheck failure (oversize buys against a $100K NAV with `min_cash_pct=0.10`). After failure: assert `portfolio_decision_snapshot.json` exists at the run path with full `sells/buys/holds` arrays; assert the event-log entry for `make_pm_decision` contains the full JSON with no trailing `…` truncation marker.

### PR-B3 — run_log aggregator fix

**Scope.** `run_log.jsonl` summary writes `llm_calls=0, tokens_in=0, vendor_calls=0` despite many calls happening. Find the aggregator, fix the source of zeros (likely a counter scope mismatch or an event-tag filter that no longer matches what nodes emit).

**Files.** Likely `agent_os/backend/services/run_helpers.py` or the run-finalization path in `agent_os/backend/services/langgraph_engine.py`. Start by `grep -rn '"llm_calls"\|tokens_total' agent_os/`.

**Acceptance tests.**
- Unit: feed a fake event stream with 5 LLM events (each with `tokens_in/tokens_out`); invoke the summarizer; assert `llm_calls==5` and `tokens_total==sum`.
- Integration: existing portfolio smoke pytest must show summary counters > 0 after run.

### PR-A1 — Regime drift assertion

**Scope.** Post-node validator after Market Analyst: parse the regime label/score the analyst wrote and compare against the canonical regime in state. Raise on mismatch.

**Files.**
- `tradingagents/graph/_graph_utils.py` — add `assert_regime_consistent(analyst_output: str, canonical_regime: dict) -> None` using regex for `(RISK-ON|RISK-OFF|TRANSITION)` and `[+-]?\d+/6`.
- `tradingagents/graph/setup.py` — wire the helper into the Market Analyst exit edge (or a dedicated post-validator node).

**Acceptance test.** Unit test with two synthetic Market Analyst outputs (one "RISK-ON +5/6", one "TRANSITION +2/6") against state with canonical "RISK-ON +5/6"; assert the first passes silently, the second raises with both values in the message. Replay the QCOM Market Analyst snapshot from run `01KQHDVJB2R19S4D7Z7Z6DP9F7` and confirm the assertion fires with "RISK-ON +5/6 != TRANSITION +2/6".

### PR-B2 — Cash ceiling in prompt + `rescale_buys` node

**Scope.** Two parts.

(1) Inject `max_total_buy_notional = available_cash - min_cash_pct * NAV` as an explicit number into the PM prompt and into the response-schema description. Today's prompt only states the percentage cap; we add the resolved dollar number so the LLM can sanity-check itself.

(2) Add a new graph node `rescale_buys` between `make_pm_decision` and `cash_sweep` that proportionally scales every PM-issued BUY's `shares` down (rounded down to integers) until the cash floor holds. Final order: `make_pm_decision → rescale_buys → cash_sweep → pm_decision_postcheck`. Rationale: `cash_sweep` adds an SGOV cash-equivalent order from residual cash, which is a deliberate cash-park — it must NOT be subject to proportional rescaling, otherwise the sweep would compete with PM buys. Postcheck stays as the safety net for any other invariants.

**Files.**
- `tradingagents/graph/portfolio_setup.py` — add `_make_rescale_buys_node()`, mirroring postcheck's projection math at lines 480–491. Insert into workflow: `workflow.add_edge("make_pm_decision", "rescale_buys")`, `workflow.add_edge("rescale_buys", "cash_sweep")`, `workflow.add_edge("cash_sweep", "pm_decision_postcheck")`. Update the PM prompt builder to inject the notional ceiling.

**Rescale algorithm.**
```
projected_cash, total_buy_notional = project_basket(decision, holdings)
min_required_cash = projected_total_value * min_cash_pct
if projected_cash >= min_required_cash:
    return decision  # no-op
excess = min_required_cash - projected_cash
scale = max(0.0, (total_buy_notional - excess) / total_buy_notional)
for buy in decision.buys:
    buy.shares = int(math.floor(buy.shares * scale))
emit_event("rescale_buys", original=..., rescaled=..., scale=scale)
return decision
```
If `scale == 0` (all buys eliminated), return the empty-buys decision unchanged; postcheck still validates other invariants.

**Acceptance tests.**
- Synthetic decision with buy notional $20K above the floor on a $100K NAV: rescale node reduces shares so the floor is met (within $1 rounding); postcheck passes.
- Decision already within budget: rescale is a no-op; output equals input bit-for-bit.
- Replay run `01KQHDVJB2R19S4D7Z7Z6DP9F7` PM decision: rescale brings projected_cash from $2,687.88 to ≥ $9,992.32; postcheck passes; `execute_trades` sees a smaller basket. Audit event records original vs rescaled basket.

### PR-A2 — RM↔fundamentals numeric guard

**Scope.** Post-Research-Manager validator: extract numeric claims from RM bullets, diff against the fundamentals report, re-prompt RM once with violations, hard-fail if violations remain. Low-confidence extractions (metric name doesn't map to fundamentals) downgrade to flag-only and surface in the report under "Numeric Consistency Warnings".

**Files.**
- New: `tradingagents/graph/_consistency_guard.py` with two pure functions:
  - `extract_numeric_claims(rm_text: str) -> list[NumericClaim]` where `NumericClaim = {metric: str, value: float, unit: Literal["%","bps","x","B","M"], direction: Literal["expansion","compression","increase","decrease",None], confidence: Literal["high","low"]}`.
  - `verify_against_fundamentals(claims: list[NumericClaim], fundamentals_text: str) -> {violations: list[Violation], flags: list[NumericClaim]}`.
- `tradingagents/graph/setup.py` — wire as a post-RM node before Trader; on high-confidence violations, route back to RM with a corrective prompt fragment containing the violations list.
- RM prompt — append: "If the input contains a `consistency_violations` field, your next response must address each violation listed there with the corrected number from the fundamentals report or remove the claim entirely."

**Extraction strategy.** Regex over RM bullet text for `[+-]?\d+(\.\d+)?\s*(%|bps|x|B|M)\s*(YoY|QoQ|year-over-year|quarter-over-quarter)?` paired with the metric noun-phrase preceding it (window: prior 60 chars). Tolerance: ±50bps for percentages, ±5% relative for dollar magnitudes. Confidence is "low" if the metric noun-phrase has no entry in the fundamentals summary table; "high" otherwise.

**Failure mode.** If the corrective re-prompt still emits violations, the node raises with all unresolved violations listed. The trading graph for that ticker fails fast; other tickers continue.

**Acceptance tests.**
- Replay ET RM output from run `01KQHDVJB2R19S4D7Z7Z6DP9F7`: extractor returns the "+3.8% EBITDA margin expansion", "−320bps net leverage decline", "+14.2bps FCF conversion improvement" claims; verifier flags all three as high-confidence violations against the actual fundamentals report (margin compressed, debt up $6.12B, FCF turned negative).
- With a mocked RM that corrects on re-prompt: run continues, second-pass output replaces first-pass.
- With a mocked RM that repeats the same bad numbers: run hard-fails with the three violations listed.
- Low-confidence path: feed an RM claim referencing "DCF coverage ratio +1.2x" (not in fundamentals); guard flags but does not block, and the warning surfaces in the persisted report.

### PR-A3 — Canonical regime routing

**Scope.** Pass the same `macro_regime_brief` that `make_pm_decision` consumes into the trading graph's per-ticker run, and rewrite the Market Analyst prompt to read the regime from input rather than infer it. PR-A1's assertion should stop firing under normal operation after this lands.

**Files.**
- Trading graph state schema (search for `class TradingState` or equivalent in `tradingagents/graph/`) — add `macro_regime_brief: str` field.
- `agent_os/backend/services/langgraph_engine.py` — when invoking the trading graph per ticker, populate `macro_regime_brief` from the same source the portfolio graph uses (likely `agent_os/backend/services/scanner_context.py` or a shared run-scoped fixture).
- `tradingagents/graph/setup.py` — Market Analyst prompt: replace "classify the macro regime" instructions with "the canonical macro regime is `{macro_regime_brief}`; contextualize the ticker against it."

**Acceptance test.** Run trading graph for QCOM with the canonical brief that emitted "RISK-ON +5/6" — Market Analyst output's regime line is exactly "RISK-ON +5/6", not "TRANSITION +2/6". PR-A1's assertion does not fire across a smoke run of all daily-flow tickers.

### PR-B4 — PM latency

**Scope.** Reduce kimi-k2.6 PM call from ~520s to <120s. Two-step: prompt diet first (low risk), model swap if still slow.

**Files.** PM prompt construction in `tradingagents/graph/portfolio_setup.py` and the PM agent definition (wherever the model is bound — possibly `tradingagents/default_config.py` or a portfolio-specific config).

**Step 1 — prompt diet.** Strip prose framing. Replace inline pasted briefs with a `# INPUTS` block of three labeled JSON sections (macro, micro, candidates), and require JSON-only response matching the existing schema. No streaming yet.

**Step 2 — if still > 120s, model swap.** Switch the PM node to `claude-sonnet-4-6` (per-node override; rest of graph unchanged).

**Acceptance test.** Same portfolio inputs as a recent successful run.
- After Step 1: PM latency < 120s; decision matches the prior run on direction (BUY/HOLD/SELL) for every ticker and on share counts within ±10%.
- After Step 2 (if needed): PM latency < 60s with the same decision-quality bar.

## Risks and open questions

- **Extractor false positives in PR-A2.** Regex extraction over free-form RM bullets is the riskiest piece. The flag-only fallback for low-confidence claims is the safety valve — if the extractor proves noisy in practice, ratchet more claim shapes from "high" to "low" confidence rather than weakening the hard-fail behavior.
- **Rescale fairness in PR-B2.** Proportional scaling treats all buys as equally optional. If the candidate ranking implies priority (e.g., highest-conviction first), we may want to drop low-conviction buys entirely before scaling the rest. Out of scope for this round; revisit if PR-B2 proves blunt.
- **PM model swap thesis risk in PR-B4.** Sonnet 4.6 is faster but may have a different decision profile than kimi-k2.6 on the same inputs. The acceptance test pins direction + ±10% sizing as the floor; tighten if drift is observed in the first week.
- **Coupling between PR-A1 and PR-A3.** A1 ships a detector that A3 makes obsolete. That's intentional — A1 is value in the gap, and after A3 it becomes a regression guard. Don't delete A1's assertion when A3 lands.

## Acceptance for the design as a whole

After all seven PRs land:
1. Replaying run `01KQHDVJB2R19S4D7Z7Z6DP9F7`'s inputs produces a decision whose buys honour the cash floor without postcheck failure.
2. The QCOM Market Analyst regime output matches the canonical macro brief.
3. The ET Research Manager output contains no numeric claims that contradict the fundamentals report; if it tries, the run fails fast with named violations.
4. PM latency for the same inputs is < 120s.
5. Run telemetry counters (`llm_calls`, `tokens_total`, `vendor_calls`) are non-zero and accurate.
6. On any future postcheck failure, `portfolio_decision_snapshot.json` exists and the event log contains the full PM decision JSON.
