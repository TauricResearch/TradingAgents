# ADR 027: Robust Pipeline with Fail-Loud on Bad Inputs

**Date**: 2026-04-25
**Status**: Proposed (umbrella ADR)
**Tags**: [reliability, decision-integrity, robustness, fail-loud]
**Supersedes / consolidates**: ADR 023, 024, 025
**Related**: ADR 017 (LLM policy fallback), ADR 011 (vendor fail-fast)

## Context

Two failure modes have been observed in production runs:

1. **Brittleness from transient faults** — provider 404 / 429,
   network blips, malformed vendor payloads, single-ticker yfinance
   shape variance — historically crashing the whole run.
2. **Silent corruption from wrong-but-plausible inputs** — `cash=0,
   total_value=null` accepted by the PM, malformed kimi-k2 JSON
   absorbed by the structured-output fallback, news claims
   referencing sources that aren't in the evidence store.

The earlier instinct was to add fallbacks to mask both. That is the
wrong answer for #2: continuing on wrong inputs produces an output
that **looks like a real decision** but isn't grounded in valid
reasoning. Run `01KQ05XQ07FCBTNSEFJN6EZCNY` exhibited exactly this
class of failure.

The right model has two layers:

- A **robustness layer** that absorbs transient faults so the
  pipeline rarely fails for the wrong reason.
- A **fail-loud layer** that refuses to continue when inputs or
  outputs are genuinely wrong, even if a synthetic continuation is
  technically possible.

## Principle

> The system is robust, not permissive.
> It tolerates transient faults; it does not tolerate wrong inputs.
> **It is not important to continue if it is wrong.**

## Decision

Adopt a two-layer contract for every node, with explicit ownership.

### Layer A — Robustness (always present)

Every node, regardless of category, must implement:

| Mechanism | Purpose | Reference |
|---|---|---|
| Bounded timeout | No hung node, ever | `quick/mid/deep_think_llm_timeout` per ADR 017 |
| Per-tier model fallback | Survive provider policy / 429 | ADR 017 |
| Retry on transient errors | Survive flaky network | client-level retry in `openai_client.py` |
| Idempotent persistence | Survive partial reruns | `check_and_load_report` + `save_node_report` |
| Schema/type validation on inputs | Refuse impossible state early | new (this ADR) |
| Structured error payload | Diagnose without prose-parsing | ADR 025 |

Layer A failures are **caught and retried**. They do not propagate
unless retries are exhausted.

### Layer B — Fail-loud (decision-effecting nodes only)

Once Layer A is exhausted, the node either succeeds with valid output
or **raises**. Decision-effecting nodes may not emit a synthetic
result.

| Node | Layer-B contract |
|---|---|
| `research_manager.py` | Raise on timeout/empty/parse after Layer-A retries. Remove `build_research_manager_fallback`. |
| `trader.py` | Raise on empty plan or LLM failure (existing entry-drift guardrail already raises — extend to the LLM path). |
| `portfolio_manager.py` (trading graph) | Raise on empty content. Remove the `risk_synthesis_structured`-derivation fallback. |
| `pm_decision_agent.py` | Raise on schema failure. Remove the plain-LLM + `extract_json` fallback. |
| `macro_summary_agent.py` | Raise on missing/error-only `scan_summary`. Remove the `"NO DATA AVAILABLE"` sentinel. |
| `risk_synthesis.py` | Already raises — reference behavior. |
| `pm_decision_postcheck` (new) | Raise on cash-adequacy / position-cap / sector-cap / orphan-hold violation. Never clamp. |
| `portfolio_integrity_guard` (new) | Raise on `total_value=None`, conservation breach, mixed currency, or `(cash=0 AND no holdings)`. |
| News Fact Checker | Raise (via structured abort) on missing evidence rather than silently dropping claims. |

