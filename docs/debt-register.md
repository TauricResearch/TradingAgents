# Debt Register

Known technical and process debt, with impact and the condition under which each
entry expires. Owner identifiers follow the A–E role map in `execution_plan_261111.md`.

| ID | Category | Description | Impact | Opened | Expiry condition | Status |
|---|---|---|---|---|---|---|
| DEBT-FR05-D4 | Governance / audit debt | The D#4 of the approved baseline (`5e30376`) remains **false-green**: `failures` / `quality_labels` / default `run_pair_id`/`case_id` are not effectively locked by assertions; the `188`/`30` counts in `docs/req/trace-FR-05-contracts.md` / `docs/approvals/spec-registry*.md` are inconsistent with the actual **contracts 223 / E2 28**. | The implementation may pass the tests yet fail to meet D#4; the evidence basis (口径) of GATE-01/GATE-03 is inconsistent. | 2026-11-21 | Open a new **test/spec PR** to: add the D#4 assertions (failures/quality_labels/ids effectively locked), correct trace/registry counts to the actual 223/28, recompute the hashes, and re-batch review by D+B. | **Closing-pending — awaiting D (verifier) confirmation.** Implemented/merged via #18 (`10ee52d`); winner/composite still deferred (D#4 not fully complete, independent debt). |

Owner: E · Verifier: D · Due: 2026-11-22T18:00:00+08:00

| DEBT-FR01-CI | CI / governance debt | The `offline-tests` CI job does **not** gate the FR-01 evidence suite yet. It cannot be added safely until: (a) PR #5 (`test/offline/contracts/test_evidence_contracts.py`, 23 spec cases) is merged; (b) B's `EvidenceItem`/`EvidencePack` types exist (the 23 tests import them from `egta.contracts`, which needs #10 contracts merged **plus** the evidence types); (c) an `actual_cases` record exists (e.g. `docs/approvals/test-hash-FR-01-contracts.txt`). | FR-01 evidence coverage is not CI-gated; a broken evidence suite would not block. | 2026-11-21 | Add the FR-01 evidence package to `offline-tests` once the evidence types are implemented and a `test-hash-FR-01-contracts.txt` with `actual_cases` exists (applicable ⇔ `EvidenceItem`/`EvidencePack` are importable from `egta.contracts` — NOT from `egta.evidence` — and the record contains `actual_cases`; expected from the record; no skip/xfail). | Open (follow-up after FR-01 evidence type implementation) |

Owner: E · Verifier: A

> **DEBT-FR05-D4 — closing-pending (awaiting D).** E cannot close this alone; it
> needs the **verifier (D)** to confirm. Implemented/merged via **#18** (`10ee52d`)
> — contracts **223** / E2 **28** green; the D#4 test-field assertions
> (single-sided `MISSING_METRIC`, illegal rubric, observed≠threshold + Option-Y
> threshold→REVIEW failures, `quality_labels`=enhanced, explicit ids) are covered.
> **Still deferred (part of D#4, tracked as an independent debt):**
> `winner`/`composite` scoring (`winner/baseline_win/enhanced_win` = None/False).
> Owner: E · Verifier: D. **D to confirm closure.**

## Follow-up debts (from #18 / v3 review — semantics to spec/test in a later spec PR)

| ID | Category | Description | Status |
|---|---|---|---|
| DEBT-V3-SEM-1 | Spec/contract semantics | `replay_events([])` (empty input) fail-closed behaviour is undefined — should it raise `ChainBroken` (cf. `verify_chain([], anchor)`)? Specify + test in a follow-up spec PR. | Open |
| DEBT-V3-SEM-2 | Security/ordering semantics | `SqliteAuditSink.append` does not call `verify_payload` first; a bad `payload_hash` should be rejected before persistence. Specify + test in a follow-up spec PR. | Open |
| DEBT-V3-SEM-3 | Robustness | `Receipt` idempotency key `f"{run_id}:{event_id}"` can collide (e.g. ids containing `:`); use a structured/escaped key. Specify + test. | Open |
| DEBT-V3-NFR06 | Coverage evidence | NFR-06 coverage evidence (business-line coverage ≥85%, security-branch 100%) not yet produced for the v3 implementation. | Open |

All: **Owner: E · Verifier: D.**

## Superseded PRs
- **#10** (v2, impl/FR-05-contracts-v2 @ `399dfc4`) — superseded by **#18** (merged into main `10ee52d`); history retained. Formal supersede/close marker by D.
