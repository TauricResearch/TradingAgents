# Spec registry — FR-05 contracts (test-first)

## Marker & quarantine (D item 8 — Option A)

- Marker: `spec`, registered in `pyproject.toml` (`--strict-markers` on).
  Every spec file sets `pytestmark = pytest.mark.spec`.
- **Default run excludes spec:** `addopts = -ra --strict-markers -m "not integration
  and not spec"` and `testpaths = ["tests"]`. So `pytest` on the spec branch runs
  the upstream suite (**green**) and never touches the RED spec — **without relying
  on testpaths omission to hide it**.
- **Spec branch command:** `pytest tests -m "not integration"` + `py_compile` +
  AST count + (planned) hash check.
- **Implementation/main branch command (required, gated):**
  `pytest tests` + `pytest -m spec test/offline/contracts`. The gate MUST verify
  **exactly the actual collected number** (no hardcoded 188; `--collect-only`); silently
  deselected/zero-selected ⇒ fail.
- Explicit show-RED on spec branch: `pytest -m spec test/offline/contracts` →
  7 collection errors (`ModuleNotFoundError: egta`).

## Expected-RED reason
No `src/` on spec branch ⇒ `egta.contracts.audit`/`evaluation` imports fail.
`--collect-only` is not a green proof (collection imports modules).

## CI / required checks — files D must land (D item 9)
This PR prepares/records the verification inputs; **Admin D** must add the checks:
- Spec-syntax job: `py_compile test/offline/contracts/*.py` + AST test-count +
  (hash check of `aggregate_sha256` / `spec_bundle_sha256`).
- Trace/AI-log presence check.
- Implementation-PR required job: run `pytest -m spec test/offline/contracts`
  (exactly 188 cases), verify impl branch descends from spec merge commit, verify test
  aggregate hash == approved value, first impl commit after approval commit.
- Add these to `protect-main` required status checks + CODEOWNERS review.

## Coverage
- 7 test modules (9 files incl. `__init__.py`, `conftest.py`); case count = actual `--collect-only` (gate uses the precise number; contract-change adds D#1/SequenceConflict/MISSING_METRIC cases).
- `_InMemorySink` (test_audit.py) is a **reference double**; impl PR must add a
  real `SqliteAuditSink` integration test.

## Hash & approval (D item 13)
- `docs/approvals/test-hash-FR-05-contracts.txt` holds `test_content_commit`,
  `aggregate_sha256`, and `spec_bundle_sha256` (tests + contracts-summary + trace +
  this registry). Any change updates the bundle hash ⇒ re-review.
- Authoritative reviewed head = GitHub review `commit_id`; merge commit recorded in
  this registry / CI artifact / PR comment. Do not push the approval file after
  approval.

## Verification evidence (this round)
- Spec branch: `pytest -m spec test/offline/contracts` → 7 collection errors (RED).
- `py_compile` exit 0; AST = 111 functions.
- `ruff check .` green.
- Full spec-satisfying impl in `/tmp` → `pytest -m spec test/offline/contracts`
  → **188 passed**.

## Finalized (NOT PENDING)
- `quality_rubric` = independent field at the same level as `metrics_rubric`.
- `code_hash` / `policy_hash` / `manifest_hash` are in v1 and tested; code/policy
  mismatch → INCOMPLETE CODE_MISMATCH/POLICY_MISMATCH, no win.
- `MISSING_USAGE` and **`MISSING_METRIC`** are first-class `IncompleteReason`
  members (D resolved). No observation for a rubric metric → compare_runs and
  pair_report both INCOMPLETE/MISSING_METRIC; unknown usage → MISSING_USAGE; no win.
- **D#1:** `compare_runs(..., manifest: ExperimentManifest | None = None)`; when
  supplied, `compute_manifest_hash` must equal both sides' `manifest_hash` else
  MANIFEST_MISMATCH. Check order: manifest → snapshot/model/prompt/code/policy →
  result/usage → rubric observation. Direct +/− tests in contracts.
- **D#6:** `verify_chain([])` OK; `verify_chain([], anchor=...)` → `ChainBroken`
  (fail-closed) — tested in **contracts** `test_replay.py` (moved from E2).
- **`SequenceConflict(AuditContractError)`** (run_id, sequence, existing_event_id,
  incoming_event_id) for differing `(run_id, sequence)`. `DuplicateConflict` ONLY
  for differing `(run_id, event_id)`; `AuditUnavailable` ONLY store/anchor
  unavailable. Real mid-process failure → AuditUnavailable + rollback.
- **D#4 (deferred winner only):** typed rubric validation, MISSING_METRIC
  existence, operator/threshold applied (scored value = observed), quality_labels
  propagated (no forgery), run_pair_id/case_id from inputs (no hardcoded
  pair/case). Debt: winner/composite (owner E, due 2026-11-22T18:00+08:00,
  verifier D; no winner shown before FR-05 reported).
- Enforced (not deferred): RunEvent frozen + validate_assignment, `duration_ms>=0`,
  `OK` without `reason_code`, `BLOCKED` with `reason_code`, `schema_version`
  validation; `ExperimentManifest` frozen.
- `HOLD` is an `AdvisoryProposal.action` (valid non-transaction result), NOT a
  `RunStatus`/`CompletionStatus`; not a system failure (see verification-constraints).

## PENDING
- **None.** No PENDING (B) or PENDING (D) items remain.
