# Trace — FR-01 EvidencePack pack-level spec (test-first)

Requirement-to-test trace for `test/offline/evidence/test_pack.py` (PR #25). This
is the **spec/test** artifact only; the implementation (`src/egta/evidence/pack.py`)
lands in a descendant PR that must descend from this spec's merge commit (GATE-01).

## What this branch is / is not

- **Is**: pack-level tests over the `E-01…E-31` fixtures — admission, raw→
  `EvidenceItem` field mapping, dedupe, conflict grouping, integrity tamper,
  provider failure, stale cache, citation validation, and `pack_hash` properties.
- **Is not**: the INV-02 pure time filter (already in `test_time_policy.py`); the
  `EvidenceItem` / `EvidencePack` contract types (B #21); the implementation.
- **Depends on**: B's contracts PR #21 (`egta.contracts` exporting
  `Availability`/`EvidenceItem`/`EvidencePack`/`ExcludedItem`/`RunSpec`) and A's
  `egta.evidence` (`build_pack`, `validate_claims`, `InvalidCitation`).
- **RED by design**: `pytest -m spec test/offline/evidence` → 32 errors from
  `ImportError` (contracts not yet exporting evidence types on this base), no
  xfail/skip. `-m "not spec"` stays green (13 time-policy tests).

## Frozen cross-module contracts (resolved from D's review of #25)

| Contract | Frozen decision | Rationale / consumer |
|---|---|---|
| `pack_hash` provenance | **Computed by `build_pack`**, never caller-supplied | D's risk gate (`risk_gate/rules.py`) recomputes `recompute_evidence_hash(pack)` and rejects a mismatch as `INTEGRITY_VIOLATION`; a caller-supplied hash cannot match |
| `pack_hash` properties | 64-hex, deterministic (same input → same digest), content-bound (mutated item → different digest) | Testable without freezing the algorithm |
| `pack_hash` algorithm | **Frozen by executable equality**: `pack.pack_hash == egta.risk_gate.canonical.recompute_evidence_hash(pack)` (helper already on main), asserted by `test_pack_hash_matches_risk_gate_canonical` over E-01/E-07/E-22/E-23 | No ADR-004 needed: the equality test against the existing canonical helper is the integration proof, not a "must equal" claim |
| claim evidence id form | **Full** `<run_id>-<case_local_id>` | Risk gate indexes claims by full `evidence_id` (`risk_gate/rules.py` `_check_claims`) |
| dangling citation error | Concrete `egta.evidence.InvalidCitation` carrying `ReasonCode.INVALID_CITATION`; message names the bad id | No `pytest.raises(Exception)` |
| E-22 `conflict_group` | Caller supplies `conflict_key`; item group equals that key | No underivable label frozen |
| E-26 stale rule | `source_type == "cache"` is always stale (`STALE_DATA`/`stale`); fresh non-cache control admitted | No freshness threshold in this spec |
| `pack.items` order | Preserves input order (admitted items only) | Explicit, not implicit |

## Test function → requirement mapping

| Test function | Covers | Fixture / input | Notes |
|---|---|---|---|
| `test_normal_items_admitted` | FR-01 | E-01…E-06, E-08, E-09, E-10, E-12 | admitted ids, empty exclusions, no reason code |
| `test_raw_fields_map_to_evidence_item` | FR-01 (traceability) | E-01, E-07, E-10 | source_uri/published_at/fetched_at/excerpt/trust_label/content_hash survive raw→item |
| `test_date_only_before_cutoff_admitted` | INV-02 wired | E-07 | date preserved (no invented time) |
| `test_time_filtered_items_excluded` | INV-02 wired | E-16, E-17 | FUTURE_DATA vs EVIDENCE_MISSING distinct |
| `test_duplicate_keeps_canonical` | FR-01 | E-21 | only canonical admitted; dup not an exclusion |
| `test_conflicting_items_share_group` | FR-01 | E-22 | both retained, group == supplied key |
| `test_non_conflicting_has_no_group` | FR-01 | E-01 | single item never grouped |
| `test_tampered_item_excluded` | FR-01, NFR-08 | E-23 | forged copy excluded INTEGRITY_VIOLATION |
| `test_single_tampered_item_excluded` | FR-01, NFR-08 | E-30 | single tamper excluded |
| `test_provider_failure_becomes_provider_exclusion` | FR-01 | E-24, E-25 | provider exclusion VENDOR_UNAVAILABLE/unreachable |
| `test_offline_cache_is_stale` | FR-01 | E-26 | cache item stale, never available |
| `test_fresh_non_cache_item_is_admitted` | FR-01 | E-26 variant | rule is cache-keyed, not age-keyed |
| `test_dangling_citation_rejected` | FR-01 | E-29 | full-id dangling → InvalidCitation naming id |
| `test_valid_citation_passes` | FR-01 | E-29 | full-id resolves |
| `test_pack_hash_is_computed_hex64` | FR-01 | E-01 | build-computed 64-hex |
| `test_pack_hash_is_deterministic` | FR-01 | E-01 | same input → same digest |
| `test_pack_hash_is_content_bound` | FR-01 | E-01 mutated | changed content → changed digest |
| `test_pack_hash_matches_risk_gate_canonical` | FR-01 (A→D integration) | E-01, E-07, E-22, E-23 | `pack.pack_hash == egta.risk_gate.canonical.recompute_evidence_hash(pack)` via the helper already on main |
| `test_pack_items_preserve_input_order` | FR-01 | E-22 | input order preserved |
| `test_admitted_content_hash_matches_excerpt` | FR-01, NFR-08 | E-01 | content_hash == sha256(excerpt) |

## Evidence

- `docs/evidence/FR-01/pack-red-baseline.txt` — full exit codes + raw ImportError.
- `docs/evidence/FR-01/pack-manifest-green.txt` — manifest/meta green.
- `docs/evidence/FR-01/pack-ruff.txt` — ruff.
- `docs/approvals/test-hash-FR-01-pack.txt` — per-file + aggregate test hash.

## Post-#21 status

- **B #21 merged to main `141547a`**: `RunSpec`/`EvidenceItem`/`EvidencePack`/
  `ExcludedItem`/`Availability` now import from `egta.contracts`; this branch is
  rebased onto `141547a` and the RED re-captured — it is now purely "egta.evidence
  absent" (`ImportError: InvalidCitation`), not a contracts gap. The test file was
  updated to add `test_pack_hash_matches_risk_gate_canonical` (the real A→D
  equality check against the canonical helper on main) and to correct the
  post-#21 docstrings; per-file/aggregate hashes and `test_content_commit` are
  rebound below.
- Remaining before approval: D re-review on this post-#21 head; fill
  `reviewed_pr_head` / `merge_commit` after merge. The implementation PR (A) must
  descend from this spec's merge commit and provide `egta.evidence.InvalidCitation`
  + `build_pack`/`validate_claims`.
