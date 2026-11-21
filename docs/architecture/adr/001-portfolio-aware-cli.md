# ADR 001 — Portfolio-aware CLI: input/service boundary and consent

- Status: **Proposed (architecture draft)**. Selection made by Brian (human) 2026-11-12; awaiting team/instructor reconciliation. Not implementation.
- Deciders: Brian (selection), Member B (author), pending A (requirements coherence), E (governance/assembly).
- Scope: `SEL-TA-FR-001..007`, `SEL-TA-NFR-001..006`, `SEL-TA-GOV-006` (permission design contribution).
- Supersedes: none. Does not modify v2 requirements or the D1 registry (A owns).

> Estimates in this ADR are labelled **ESTIMATE** and are design judgements. No measurement or verification is claimed.

## Context

TradingAgents v0.7.1 already has an optional `--portfolio PATH` that loads a `PortfolioContext` and renders it into decision-agent prompts (`cli/main.py:50-55`, `tradingagents/portfolio.py`, `tradingagents/graph/trading_graph.py:293-307`). The selected requirements extend this into a discovery + explicit-consent + frozen-provenance + deterministic-check workflow, with distinct `NO_PORTFOLIO`/`PORTFOLIO_PROVIDED` semantics. The course additionally requires a **layered agent context** design, context assembly and compaction constraints, which this ADR records.

Constraints from the current selection (treated as fixed working decisions): CLI-only UI; `PORTFOLIO_DIR=<root>/portfolios`; `--without-portfolio`; `--portfolio-as-of`; consent behaviour; full normalized-content SHA-256 fingerprint; no silent fallback; no invented zero holdings/cash; model cannot assign checks.

## Course-required layered context (design)

| Layer | Content (bounded application context) | Source |
|---|---|---|
| Identity | Instrument/ticker + resolved identity context | `agents/context.py:build_instrument_context` |
| Standing constraints | Advisory-only role; no execution; rating vocabulary; disclaimer requirement; "no account ownership assumed" | prompts + frozen strings |
| Knowledge | Analyst reports, research/trader plans, risk debate | graph state |
| History | Memory-log lessons from prior decisions | `tradingagents/memory/` |
| State | Input mode, selected basename, as-of/basis, fingerprint (safe projection) | `RunContext` |
| Current task | The run's instruction to produce a rating + decision | node prompt |

### Context assembly pipeline (application-bound)
`deduplicate → prioritize (identity/constraints first) → budget (per-agent token cap) → compact (summarize low-priority narrative; never drop mode/snapshot identity/output authority/critical constraints) → assemble (final prompt)`.

#### Operational budget and compaction design (B3-07, F6; proposed, unmeasured)
All numbers are **proposed design values (ESTIMATE)**, not measured. C/D later verify/measure.

- **Estimator:** token counts approximated by `ceil(len(prompt_chars)/4)` (cheap, provider-agnostic; **explicitly estimated**, no guarantee against provider tokenizer; no tokenizer dependency added).
- **Per-agent context cap** `C_cap = 24,000` estimated tokens (proposed): bounds the **assembled prompt context** for one agent, not an aggregate run budget.
- **Critical reserve** `R_reserve = 4,000` estimated tokens (proposed) planned for identity + standing constraints + state/authority + frozen notice/disclaimer; never compacted.
- **Compaction threshold** `T_compact = floor(0.8 · C_cap) = floor(19,200) = 19,200`; compact when estimated context exceeds `T_compact`; hard stop at `C_cap`. (Arithmetic corrected: 0.8 × 24,000 = **19,200**, not 20,000.)
- **Protected-context overflow (actual estimate, not the constant):** let `P` be the **measured estimate of the protected layers** (identity + constraints + state/authority + notice/disclaimer) at assembly time. If `P + (minimum irreducible task/history context) > C_cap`, or more simply if `P > C_cap − C_min_task` (where `C_min_task` is the minimum needed for the current task), **fail closed** (typed `INTERNAL_ERROR`, redacted). The guard compares the **actual protected estimate `P`**, never merely `R_reserve` (which by construction is ≤ `C_cap` and could never overflow).
- **Compaction termination:** compaction reduces only low-priority narrative (debate prose, redundant analyst text) until total ≤ `T_compact` or until the only remaining reducible content is protected; if compacting all reducible narrative still leaves total > `C_cap`, **fail closed**. Available narrative budget = `C_cap − P`; stop when narrative reaches that bound.
- **Compaction method:** summarize/trim **low-priority narrative layers only**; deterministic truncation with an explicit "(compacted)" marker is the baseline. If a summarizing **model call** is used it is an **explicitly disclosed extra provider call** logged as `event=context.compact` — not silent network behaviour. Default design = deterministic truncation (no extra model; consistent with the note that these corrections imply **no new summarizing provider call**).
- **Re-injection:** after compaction re-inject identity, mode, snapshot identity (fingerprint/basename/as-of), output authority and frozen disclaimer/notice.
- **Where:** node-prompt assembly in the agent context layer (`tradingagents/agents/context.py` + prompt builders); **not** OpenCode's internal context.
- **Temporal guards:** memory/context retrieval keeps upstream as-of/time guards; compaction must not reintroduce out-of-window history.
- **Illustrative over-cap (document example; arithmetic verified):** assembled estimate = 26,000 tokens; protected `P ≈ 3,200` (identity/constraints/state/notice). Reducible narrative ≈ 22,800. Compaction truncates older bull/bear debate prose (~6,500 → ~500, saving ~6,000) giving 26,000 − 6,000 = **20,000**, still > `T_compact`=19,200, so further low-priority narrative is trimmed (e.g., another ~800) to reach ≈ **19,200** ≤ `T_compact`; protected `P` and current task survive. If instead `P` were 23,000, then `C_cap − P = 1,000` narrative budget, and it fails closed when the minimum task context cannot fit.
- **Distinction:** bounded **application-context** design; not OpenCode internal management; **not** an aggregate run-token/time/call budget (deferred).

