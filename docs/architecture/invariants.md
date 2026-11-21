# Invariant Register

- **Status:** PARTIAL — D-owned entries only. Other owners must append their sections.
- **Owner of this file's D section:** D
- **Related:** `execution_plan_261111.md` §4.4, FR-04, NFR-05, NFR-09

> This file is created with the D-owned entries because it did not exist in the
> repository. A/B/C/E must append or reconcile their entries rather than overwrite
> the D section. The D entries are proposed enforcement descriptions and are not
> evidence of human approval.

## INV-01 — Only approved proposals may modify the paper ledger

- **Statement:** No proposal may change cash, positions, or ledger entries unless the
  deterministic RiskGate approves it and commits it in the same transaction as the
  verdict and audit event.
- **Source:** FR-04; execution plan §4.4.
- **Enforced by:** `RiskGate.evaluate_and_commit`; private ledger writer; fixed public
  signature with no bypass parameters; minimal exports; import/AST checks.
- **Verification:** `T-RISK-ACT-*`, `T-RISK-FND-*`, `T-RISK-EVD-*`,
  `T-RISK-ATM-*`, `T-RISK-SEC-04..07/14/16`.
- **Violation / inability:** roll back; return `BLOCKED`/`REJECTED`; no ledger change;
  record a security-relevant refusal.
- **Limitation:** a local process with write access to the SQLite file is outside the
  application trust boundary. This is documented in ADR-003.

## INV-04 — Idempotent proposal execution

- **Statement:** The same `proposal_hash` must never produce a second ledger change.
  Duplicate requests return the stored verdict.
- **Source:** FR-04; execution plan §4.4.
- **Enforced by:** unique `proposal_hash` in the verdict/idempotency store; single
  SQLite transaction; `BEGIN IMMEDIATE`; duplicate path returns the stored verdict.
- **Verification:** `T-RISK-IDM-10..16`; `T-RISK-ATM-05..07/18`.
- **Violation / inability:** fail closed; do not convert a duplicate into a second
  trade; do not report a fabricated success.

## INV-06 — Atomic ledger and audit recording

- **Statement:** A simulated execution, its risk verdict, and its audit outbox event
  commit together or not at all. Audit storage failure aborts the execution.
- **Source:** FR-04, NFR-09; execution plan §4.4.
- **Enforced by:** one SQLite transaction; in-database outbox; rollback on any write
  failure; no external `AuditSink` call outside the transaction is accepted as atomic.
- **Verification:** `T-RISK-ATM-10..16/22/23`; crash subprocess tests at
  `after_ledger_insert` and `after_outbox_insert`.
- **Violation / inability:** rollback all rows; return `BLOCKED` with
  `AUDIT_UNAVAILABLE`; retry is allowed only after the storage path is available.

## INV-07 — Secret protection

- **Statement:** Secrets must not enter prompts, reports, commits, verdicts, outbox
  events, or exports. The gate persists only allowlisted fields.
- **Source:** NFR-05; execution plan §4.4.
- **Enforced by:** no raw claims/evidence text in persisted verdict/outbox fields;
  error-message redaction; secret scan; export/commit checks shared with E.
- **Verification:** `T-RISK-SEC-08..12`; canary scan over all text columns;
  permission/secret checks in the Phase 7 governance tooling.
- **Violation / inability:** block export/commit; treat as a security incident;
  rotate the affected credential; preserve a redacted record.
- **Limitation:** D protects fields the gate persists; E and each member remain
  responsible for their own logs, sessions, and exports.

## Cross-module boundary notes (not new invariants)

- INV-02 (evidence time) is owned by A; D consumes `EvidencePack` and re-checks the
  pack hash/cutoff but must not replace A's evidence logic.
- INV-03 (budget reservation) is owned by B; D must not call a model provider and must
  not bypass B's budget path.
- INV-05 (untrusted text isolation) is owned by C plus the permission gateway; D
  contributes the deterministic rule that free text cannot authorize an exemption.
