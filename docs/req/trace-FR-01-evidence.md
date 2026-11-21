# Trace — INV-02 evidence time filtering (test-first spec)

Requirement-to-test trace for `test/offline/evidence/` (PR #4). This is the
**spec/test** artifact only; implementation lands in a descendant PR that must
descend from this spec's merge commit (GATE-01).

## What this branch is / is not

- **Is**: INV-02 time-policy tests (`test_time_policy.py`, 13 test functions),
  the `E-01…E-31` fixture set, the generator, `docs/evidence/FR-01/`, and this
  trace.
- **Is not**: `EvidenceItem` / `EvidencePack` construction, pack field
  completeness, `pack_hash`, dedupe / conflict / citation / integrity pack
  outcomes. Those are FR-01 and wait on contracts v1.
- **RED by design**: no `src/egta/evidence/` here; collection fails at import
  with `ModuleNotFoundError: No module named 'egta'`, `exit 2`.

## Expected-red registry

| Suite | Command | Expected result | Captured evidence |
|---|---|---|---|
| INV-02 time policy | `python -m pytest test/offline/evidence -q --tb=line` | exit 2, collection error (`ModuleNotFoundError: egta`); no xfail/skip | `docs/evidence/FR-01/red-baseline.txt` |
| syntax / AST | `python -m py_compile test/offline/evidence/*.py` | exit 0; AST count = 13 `test_*` functions | `docs/evidence/FR-01/compile-ast.txt` |
| lint | `python -m ruff check .` | All checks passed | `docs/evidence/FR-01/ruff.txt` |

## Test function → requirement mapping

| Test function | Covers | Fixture / input | Notes |
|---|---|---|---|
| `test_future_items_excluded` | INV-02 | E-13, E-14, E-15, E-16, E-28 | next-day, post-as_of filing, same-day 00:30Z, future date |
| `test_boundary_before_cutoff_admitted` | INV-02 | E-27 | 23:30Z < 00:00Z |
| `test_offset_normalized_to_utc` | INV-02, NFR-10 | E-11 | +08:00 → 09:00Z |
| `test_date_only_before_cutoff_admitted` | INV-02 | E-07 | date-only strictly before as_of date |
| `test_day_granularity_future_excluded` | INV-02 | E-16 | day granularity future |
| `test_missing_published_at_records_reason` | INV-02 | E-17, E-20 | EVIDENCE_MISSING; never silently dropped |
| `test_malformed_time_is_invalid` | INV-02 | E-18 | corrupted timestamp |
| `test_naive_timestamp_not_assumed_utc` | INV-02, NFR-10 | E-19 | no offset must never be assumed UTC |
| `test_epoch_input_supported` | INV-02 | inline epoch | provider epoch seconds |
| `test_naive_as_of_rejected` | INV-02 | inline | naive as_of raises ValueError |
| `test_date_only_equal_to_as_of_date_excluded` | INV-02 | E-31 | same UTC date excluded as unverifiable |
| `test_day_granularity_equal_to_as_of_date_excluded` | INV-02 | inline, day granularity on the as_of UTC date | same UTC date excluded as unverifiable |
| `test_published_at_exactly_equal_to_as_of_admitted` | INV-02 | inline | exact equality admitted, not FUTURE_DATA |

## Fixture coverage matrix

Asserted by this suite (13): E-07, E-11, E-13, E-14, E-15, E-16, E-17, E-18,
E-19, E-20, E-27, E-28, E-31.

Carried as data, **not asserted here** (18): E-01 … E-06, E-08 … E-10, E-12,
E-21 … E-26, E-29, E-30. Reason: pack-level semantics (dedupe, conflict,
citation, stale, provider errors, integrity) need `EvidencePack` and the
canonical `ReasonCode`, which are not frozen in contracts v1. They are asserted
by the FR-01 pack test PR, which must open before any `EvidencePack`
implementation.

Note: E-24/E-25 (`items: []`, `outcome: PACK`) and E-29 (`admitted` plus
`outcome: ERROR`) are pack-level expectations; their pack outcome is deliberately
not constrained here. This is recorded as a clarification to D, not a change of
the time-policy scope.

## Blocking dependencies

1. **ReasonCode source** — the codes this suite asserts (`FUTURE_DATA`,
   `EVIDENCE_MISSING`, `INVALID_TIME`, and `None` when admitted) are all inside
   the canonical set B confirmed in writing on 2026-11-21: FUTURE_DATA,
   EVIDENCE_MISSING, INVALID_TIME, STALE_DATA, VENDOR_UNAVAILABLE,
   INVALID_CITATION, INTEGRITY_VIOLATION, plus None when admitted. The contracts
   PR that lands them is not opened yet (as of 2026-11-21), so there is no
   contracts file or commit to cite yet; when it lands, this item will cite it.
   `STALE_DATA`, `VENDOR_UNAVAILABLE`, `INVALID_CITATION` and
   `INTEGRITY_VIOLATION` appear only in carried-as-data fixtures and are never
   asserted here.
2. **EvidencePack contract** — pack fields and `pack_hash` are PENDING.
3. **Approval** — D must approve this spec head before implementation starts.

## ReasonCode mapping (option B)

- missing published_at -> EVIDENCE_MISSING
- explicit future -> FUTURE_DATA
- malformed or naive timestamp -> INVALID_TIME
- date-only or day on the as_of UTC date -> FUTURE_DATA (conservative; the
  day's full OHLC cannot exist at as_of, so this is future data, not an
  unparsable timestamp)
- admitted -> None

A date-only value on the as_of UTC date is recorded as unavailable with
FUTURE_DATA because availability is a state and reason_code is a cause; this is
a conservative exclusion, not a claim that the source was unreachable.

The asserted fixture count stays 13, and the carried-as-data fixtures stay 18.