Non-decision-effecting nodes (analysts producing context, scanner
summarizers, memory writes, observability) keep their deterministic
fallbacks — their output is consumed by a decision node that itself
follows Layer-B rules.

### Concrete invariants (must always hold)

These are graph-level invariants that, when violated, must raise
rather than degrade:

1. **Cash conservation.** `total_value == cash + Σ holdings.market_value`
   (within $1 tolerance) at every node boundary.
2. **Buy affordability.** `Σ buy.shares × buy.price <= cash × (1 - min_cash_pct)`.
3. **Position-cap.** Every buy fits the configured `max_position_pct`.
4. **Sector-cap.** Aggregate per-sector ≤ `max_sector_pct`.
5. **Hold/sell reference.** Every `hold.ticker` / `sell.ticker`
   exists in current holdings.
6. **Decision-rationale grounding.** Every PM `buy.ticker` has a
   completed deep-dive entry in `prioritized_candidates`.
7. **Evidence grounding.** Every news-claim source exists in
   `NewsEvidenceStore` for the active `run_id`.
8. **Schema integrity.** Every structured-output Pydantic model
   round-trips without lossy coercion (no `\nc` for `%`).

Each invariant is enforced at the node where it can first be
checked, raising on violation.

### Robustness additions to be implemented

Even with fail-loud, the robustness layer can be deepened:

- **Per-node circuit breakers.** If `pm_decision_agent` raises 3
  times in a 24 h window, alert and pause auto-runs rather than
  retry blindly.
- **Wall-clock budget per node.** A hard ceiling (e.g. 300 s for
  any single node) guarantees the 38-min run cannot become a
  60-min run without surfacing the regression.
- **Output-content sanitizer.** Before a structured-output result
  reaches downstream consumers, scrub for the kimi-k2 `\nc`
  artifact and reject (Layer-A retry, then Layer-B raise).
- **Per-vendor health probes.** Cheap pre-flight against critical
  providers; surface degradation as a structured warning, not as a
  graph crash.
- **Idempotent partial-rerun resume.** When the graph raises,
  `setup_graph_from(start_node)` should be the documented next
  step for the operator, with run-events log pointing at the exact
  failure node.

### What "more robust" does NOT mean

- It does **not** mean adding fallbacks to decision-effecting nodes.
- It does **not** mean clamping or shrinking PM proposals to fit
  constraints.
- It does **not** mean substituting a default verdict on LLM
  failure.
- It does **not** mean continuing the run when the portfolio loader
  returned a stub.

If the inputs are wrong, the right answer is to fix the inputs and
rerun from the checkpoint.

## Consequences

- The pipeline rarely fails for transient reasons (Layer A absorbs
  them) but always fails on wrong reasoning (Layer B raises).
- Audit trails become trustworthy — every persisted decision
  represents a real model verdict against valid inputs.
- Operators get actionable stack traces pointing at the actual
  failure (loader, schema, evidence store) instead of plausible-
  looking outputs to debug.
- The cost is run mortality on certain failure classes that today
  silently produce a synthetic decision. This is the trade-off.

## Migration

ADRs 023, 024, 025, 026 are the concrete deliverables under this
umbrella:

| ADR | Scope |
|---|---|
| 023 | Remove fallbacks from decision-effecting nodes |
| 024 | Add `portfolio_integrity_guard` + `pm_decision_postcheck` |
| 025 | Replace `[CRITICAL ABORT]` string-prefix with structured `abort_signal` |
| 026 | Wire `record_outcome()` so memory feedback loop closes |

The robustness deepening (circuit breakers, wall-clock budgets,
output sanitizer, vendor health probes) is tracked here as the
follow-up scope of this umbrella ADR; individual implementations
can reference 027 directly.

## Out of scope

- Auto-resume after a Layer-B failure. Resume tooling is an
  operator workflow, not an automatic behavior — auto-resume on a
  structured-abort would re-introduce the "continue on wrong
  inputs" pattern this ADR rejects.
