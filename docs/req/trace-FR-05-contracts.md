# Trace — FR-05 contracts (test-first spec)

Requirement-to-test trace. **Spec/test only.** Implementation
(`src/egta/contracts/{events,audit,evaluation,manifest}.py`) is delivered in a
descendant implementation PR. Contract definitions: `docs/req/contracts-summary.md`.
Related: **PR #1** (original record; DEBT-D2).

**Status:** 7 test modules (9 files), **136 test functions → 223 cases** (test_comparison: 34 functions incl. operator boundaries). RED here: imports of
`egta.contracts.audit`/`evaluation` fail (`ModuleNotFoundError`). Quarantine (D
item 8, Option A): default `pytest` collects only `tests/` (green); the spec is
run explicitly on the impl branch via `pytest -m spec test/offline/contracts`
(required, gate exactly 223 cases) — we do NOT rely on testpaths omission to hide it.
`_InMemorySink` in `test_audit.py` is a **reference double**; the impl PR must add
a real `SqliteAuditSink` integration test. `compare_runs`/`replay_events` are
defined in `egta.contracts.evaluation` (see contracts-summary §2).

## Files (cases)
- `test_events.py` (23 fns) — RunEvent fields/hashes/tz/extra/reason; immutability
  (frozen), sequence strictness (neg/bool/str), OK+reason / BLOCKED-no-reason,
  schema_version, duration; public audit payload binding/chain/dedupe. → FR-05,
  NFR-08, NFR-09
- `test_audit.py` (18) — AuditContractError + 4 exception signatures; Receipt 12
  fields + type/extra; empty chain; first-event prev; anchor/tail-truncation;
  AuditSink idempotency; cross-run identity; fail-closed; AuditReader sort/scope.
  → FR-05, NFR-08, NFR-09
- `test_evaluation_result.py` (10) — CompletionStatus/IncompleteReason members;
  manifest_hash required; typed metrics/quality_labels/failures; INCOMPLETE⇔reason,
  COMPLETE⇔None; winner fields. → FR-05, NFR-09
- `test_comparison.py` (34 functions) — typed inputs (reject dict); snapshot/model/prompt/
  code/policy + manifest_hash mismatch → INCOMPLETE specific reason, no win;
  MISSING_RESULT; rubric used. → FR-05
- `test_replay.py` (8) — ReplayState fields/content; determinism; order-indep;
  dedupe; DuplicateConflict; anchor tail-truncation; offline content asserts.
  → FR-05, NFR-08
- `test_manifest.py` (23) — B0-B3 mandatory; empty B1/B2/B3; unknown; hashes
  (model/prompt/policy 64-hex, code 40-hex); code/policy present; manifest_hash;
  MetricDef 7 fields + illegal operator/threshold/unit/extra; quality_rubric
  independent + fields/levels/bool/extra. → FR-05, NFR-08, NFR-09
- `test_metrics_serialization.py` (8) — reject NaN/±inf/non-JSON object/bytes/
  Decimal; nested non-finite; non-dict metrics; positive roundtrip. → NFR-08

## Scope note (no overstatement)
Duplicate handling is via `AuditSink.append` / `dedupe_events`; rubric via the
independent `quality_rubric` + typed `metrics_rubric`. Stated once per contract.

## Finalized (NOT PENDING)
- quality_rubric independent field; code_hash/policy_hash/manifest_hash in v1
  (code/policy mismatch → INCOMPLETE CODE_MISMATCH/POLICY_MISMATCH, no win).
- `MISSING_USAGE` in `IncompleteReason`; frozen/validate_assignment/duration/
  status-reason/schema_version are enforced (not deferred).
- `HOLD` = `AdvisoryProposal.action` (not RunStatus/CompletionStatus; not a
  system failure). `RunSummary.variant` propagates to `EvaluationResult.variant`.
- `MISSING_METRIC` added to `IncompleteReason` (no observation for a rubric
  metric → INCOMPLETE/MISSING_METRIC).
- `SequenceConflict(AuditContractError)` for differing `(run_id, sequence)`
  (fields run_id, sequence, existing_event_id, incoming_event_id);
  `DuplicateConflict` ONLY for differing `(run_id, event_id)`; `AuditUnavailable`
  ONLY for store/anchor unavailability.
- `compare_runs(..., manifest: ExperimentManifest | None = None)` (D#1): supplied
  manifest's `compute_manifest_hash` must equal both sides' `manifest_hash` →
  else MANIFEST_MISMATCH; check order manifest → snapshot/model/prompt/code/
  policy → result/usage → rubric observation.
- **D#4 (winner deferred only; threshold = Option Y):** winner/composite scoring
  deferred (owner E, due 2026-11-22T18:00+08:00, verifier D). Required now and
  tested: typed rubric validation (`ValidationError` only), `MISSING_METRIC`,
  observed-value scoring (not threshold), and **threshold breach → REVIEW with
  per-side `THRESHOLD_VIOLATION` failures** (within → COMPLETE/failures=[]);
  `quality_labels` source = enhanced. Winner not reported before FR-05 is reported.
- **D#6 (contracts):** `verify_chain([])` OK; `verify_chain([], anchor=...)` →
  `ChainBroken` (fail-closed) — tested here in contracts.

## PENDING
- None (no PENDING B/D).

## Approval
D under GATE-01; author no self-review. Binding: `docs/approvals/test-hash-FR-05-
contracts.txt` (test_content_commit + aggregate + spec_bundle_sha256) + GitHub
review commit_id (authoritative) + external registry (merge). Do not push approval
file after approval.
