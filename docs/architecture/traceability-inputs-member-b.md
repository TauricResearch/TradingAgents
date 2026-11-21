# Traceability Inputs — Member B (for E)

Status: **incomplete on purpose.** This is B's contribution of component/invariant/runtime-monitor rows for E's shared `trace-matrix.md`. B does **not** publish a competing final matrix (E owns assembly). C's test IDs/evidence and D's implementation links are **pending** and must not be invented.

Legend: **Enforced-by** = design component; **Fallback** = concrete behaviour; **Monitor** = runtime observation; **Test ID / Impl link** = pending (C / D).

| Req ID | Enforced-by (design) | Distilled invariant | Runtime monitor / event | Fallback | Test ID | Impl link |
|---|---|---|---|---|---|---|
| SEL-TA-FR-001 | `PortfolioInputService.discover` | INV-01 | `input.selection` | reselect/cancel; zero LLM | pending (C) | pending (D) |
| SEL-TA-FR-002 | Coordinator consent | INV-09 | `input.consent` | decline → no run | pending | pending |
| SEL-TA-FR-003 | `PortfolioInputService` precheck+freeze | INV-01/INV-02 | `input.mode_resolved` | stop pre-dispatch | pending | pending |
| SEL-TA-FR-004 | RunContext + prompt/context semantics | INV-02/INV-13 | `input.mode_resolved` | render frozen notice; keep unknowns | pending | pending |
| SEL-TA-FR-005 | Reporting labels + `rating.py` | INV-13 | `output.check` | REVIEW stays REVIEW | pending | pending |
| SEL-TA-FR-006 | `runapi/context.py` + reporting projection | INV-04/INV-05/INV-05b | `output.provenance` | refuse fallback to file/mtime; deep-immutable tuples | pending | pending |
| SEL-TA-FR-007 | `runapi/checks.py` | INV-03/INV-08 | `output.check` | NEEDS_REVIEW; suppress badge | pending | pending |
| SEL-TA-NFR-001 | `OutcomeFinalizer` | INV-07 | `run.terminal` | typed incomplete | pending | pending |
| SEL-TA-NFR-002 | `runapi/events.py` | INV-11 | `run.terminal` (count=1) | terminal-append failure best-effort: logical outcome preserved, `durable=false` | pending | pending |
| SEL-TA-NFR-003 | `Redactor` | INV-06 | `security.redaction` | redact before delivery | pending | pending |
| SEL-TA-NFR-004 | `runapi/persist.py` + coordinator | INV-12/INV-14 | `output.persist` | run-ID isolation; refuse overwrite | pending | pending |
| SEL-TA-NFR-005 | `runapi/execution.py` shared service + `cli/input_ui.py` | INV-10/INV-09 | `api.entry` | supported API traverses boundary; raw primitive reduced-coverage (A approval) | pending | pending |
| SEL-TA-NFR-006 | `RunRecord` aggregation (`runapi/result.py`; interface-contracts §10) | (risk R-LABEL) | `run.started`/`run.terminal` | zero-completed ⇒ insufficient evidence | pending | pending |
| SEL-TA-GOV-001 | C/E/human (test-plan approval) | — | — | — | owned C/E | n/a |
| SEL-TA-GOV-002 | A/E (registry schema) | — | — | — | owned A/E | n/a |
| SEL-TA-GOV-003 | C/E (CI gates) | — | — | — | owned C/E | n/a |
| SEL-TA-GOV-004 | C/D/E (semantic threshold) | — | — | — | owned C/D/E | n/a |
| SEL-TA-GOV-005 | E/all (AI-use log) | — | — | — | owned E | n/a |
| SEL-TA-GOV-006 | B (permission design) → E (enforce) | (permission-model.md) | denied-write log | block denied write | owned C/E | pending (E) |

## Notes
- All FR/NFR rows have an architecture allocation (this file + `invariants.md`). GOV rows are allocated to other owners; B contributes only the `GOV-006` permission design.
- Deferred requirements (selected-requirements §5) are **not** claimed satisfied and are omitted.
- Unknown test IDs and implementation links stay `pending` for C and D; E assembles the final matrix.
