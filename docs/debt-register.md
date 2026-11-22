# Debt Register

Known technical and process debt, with impact and the condition under which each
entry expires. Owner identifiers follow the A–E role map in `execution_plan_261111.md`.

| ID | Category | Description | Impact | Opened | Expiry condition | Status |
|---|---|---|---|---|---|---|
| DEBT-FR05-D4 | Governance / audit debt | The D#4 of the approved baseline (`5e30376`) remains **false-green**: `failures` / `quality_labels` / default `run_pair_id`/`case_id` are not effectively locked by assertions; the `188`/`30` counts in `docs/req/trace-FR-05-contracts.md` / `docs/approvals/spec-registry*.md` are inconsistent with the actual **contracts 223 / E2 28**. | The implementation may pass the tests yet fail to meet D#4; the evidence basis (口径) of GATE-01/GATE-03 is inconsistent. | 2026-11-21 | Open a new **test/spec PR** to: add the D#4 assertions (failures/quality_labels/ids effectively locked), correct trace/registry counts to the actual 223/28, recompute the hashes, and re-batch review by D+B. | Open (deferred to follow-up test/spec PR) |

Owner: E · Verifier: D · Due: 2026-11-22T18:00:00+08:00

| DEBT-FR01-CI | CI / governance debt | The `offline-tests` CI job does **not** gate the FR-01 evidence suite yet. It cannot be added safely until: (a) PR #5 (`test/offline/contracts/test_evidence_contracts.py`, 23 spec cases) is merged; (b) B's `EvidenceItem`/`EvidencePack` types exist (the 23 tests import them from `egta.contracts`, which needs #10 contracts merged **plus** the evidence types); (c) an `actual_cases` record exists (e.g. `docs/approvals/test-hash-FR-01-contracts.txt`). | FR-01 evidence coverage is not CI-gated; a broken evidence suite would not block. | 2026-11-21 | Add the FR-01 evidence package to `offline-tests` once the evidence types are implemented and a `test-hash-FR-01-contracts.txt` with `actual_cases` exists (applicable ⇔ `EvidenceItem`/`EvidencePack` are importable from `egta.contracts` — NOT from `egta.evidence` — and the record contains `actual_cases`; expected from the record; no skip/xfail). | Open (follow-up after FR-01 evidence type implementation) |

Owner: E · Verifier: A

> **DEBT-FR05-D4 — closing-pending (status unchanged: Open).** This follow-up
> test/spec PR (`spec/FR-05-compare-fixes`) adds the previously-missing
> assertions (single-sided metric → MISSING_METRIC, illegal rubric rejection,
> observed≠threshold scoring, strong `failures`/`quality_labels`/`run_pair_id`/
> `case_id` locks). Debt status is **not** changed here; it will be marked
> closed **only after** D confirms this spec + #10 is implemented to it (D's
> decision pending).
