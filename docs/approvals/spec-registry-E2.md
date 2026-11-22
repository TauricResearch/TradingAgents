# Spec registry — E2 evaluation (test-first)

## Marker & quarantine (same Option A as FR-05 contracts)
- Marker `spec` (already registered in `pyproject.toml`; `--strict-markers` on).
- Every file under `test/offline/evaluation/test_*.py` sets
  `pytestmark = pytest.mark.spec`.
- Default `pytest` excludes `spec` (`addopts -m "not integration and not spec"`);
  the spec is enabled explicitly on the impl branch via
  `pytest -m spec test/offline/evaluation`. Gate = **exact case count** (filled
  from `--collect-only` when frozen), not `>=`.
- RED on spec branch: `pytest -m spec test/offline/evaluation` → collection errors
  (`ModuleNotFoundError: egta.evaluation.*`). `py_compile`/AST prove well-formed.

## Scope (from D PR #6)
- **D#3:** sink moved to `evaluation/sink.py`; contracts/audit.py = protocols/
  Receipt/exceptions/verify only. `test_sqlite_sink.py` = real SQLite integration.
- **D#1:** `compare_runs(..., manifest: ExperimentManifest | None = None)`;
  supplied manifest's `compute_manifest_hash` must equal both sides'
  `manifest_hash` → else INCOMPLETE/MANIFEST_MISMATCH. `RunSummary` unchanged.
- **D#4:** winner/composite scoring is deferred (DEBT-FR05-D4, owner E, due
  2026-11-22 18:00, verifier D). **Required now and tested:** operator/threshold
  scoring with per-side `THRESHOLD_VIOLATION` failures, `quality_labels` (source =
  enhanced), and explicit `run_pair_id`/`case_id` propagation.
- **D#6:** `verify_chain([])` OK; `verify_chain([], anchor=...)` → `ChainBroken`
  (fail-closed).

## Files & case counts (exact from `--collect-only`)
- E2 collect-only (actual): **28 cases**. Contracts collect-only (actual): **223 cases**.
- Gate = exactly the actual collected numbers (do not hardcode; contracts 223 / E2 28). E2 moved
  D#6 `verify_chain([], anchor)` tests to `test/offline/contracts/test_replay.py`.
- `test_replay.py` · `test_report.py` · `test_metrics.py` · `test_sqlite_sink.py`
  (current E2 total 28).

## Hash & approval
- `docs/approvals/test-hash-E2-evaluation.txt` holds `test_content_commit`,
  `aggregate_sha256`, `spec_bundle_sha256` (tests + trace + this registry).
- Authoritative reviewed head = GitHub review `commit_id`; merge recorded
  externally. Do not push the approval file after approval.

## Dependencies
- E2 impl depends on `egta.contracts.*` — the contracts implementation **#10**
  (successor of #6). **E2 impl waits for #10 to merge**; this spec may proceed in
  parallel off `main`.