## Decision

Adopt **C2: an input-service + deeply immutable `RunContext` boundary with a small explicit CLI lifecycle coordinator and a shared execution service.**

- `PortfolioInputService` (`tradingagents/runapi/input_service.py`): the sole discoverer/validator/freezer; produces a `RunContext`.
- `RunContext`/`FrozenSnapshot` (`runapi/context.py`): deeply immutable value tuples + mode + full-64 canonical SHA-256 + as-of/basis + consent_state; read-only provenance source.
- **Shared execution service** (`runapi/execution.py: run_analysis_api`): the **common application entry** for CLI and supported project API; rejects non-`CONFIRMED` contexts; owns execution, exception mapping, checks, finalize, staging/publish and terminal event; prompt-free.
- `RunLifecycleCoordinator` (CLI layer): interactive selection/consent transitions; no LLM; no broad orchestration rewrite; no backtest/resume.
- `OutputChecker` and `OutcomeFinalizer` are the sole assigners of `output_check`/`run_outcome`.
- Upstream engine signature preserved; the raw primitive is a declared reduced-coverage path whose product reliance requires A's approval (R-API).

## Alternatives considered (actual, preserved)

- **C1 — Minimal baseline extension.** Inline discovery/validation (sole shared module, thin inline adapter); header lines appended in reporting; small checker; inline manifest. Pros: smallest footprint. Cons: lifecycle sequencing inline; higher risk of provenance drift if reporting re-derives from `final_state` (latent FR-006/007 risk); weakest typed failure behaviour. Score 3.30.
- **C2 — Input-service + `RunContext` + small coordinator + shared execution service (selected).** Pros: explicit input/snapshot boundary; clean test seams; shared provenance; typed outcomes; full-coverage API path. Cons: more modules than C1. Score 4.65.
- **C3 — Phased single-run orchestrator façade.** Same service/context, plus a façade over the whole single-run lifecycle. Pros: strong phase testing. Cons: broader `cli/run.py` change; highest coupling/surface; scope-creep risk. Score 3.75.

## Human selection rationale (recorded verbatim in substance)

Brian selected **C2** because of its **explicit input/snapshot boundary, test seams and shared provenance, without C3's broader orchestration change.** This is a **human design choice based on estimated tradeoffs**, explicitly **not** a claim of verified superiority.

## Consequences

Positive: single provenance source; deterministic check authority; consent is an explicit transition; shared execution service gives full-coverage API path; preserved engine signature.
Negative/risks: the raw low-level engine primitive can bypass the boundary and its product use requires A's approval (R-API); full-64 fingerprint canonicalization must be exactly implemented (`interface-contracts.md` §2.2); prompt/context wording changes are required (not optional).

## Reopening conditions

- Instructor mandates a single orchestration façade → revisit C3.
- File-count/scope constraints favour C1 → revisit.
- Real test evidence (C) shows C1's inline path is cleanly testable with no provenance drift → re-score.
- Any change to consent semantics, provenance identity or check authority requires a new ADR.

## Related

- Canonical blueprint: [../../../architecture-blueprint.md](../../../architecture-blueprint.md)
- [../interface-contracts.md](../interface-contracts.md), [../evaluation-table.md](../evaluation-table.md), [../evaluation-logbook.md](../evaluation-logbook.md), [../risk-list.md](../risk-list.md), [../option-ledger.md](../option-ledger.md), [../invariants.md](../invariants.md), [../memory-design.md](../memory-design.md), [../runtime-policy-catalog.md](../runtime-policy-catalog.md), [../permission-model.md](../permission-model.md), [../traceability-inputs-member-b.md](../traceability-inputs-member-b.md).
