# Trace — E2 evaluation (test-first spec)

Test-first spec for the E2 evaluation layer (`src/egta/evaluation/`), delivered
in a **descendant implementation PR** after this spec merges. Tests only here;
no `src/`. RED via `ModuleNotFoundError: egta.evaluation.*`.

Dependencies (reused, not redefined): `egta.contracts.{audit,evaluation,events,manifest}`
(the contracts implementation **#10**, successor of #6). E2 implementation waits for #10 to merge.

## Scope changes folded in (from D's PR #6 review)
- **D#3 sink placement:** `contracts/audit.py` keeps only
  `AuditSink`/`AuditReader`/`Receipt`/exceptions/`verify_*`; the real
  `SqliteAuditSink` lives in `src/egta/evaluation/sink.py`. Covered by
  `test_sqlite_sink.py`.
- **D#1 compare manifest verification (option a):** `compare_runs(baseline,
  enhanced, rubric, manifest: ExperimentManifest | None = None)`; when `manifest`
  is supplied, `compute_manifest_hash(manifest)` must equal **both** sides'
  `manifest_hash`, else INCOMPLETE/MANIFEST_MISMATCH. `RunSummary` unchanged.
  Covered by `test_report.py`.
- **D#4 rubric comparison (NOT deferred except winner):** `compare_runs` MUST use
  observed values (not threshold) and apply `MetricDef.operator`/`threshold`,
  recording breaches in `failures`; MUST validate the rubric (illegal → reject);
  MUST require each metric on BOTH sides (single-sided → INCOMPLETE/MISSING_METRIC).
  Only the final winner/composite is deferred (DEBT-FR05-D4, closing-pending).
  Covered by `test_report.py` + `test/offline/contracts/test_comparison.py`
  single-sided/illegal-rubric/observed-value tests. Threshold handling (D Option
  Y): within → COMPLETE/failures=[]; one/both exceed → REVIEW with per-side
  `THRESHOLD_VIOLATION:<metric>:<side>:observed=<v>:operator=<op>:threshold=<t>`
  failures (≥2 when both); THRESHOLD_VIOLATION is not an IncompleteReason.
- **D#6 empty chain + anchor (fail-closed):** `verify_chain([])` (no anchor) → OK;
  `verify_chain([], anchor=...)` → `ChainBroken`. Covered by `test_replay.py`
  (empty-chain anchor) and the contracts layer.

## Test files → cases → REQ

### `test_replay.py` — `egta.evaluation.replay.replay_run(events, *, run_id=None, anchor=None) -> ReplayState`
| Test | Covers | REQ |
|---|---|---|
| `test_replay_returns_replay_state` | ReplayState returned | FR-05 |
| `test_replay_deterministic` | same input → same state | NFR-08 |
| `test_replay_order_independent` | sorts `(run_id, sequence)` | NFR-08 |
| `test_replay_dedupes_identical` | dedupe identical | FR-05 |
| `test_replay_duplicate_conflict_raises` | diff content → DuplicateConflict | FR-05 |
| `test_replay_anchor_tail_truncation` | anchor tip mismatch → ChainBroken | NFR-08 |
| `test_replay_offline_no_network` | socket poisoned; content asserts | NFR-08 |
| `test_replay_scopes_to_run_id` | run_id scoping | FR-05 |
| `test_empty_chain_without_anchor_ok` | D#6: `verify_chain([])` OK | NFR-08 |
| `test_empty_chain_with_anchor_fail_closed` | D#6: `verify_chain([], anchor)` → ChainBroken | NFR-08 |

### `test_report.py` — `egta.evaluation.report.pair_report(...)`
| Test | Covers | REQ |
|---|---|---|
| `test_equal_manifest_complete` | COMPLETE when comparable | FR-05 |
| `test_delegates_to_compare_runs` | equals compare_runs output | FR-05 |
| `test_manifest_param_hash_matches_compute_complete` | D#1 match → COMPLETE | FR-05 |
| `test_manifest_param_hash_not_equal_compute_incomplete` | D#1 hash≠compute → MANIFEST_MISMATCH, no win | FR-05 |
| `test_manifest_param_side_inconsistent_incomplete` | D#1 sides differ → MANIFEST_MISMATCH | FR-05 |
| `test_no_rubric_observation_metrics_not_misleading_complete` | D#4 no misleading COMPLETE | FR-05 |

### `test_metrics.py` — `egta.evaluation.metrics.aggregate(results, rubric) -> dict`
| Test | Covers | REQ |
|---|---|---|
| `test_denominator_counts_ok_and_hold_only` | denominator `|OK|+|HOLD|` | FR-05, NFR-09 |
| `test_failure_samples_excluded_but_reported` | excluded-but-reported (verification-constraints) | FR-05 |
| `test_rubric_used_operator_threshold` | rubric applies | FR-05 |
| `test_missing_usage_incomplete_not_ok` | MISSING_USAGE excluded | FR-05 |
| `test_invalid_rubric_rejected` | bad rubric rejected | FR-05 |

### `test_sqlite_sink.py` — `egta.evaluation.sink.SqliteAuditSink` (D#3, real SQLite)
| Test | Covers | REQ |
|---|---|---|
| `test_sink_satisfies_audit_protocols` | conforms to AuditSink/AuditReader | FR-05 |
| `test_append_returns_receipt_with_12_fields` | Receipt 12 fields persisted | NFR-09 |
| `test_append_idempotent` | same id+content → same Receipt | FR-05, NFR-09 |
| `test_duplicate_conflict` | diff content → DuplicateConflict | FR-05 |
| `test_cross_run_same_event_id_ok` | cross-run identity | FR-05 |
| `test_unique_run_sequence_enforced` | UNIQUE(run_id, sequence) | FR-05 |
| `test_fail_closed_no_partial_write` | fail-closed | NFR-08 |
| `test_reader_sorted_and_scoped` | reader sorting/scope | NFR-09 |

Cases total (actual via --collect-only): **28** (E2). Contracts: **223**. D#6 empty-chain+anchor tests are in `test/offline/contracts/test_replay.py` (moved per D).

## Approval
D (@ZFebron491001) under GATE-01; author no self-review. Binding in
`docs/approvals/spec-registry-E2.md`.
