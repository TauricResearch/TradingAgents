# Evaluation Table (Member B)

Status: architecture draft. Candidate comparison and the human selection. All scores are **design estimates** (authoring-time judgements), **not** measured verification. Weights are the approved set. The selection is a human choice based on estimated tradeoffs, not a claim of verified superiority.

## 1. Candidates (neutral)

- **C1 — Minimal baseline extension.** Sole shared `portfolio_input` module (discover/validate/freeze) with a **thin inline adapter** in `cli/main.py`; header lines appended in reporting; small checker; inline manifest. Lifecycle sequencing stays inline.
- **C2 — Input-service + immutable `RunContext` + small lifecycle coordinator (SELECTED).** One `PortfolioInputService` → `RunContext`; CLI `RunLifecycleCoordinator` with explicit consent transitions; `OutputChecker`; `OutcomeFinalizer`; redaction; JSONL events; atomic manifest. Single-run scope only.
- **C3 — Phased single-run orchestrator façade.** Same service/context as C2 plus a façade over the whole single-run lifecycle; no backtest/resume.

## 2. Disqualifying constraints pre-screen (DQ1–DQ10)

| # | Constraint | C1 | Rationale | C2 | Rationale | C3 | Rationale |
|---|---|---|---|---|---|---|---|
| DQ1 | No prompts in agents/engine | Pass | Discovery/consent in CLI entry; agents untouched | Pass | Service/coordinator in CLI layer; engine API unchanged | Pass | Façade is CLI-layer coordinator |
| DQ2 | No silent default file pick | Pass | Inline requires explicit choice | Pass | `discover()` returns sorted list; explicit selection | Pass | Same service |
| DQ3 | Absent ≠ flat; missing cash ≠ 0 | Pass | Reuses `PortfolioContext` semantics | Pass | `RunContext` explicit mode + None vs empty | Pass | Same as C2 |
| DQ4 | Recoverable sentinel not fatal | Pass | Outcome finalizer module | Pass | Finalizer consumes typed exceptions | Pass | Delegates to same finalizer |
| DQ5 | Model cannot set check/outcome | Pass | Checker separate; header from frozen state | Pass | `RunContext`+`OutputChecker` authoritative | Pass | Same authority objects |
| DQ6 | No full portfolio payload to new sinks | Pass | Single redactor; discipline required | Pass | Provenance/`SafeRunMetadata` only; redactor at sink | Pass | Same |
| DQ7 | Reusable input-service boundary | Pass | **Sole shared-service ownership with thin inline adapter** (resolved: one validator/discoverer; reporting reads only returned frozen context) | Pass | One service+immutable context | Pass | Same service+context |
| DQ8 | Mode-aware prompt/context wording | Pass | Manager prompt edits required | Pass | Same edits via rendered context | Pass | Same |
| DQ9 | Redaction across sinks | Pass | One helper at each sink | Pass | Redactor at sink boundary | Pass | Same |
| DQ10 | No backtest/resume scope creep | Pass | CLI single-run only | Pass | Coordinator scoped to one fresh run | Pass | Façade strictly single-run |

All three are eligible. C1's DQ7 pass depends on the discipline that reporting/report code never re-derives provenance from `final_state` (latent FR-006/007 risk if violated — recorded as a C1 risk in `risk-list.md`).

## 3. Score matrix (design estimates) with rationale + uncertainty

Scores 1–5 (5 best). Every score is a design estimate.

| Criterion (weight) | C1 | Rationale / uncertainty | C2 | Rationale / uncertainty | C3 | Rationale / uncertainty |
|---|---|---|---|---|---|---|
| Testability / independent seams (25%) | 3 | Shared module helps; inline `main.py` branches harder to isolate. Uncertainty: medium (seams unknown until C plans) | 5 | Service+RunContext+checker cleanly mockable; identity testable independently. Uncertainty: low | 4 | Phased façade testable per phase; more states. Uncertainty: medium |
| Change surface / coupling / maintainability (25%) | 4 | Small footprint; scattered-edit drift risk. Uncertainty: medium-high | 4 | Bounded cohesive modules; small report/manager touch. Uncertainty: low-medium | 2 | Broad `cli/run.py` lifecycle change. Uncertainty: high |
| Auditability / provenance (20%) | 3 | Provenance fragmented across main/reporting. Uncertainty: medium | 5 | Centralized in RunContext; single source for result/header/manifest/events. Uncertainty: low | 5 | Same centralization via façade. Uncertainty: low |
| Failure behaviour (15%) | 2 | Inline path risks untyped escapes; finalizer bolted on. Uncertainty: medium-high | 5 | Coordinator+finalizer enforce typed mapping at every phase. Uncertainty: low | 5 | Façade owns phase failure. Uncertainty: low |
| Compatibility w/ intentional changes (10%) | 4 | Required CLI changes intentional; minor scattered edits. Uncertainty: low | 5 | Clean flag additions; documented intended changes. Uncertainty: low | 4 | More churn in run path. Uncertainty: medium |
| Effort/token estimate (5%) | 5 | ESTIMATE: lowest. Uncertainty: high (may grow) | 3 | ESTIMATE: medium — module map now lists ~10 `runapi` modules (supersedes "~4"). Uncertainty: medium | 2 | ESTIMATE: medium-high; façade rewrite. Uncertainty: high |

