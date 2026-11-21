# Debt Register

Known technical and process debt, with impact and the condition under which each
entry expires. Owner identifiers follow the A–E role map in `execution_plan_261111.md`.

| ID | Category | Description | Impact | Opened | Expiry condition | Status |
|---|---|---|---|---|---|---|
| DEBT-FR05-D4 | Governance / audit debt | The D#4 of the approved baseline (`5e30376`) remains **false-green**: `failures` / `quality_labels` / default `run_pair_id`/`case_id` are not effectively locked by assertions; the `188`/`30` counts in `docs/req/trace-FR-05-contracts.md` / `docs/approvals/spec-registry*.md` are inconsistent with the actual **contracts 199 / E2 28**. | The implementation may pass the tests yet fail to meet D#4; the evidence basis (口径) of GATE-01/GATE-03 is inconsistent. | 2026-11-21 | Open a new **test/spec PR** to: add the D#4 assertions (failures/quality_labels/ids effectively locked), correct trace/registry counts to the actual 199/28, recompute the hashes, and re-batch review by D+B. | Open (deferred to follow-up test/spec PR) |

Owner: E · Verifier: D · Due: 2026-11-22T18:00:00+08:00
