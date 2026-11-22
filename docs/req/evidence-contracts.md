# Evidence contracts — `RunSpec`, `EvidenceItem`, `EvidencePack` (B, FR-01)

Standalone contract definition for the evidence-side types. Delivered as a
test-first spec in PR #5; the three types are implemented by B in a separate
implementation PR after #5 is approved and merged. This file is intentionally
separate from `docs/req/contracts-summary.md` (E's FR-05 contract summary), which
PR #5 leaves unchanged from its `main` baseline. The cross-reference from the
FR-05 summary is recorded in the PR, not by editing that shared file.

---

**Status:** spec frozen by PR #5 (test-first, no `src/`). The three types are
**not implemented anywhere yet** (checked across `main`, `spec/B-evidence-contracts`,
and E's `impl/FR-05-contracts`). B delivers them in a **separate implementation PR**
after #5 is approved and merged; that PR has **no number yet**. Until it lands,
`from egta.contracts import RunSpec, EvidenceItem, EvidencePack` raises
`ModuleNotFoundError` at collection — that is the intended RED, not a broken spec.
The shared `ReasonCode` is provided by E's contracts (`egta.contracts.events`,
extended to 13 codes by E's active contracts implementation PRs (#18 v3 / #10
v2; PR #6 is closed).

### `RunSpec` (plan §5.1)
Required keys (all required; values may be checked separately): `schema_version,
run_id, ticker, as_of, mode, model_config_hash, prompt_hash, policy_hash,
snapshot_id, limits`. `as_of` is a timezone-aware UTC instant (a bare date or a
naive timestamp is rejected). `limits` names at least `max_calls`,
`max_total_tokens`, `max_cost_usd` in the sample.

### `EvidenceItem`
Required base keys: `evidence_id, source_uri, published_at, fetched_at,
content_hash, excerpt, availability, trust_label`. Optional: `reason_code`
(`ReasonCode | None`, default `None`), `conflict_group` (`str | None`,
default `None`).

- `availability` is **REQUIRED** and one of `available / stale / unreachable /
  unavailable`. It is a state; `reason_code` is the cause — they are independent
  and not substitutes.
- **Normalization is the evidence module's job** (A): admitted fixture entries
  that omit `availability` are filled with `available`, and the full
  `evidence_id` is generated from the supplied `run_id` and the case's
  `case_local_id` (e.g. `run01` + `E-01-1` -> `run01-E-01-1`) before the public
  object is constructed. The public type stores the id it is given; it does not
  mint ids or add a hyphen restriction on `run_id`.
- `published_at` may be **date-only** (a yfinance trading date). The public JSON
  form keeps day precision and never fabricates a time/offset.
- **No cross-field validation of `content_hash` vs `excerpt`.** The type permits
  a well-formed digest that does not equal `sha256(excerpt)` so tampering
  fixtures (A's E-23-2 / E-30-1) are constructible. The evidence module
  recomputes the digest at pack time, compares, and reports
  `INTEGRITY_VIOLATION` on a mismatch (see `excluded_items` below).

### `EvidencePack`
Fields: `run_id, snapshot_id, items, excluded_items, cutoff, pack_hash`.
`excluded_items` is **required**; an explicit empty list is valid and omitting
the key fails. `cutoff` is the same instant as the run/fixture `as_of`; the
evidence module passes the fixture's `as_of` into `EvidencePack.cutoff` (the two
names refer to the same boundary; the pack field is `cutoff`).
`pack_hash` is carried as supplied; its computation algorithm is **not** frozen
here.

### `excluded_items` entry shape (non-empty)
Each entry is a **separate** type from `EvidenceItem`; it carries exactly three
fields and **no** `published_at` or full `evidence_id`:

```json
{"case_local_id": "E-23-2",  "availability": "unavailable",  "reason_code": "INTEGRITY_VIOLATION"}
{"case_local_id": "provider", "availability": "unreachable",  "reason_code": "VENDOR_UNAVAILABLE"}
{"case_local_id": "E-17-1",  "availability": "unavailable",  "reason_code": "EVIDENCE_MISSING"}
{"case_local_id": "E-26-1",  "availability": "stale",        "reason_code": "STALE_DATA"}
```

`case_local_id == "provider"` marks a **provider-level** failure (no item).
The tests exercise this shape only through `EvidencePack(excluded_items=[...])`;
the top-level export name for the excluded-entry type is **not frozen** here.

Provider error detail (for example A's `provider_error` `status`/`detail` in
E-24/E-25) is **not** part of the three-field pack entry. The evidence module
records that detail in the `RunEvent`/audit payload; the pack carries only the
admission-relevant `case_local_id`, `availability`, and `reason_code`.

### UTC date boundary (owned by A, mirrored by these types)
From D's second review of PR #4 (fixture E-31 at `19da73a`):

- date-only, or `time_granularity="day"`: admitted ONLY when the date is
  **strictly earlier** than the `as_of` UTC date;
- the **same** UTC date as `as_of`: excluded / `availability="unavailable"` with
  `reason_code="FUTURE_DATA"` (never `INVALID_TIME`) — a same-day full bar cannot
  be proven published before `as_of`;
- exact timestamp equality (`published_at == as_of`): admitted.

The filter algorithm and its behaviour tests remain A's (PR #4). #5 only shows
the public types can REPRESENT these outcomes, including day precision.

### ReasonCode
Tests reference `egta.contracts.events.ReasonCode`. E's active contracts PRs
(#18 v3 / #10 v2; #6 is closed) carry the 13 codes including `INVALID_TIME`,
`STALE_DATA`, `VENDOR_UNAVAILABLE`, `INVALID_CITATION`, `INTEGRITY_VIOLATION`;
the six shared codes in `test_existing_shared_codes_remain` all exist there.