## 4. Weighted totals (baseline weights)

Baseline weights: testability 25 · change 25 · auditability 20 · failure 15 · compat 10 · effort 5 = 100.

- **C1** = .25·3 + .25·4 + .20·3 + .15·2 + .10·4 + .05·5 = 0.75+1.00+0.60+0.30+0.40+0.25 = **3.300**
- **C2** = .25·5 + .25·4 + .20·5 + .15·5 + .10·5 + .05·3 = 1.25+1.00+1.00+0.75+0.50+0.15 = **4.650**
- **C3** = .25·4 + .25·2 + .20·5 + .15·5 + .10·4 + .05·2 = 1.00+0.50+1.00+0.75+0.40+0.10 = **3.750**

## 5. Sensitivity analysis (both scenarios normalized to 100%)

### Scenario (a) — change-surface–favouring (exact normalized weights)
testability 12.5 · change 37.5 · auditability 20 · failure 15 · compat 10 · effort 5 = **100**.

- C1 = .125·3 + .375·4 + .20·3 + .15·2 + .10·4 + .05·5 = 0.375+1.500+0.600+0.300+0.400+0.250 = **3.425**
- C2 = .125·5 + .375·4 + .20·5 + .15·5 + .10·5 + .05·3 = 0.625+1.500+1.000+0.750+0.500+0.150 = **4.525**
- C3 = .125·4 + .375·2 + .20·5 + .15·5 + .10·4 + .05·2 = 0.500+0.750+1.000+0.750+0.400+0.100 = **3.500**

### Scenario (b) — testability-favouring (exact normalized weights)
testability 44.4 · change 11.1 · auditability 17.8 · failure 13.3 · compat 8.9 · effort 4.4 (fractions of 100; sum 99.9 → exact fractions used below).
Exact: testability 50/112.5=0.44444 · change 12.5/112.5=0.11111 · audit 20/112.5=0.17778 · failure 15/112.5=0.13333 · compat 10/112.5=0.08889 · effort 5/112.5=0.04444 (sum = 1.00000).

- **C1** = .44444·3 + .11111·4 + .17778·3 + .13333·2 + .08889·4 + .04444·5 = 1.3333+0.4444+0.5333+0.2667+0.3556+0.2222 = **3.156** ✓
- **C2** = .44444·5 + .11111·4 + .17778·5 + .13333·5 + .08889·5 + .04444·3 = 2.2222+0.4444+0.8889+0.6667+0.4444+0.1333 = **4.800** ✓
- **C3** = .44444·4 + .11111·2 + .17778·5 + .13333·5 + .08889·4 + .04444·2 = 1.7778+0.2222+0.8889+0.6667+0.3556+0.0889 = **4.000** ✓

(Scenario (b) totals: 3.156 / 4.800 / 4.000, as required.)

## 6. Interpretation and limits
Ranking across baseline and both normalized scenarios: **C2 > C3 > C1**. This consistency is **a property of the chosen weights and the assigned design-estimate scores, not independent evidence of correctness**. Scores carry stated uncertainty; a different plausible set (e.g., C1 change-surface 5, C1 testability 4) narrows the C1 gap. Reopening conditions: instructor mandates a façade (favours C3); file-count constraint (favours C1/C3); real test evidence (C) shows C1 cleanly testable without provenance drift.

## 7. Selection
**C2 selected by Brian (human)**, rationale: explicit input/snapshot boundary, test seams and shared provenance without C3's broader orchestration change. Recorded in `adr/001-portfolio-aware-cli.md`; process in `evaluation-logbook.md`.
