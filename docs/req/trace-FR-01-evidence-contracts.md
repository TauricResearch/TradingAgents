# Trace — FR-01 evidence contracts (test-first spec, PR #5)

Requirement-to-test trace for `test/offline/contracts/test_evidence_contracts.py`.
**Spec/test only. This PR adds no `src/`.** The three public types (`RunSpec`,
`EvidenceItem`, `EvidencePack`) are delivered by a **separate implementation PR** (B) after this
spec is approved and merged; that PR has no number yet. Contract definitions:
`docs/req/evidence-contracts.md` (standalone; `docs/req/contracts-summary.md` is
left unchanged from its `main` baseline).

**This file is distinct from A's INV-02 time-policy trace**
(`docs/req/trace-FR-01-evidence.md`, PR #4). #4 owns the UTC filter algorithm and
its boundary behaviour; #5 owns only the public TYPE representation. No file
here overwrites A's trace or A's approval record.

## Status

- 23 `test_*` functions in one module.
- The module sets `pytestmark = pytest.mark.spec`. The default `pytest` run
  (`-m "not integration and not spec"`) never collects it; it is run explicitly
  with `-m spec test/offline/contracts`. The `spec` marker is registered on current
  `main`'s `pyproject.toml`.
- RED on this branch by design: `from egta.contracts import ...` raises a
  collection error because the evidence types are not implemented yet. Nothing
  imports the types until the implementation PR lands.

## Coverage matrix (FR-01 → test → fixture / responsibility)

| # | Test function | Covers | Fixture / basis | Responsibility |
|---|---|---|---|---|
| 1 | `test_public_types_construct_from_run_spec_and_one_item` | FR-01 | construction sample | B (type) |
| 2 | `test_evidence_id_is_carried_not_regenerated` | FR-01, A item 2 | `run_id` + `case_local_id` | B (type stores id) |
| 3 | `test_run_spec_accepts_aware_utc_as_of` | FR-01 | plan §5.1 | B |
| 4 | `test_run_spec_rejects_naive_as_of` | FR-01 | plan §5.1 | B |
| 5 | `test_run_spec_rejects_date_only_as_of` | FR-01 | plan §5.1 | B |
| 6 | `test_evidence_item_accepts_each_availability` | FR-01 | A->B #6 four states | B |
| 7 | `test_evidence_item_rejects_unknown_availability` | FR-01 | A->B #6 | B |
| 8 | `test_evidence_item_normal_sample_has_no_reason_and_conflict_group_defaults_none` | FR-01 | A->B #5 | B |
| 9 | `test_tampered_item_is_constructible_and_keeps_supplied_digest` | FR-01, A item 3 | E-23-2 / E-30-1 | B (construct); A (recompute/report) |
| 10 | `test_evidence_item_accepts_reason_code_from_fixture` (3 params) | FR-01 | E-13/E-18/E-17/E-20 | B |
| 11 | `test_evidence_item_rejects_misspelled_reason_code` | FR-01 | ReasonCode | B |
| 12 | `test_evidence_reason_codes_are_public` (7 params) | FR-01 | 7 evidence codes | B tests / E (#18 enum) |
| 13 | `test_existing_shared_reason_codes_remain` (6 params) | FR-01 | 6 shared codes | B tests / E (#18 enum) |
| 14 | `test_evidence_pack_explicit_empty_excluded_items_is_valid` | FR-01 | A item 4 | B |
| 15 | `test_evidence_pack_omitting_excluded_items_fails` | FR-01 | A item 4 | B |
| 16 | `test_evidence_pack_accepts_non_empty_excluded_entry` (4 params) | FR-01, A item 4 | E-23-2 / provider / E-17-1 / E-26-1 | B |
| 17 | `test_excluded_provider_entry_needs_no_published_at_or_evidence_id` | FR-01, A item 4 | E-24/E-25 (`case_local_id="provider"`) | B |
| 18 | `test_date_only_item_on_cutoff_date_represented_as_excluded` | FR-01, D #4 review | E-31 @ `19da73a` | B (type); A (filter) |
| 19 | `test_date_only_item_keeps_date_precision_in_public_json` | FR-01, D #4 review | E-31 @ `19da73a` | B (type); A (filter) |
| 20 | `test_e21_duplicate_local_ids_are_distinct_and_construct` | FR-01, A comment | E-21 (E-21-1 / E-21-2) | B (type); A (dedupe) |
| 21 | `test_pack_cutoff_carries_run_spec_as_of` | FR-01, A item 5 | plan §5.1 | B |
| 22 | `test_required_field_missing_points_at_that_field` (24 params) | FR-01 | plan §5.1 keys | B |
| 23 | `test_required_key_presence_is_not_the_same_as_null_allowed` | FR-01 | plan §5.1 | B |

## Responsibility boundary (explicit)

- **Public types (B, this spec):** field presence, `availability` required and
  enumerated, date-only JSON precision, `excluded_items` required (empty OK) and
  the 3-field non-empty shape, `RunSpec.as_of` tz-aware, `cutoff` = `as_of`.
- **Evidence module (A):** normalization (`availability="available"` default for
  admitted fixtures; full `evidence_id` from `run_id` + `case_local_id`),
  dedupe (E-21), `content_hash` recompute/compare -> `INTEGRITY_VIOLATION`.
- **UTC filter (A, PR #4):** strictly-before admitted; same-date excluded
  (`unavailable`/`FUTURE_DATA`); exact-timestamp equality admitted.

## Expected-RED registry

| Suite | Command | Expected result | Captured evidence |
|---|---|---|---|
| Evidence contract spec | `python -m pytest -m spec test/offline/contracts/test_evidence_contracts.py -q --tb=line` | exit 2, collection error (`ModuleNotFoundError: egta`); 0 executed; no xfail/skip | `docs/evidence/FR-01-contracts/red-baseline.txt` |
| syntax / AST | `python -m py_compile test/offline/contracts/test_evidence_contracts.py` | exit 0; AST count 23 `test_*` | `docs/evidence/FR-01-contracts/compile-ast.txt` |
| lint (full repo) | `ruff check .` | All checks passed | `docs/evidence/FR-01-contracts/ruff.txt` |

The full-repo `ruff check .` depends on `pyproject.toml` `known-first-party =
["egta"]` present on current `main`; this branch is synced with `main`, so the
check matches CI.

## Evidence binding

The three records in `docs/evidence/FR-01-contracts/` were captured at clean
commit `f52868d`. The test file is byte-identical at the test-content commit
`a433d5a`, the evidence commit, the reviewed head `efbcb5e`, and the post-main
sync head (`4618b25a…`). The approval record binds `test_content_commit
a433d5a`, `verification_head f52868d`, and the per-file SHA-256 values. The exact
collection-error text is environment/base-specific; the required RED signal is
"collection error, zero executed", not a particular missing module name.

## Acceptance after implementation (not met now)

These conditions are for the future implementation PR descending from #5's merge
baseline; they are NOT satisfied by this spec branch and must not be read as
passing:

- `python -m pytest -m spec test/offline/contracts/test_evidence_contracts.py`
  collects and runs all 23 test functions (collected == run), exit 0.
- The three types are importable from `egta.contracts` and enforce the rules above.
