# ADR 023: No Silent Fallback on Decision-Effecting Nodes

**Date**: 2026-04-25
**Status**: Proposed
**Tags**: [reliability, decision-integrity, fail-loud, pm, trader, research-manager]
**Related files**:
- `tradingagents/agents/managers/research_manager.py`
- `tradingagents/agents/trader/trader.py`
- `tradingagents/agents/managers/portfolio_manager.py`
- `tradingagents/agents/portfolio/pm_decision_agent.py`
- `tradingagents/agents/portfolio/macro_summary_agent.py`
- `tradingagents/agents/risk_mgmt/risk_synthesis.py`

## Context

The pipeline currently mixes two failure-handling contracts:

1. **Hard-fail (raise)** — already used by `risk_synthesis.py`,
   `macro_synthesis.py`, the trader's entry-drift guardrail, and
   per CLAUDE.md is the project default ("Pipeline Failures: Nodes
   will hard-crash on LLM timeouts or network errors instead of
   generating silent fallback states").
2. **Deterministic synthetic fallback** — used today by:
   - `research_manager.py::build_research_manager_fallback` —
     emits a Buy/Sell/Hold verdict on timeout.
   - `trader.py` — deterministic trade plan on LLM timeout/empty.
   - `portfolio_manager.py` — derives a rating from
     `risk_synthesis_structured` when the LLM returns empty content.
   - `pm_decision_agent.py` — falls back to plain LLM +
     `extract_json` when structured output fails.
   - `macro_summary_agent.py` — emits the
     `"NO DATA AVAILABLE - ABORT MACRO"` sentinel, which
     `pm_decision_agent.py` then converts into a synthetic
     "conservative-posture" brief.

The synthetic fallbacks produce output that **looks like a real
decision** but is not grounded in the underlying analyst chain. They
also pollute audit trails — a downstream reader cannot distinguish a
fallback verdict from a model-derived verdict without checking node
durations or sender markers.

This was visible in run `01KQ05XQ07FCBTNSEFJN6EZCNY` (2026-04-24):
the PM emitted buy orders against an empty portfolio
(`cash=0, total_value=null`) because the structured-output path
silently absorbed a malformed kimi-k2 response and the fallback
extracted the structure anyway.

## Decision

**No node whose output influences a trading or investment decision
may emit a synthetic fallback. On failure, it must raise.**

### Decision-effecting nodes (must hard-fail)

| Node | Current fallback | Required behavior |
|---|---|---|
| `research_manager.py` | `build_research_manager_fallback` (synthetic Buy/Sell/Hold) | Remove. Raise `RuntimeError` on LLM timeout/empty/parse failure. |
| `trader.py` | Deterministic trade plan on timeout/empty | Remove. Raise. (Existing entry-drift guardrail already raises — extend the same contract to LLM failure.) |
| `portfolio_manager.py` (trading graph) | Derives rating from `risk_synthesis_structured` on empty content | Remove. Raise. |
| `pm_decision_agent.py` | Plain LLM + `extract_json` on schema failure | Remove. Raise. (Add upstream retry — see below.) |
| `macro_summary_agent.py` | `"NO DATA AVAILABLE - ABORT MACRO"` sentinel | Remove sentinel. Raise on missing/error-only `scan_summary`. |
| `pm_decision_agent.py` macro-sentinel handling | Substitutes "conservative posture" brief | Remove. The sentinel will no longer reach this node. |
| `risk_synthesis.py` | Already raises | Unchanged — reference implementation. |

### Non-decision-effecting nodes (fallback still permitted)

These emit *context*, not decisions. Their output is consumed by a
downstream decision-effecting node that has its own validation, so a
deterministic fallback is acceptable:

- Analysts (Market/Social/News/Fundamentals) timeout fallback
  reports — they tag `[CRITICAL ABORT]` when truly unrecoverable,
  which routes to the terminal node anyway.
- Bull/Bear researchers timeout fallback content with `[LOW]`
  confidence — the Research Manager (now hard-fail) will refuse to
  synthesize from `[LOW]` if it chooses to.
- Scanner summarizers' `[NO_EVIDENCE]` deterministic short-circuit —
  this is a *truthful empty signal*, not a fabricated decision.
- Memory persistence (`MacroMemory.record_macro_state`,
  `ReflexionMemory.record_decision`) — best-effort; logging-only on
  failure is fine because the decision has already been made.
- Observability layers (token counting, run logs) — never block.

### Retry and fallback ownership

Hard-fail does not mean "no retry", but retry ownership must match
the current architecture.

Decision-effecting nodes own **output integrity**:

1. Invoke their configured LLM/client path.
2. Validate that the returned content is non-empty, parseable, and
   schema-valid for the node's contract.
3. On timeout, empty output, parse failure, schema failure, or other
   invalid decision output, raise `RuntimeError` with a message that
   names the node and failure class.

Decision-effecting nodes must not perform synthetic decision fallback
and must not attempt engine-level model substitution themselves. Node
closures receive an already-built LLM and do not know the full
primary/fallback model chain.

`LangGraphEngine` owns **model substitution and phase retry**:

1. Apply the existing per-tier client-level retry (`openai_client.py`).
2. For fallback-eligible failures, apply the engine-level fallback
   model substitution per ADR 017 (`run_helpers.build_fallback_config`)
   and retry the relevant scan, ticker pipeline, portfolio phase, or
   documented subgraph.
3. If the fallback path is also exhausted, raise/persist an engine
   error that includes the phase, node when known, failure class, and
   primary/fallback models tried.

This is **escalation, not duplication**. The change in this ADR is
that decision-effecting nodes raise instead of emitting a synthetic
decision; the engine remains the single owner of model fallback policy.

## Consequences

- A flaky model endpoint can crash a run instead of producing a
  deceptive decision. This is the explicit trade-off — per CLAUDE.md
  the checkpoint stays clean for UI resumption, and partial reruns
  via `build_debate_subgraph(...)` / `build_risk_subgraph(...)` can
  resume from the failed node.
- Audit trails become honest: every PM decision file on disk
  represents a real model verdict.
- Downstream consumers (`AgentOS UI`, `execute_trades`) can stop
  defending against synthetic decisions because they will not exist.
- Existing tests that mock the fallback paths must be updated to
  assert that `RuntimeError` is raised instead.

## Out of scope

This ADR does **not** change the existing `[CRITICAL ABORT]` flow
for analysts — see ADR 025 for that mechanism's structured-signal
upgrade. Analysts remain allowed to emit context-level fallback
because they are not decision-effecting in this taxonomy.

## Supersedes

Partially supersedes the implicit "deterministic fallback for decision
nodes" pattern that pre-dated PR #18 / ADR 011. Aligns the
LLM-decision layer with the data-vendor layer's fail-fast rule.
