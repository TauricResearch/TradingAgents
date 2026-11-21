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
  **exactly 188 spec cases actually ran** (collected==run==188); silently
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
- 7 test modules (9 files incl. `__init__.py`, `conftest.py`), **111 test functions**, **188 cases**.
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
- `MISSING_USAGE` is a first-class `IncompleteReason` member (D resolved) and
  tested (compare_runs unknown usage → INCOMPLETE/MISSING_USAGE, no win).
- Enforced (not deferred): RunEvent frozen + validate_assignment, `duration_ms>=0`,
  `OK` without `reason_code`, `BLOCKED` with `reason_code`, `schema_version`
  validation; `ExperimentManifest` frozen.
- `HOLD` is an `AdvisoryProposal.action` (valid non-transaction result), NOT a
  `RunStatus`/`CompletionStatus`; not a system failure (see verification-constraints).

## PENDING
- **None.** No PENDING (B) or PENDING (D) items remain.
