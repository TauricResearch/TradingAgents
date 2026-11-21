# Contracts Summary — spec definitions for FR-05 audit & evaluation

This is the **spec definition** of the public audit/evaluation contracts. The
tests on this branch import these types; the implementation
(`src/egta/contracts/{events,audit,evaluation,manifest}.py`) is delivered in the
implementation PR. On this spec branch the imports raise `ModuleNotFoundError` =
**RED by design** (test-first). No `src/` file exists here.

Definitions follow **D's** specification (final round) and **B's** confirmations.
B's decisions on quality_rubric / code_hash / policy_hash / manifest_hash are
**finalized** (not PENDING). `PENDING (D)` marks the only remaining open item.

---

## 1. `egta.contracts.audit`

### Exceptions — base `AuditContractError(Exception)`
```python
class AuditContractError(Exception): ...
class ChainBroken(AuditContractError):        # (run_id, expected_sequence, actual_sequence, reason)
class DuplicateConflict(AuditContractError):  # (run_id, event_id, existing_payload_hash, incoming_payload_hash)
class PayloadMismatch(AuditContractError):    # (run_id, event_id, stored_payload_hash, recomputed_payload_hash)
class AuditUnavailable(AuditContractError):   # (run_id, operation, cause)
```
Each exposes those attributes in that order.

### `Receipt` — exactly 12 fields (D)
`schema_version, receipt_id, run_id, event_id, sequence, payload_hash,
prev_event_hash, chain_tip_hash, persisted_at, store_id, transaction_id,
idempotency_key`. `extra="forbid"`; typed (e.g. `sequence: int`, `persisted_at:
datetime` tz-aware); a 13th field is rejected.

### Sink / Reader — Option A (D item 3)
```python
class AuditSink(Protocol):
    def append(self, event: RunEvent) -> Receipt: ...
    def read(self, run_id: str) -> AuditReader: ...

class AuditReader(Protocol):
    def read(self, run_id: str) -> list[RunEvent]: ...   # sorted by (run_id, sequence)
```
- `append`: same `(run_id, event_id)` + identical content → existing `Receipt`
  (idempotent); same `(run_id, event_id)` + different content → `DuplicateConflict`;
  storage failure → `AuditUnavailable` **fail-closed** (no partial write, no silent
  success).
- Cross-run: same `event_id` under a **different** `run_id` is **not** a conflict
  (identity is `(run_id, event_id)`).
- **Hybrid read API (intentional, D item 6 — do not delete):** `AuditSink.read(
  run_id) -> AuditReader` and `AuditReader.read(run_id) -> list[RunEvent]` are
  **both** part of the contract, implemented in both layers. Only one read style is
  used per call site; `_InMemorySink` in tests uses this reference-double shape, and
  the implementation PR integrates a real `SqliteAuditSink` test. The two-layer
  design is the accepted hybrid.
- `read(run_id)` (via `AuditReader`) returns only that run's events, sorted by
  `sequence`.

### Free functions
```python
def recompute_payload_hash(event: RunEvent) -> str  # canonical JSON, exclude payload_hash, sha256 hex
def verify_payload(event: RunEvent) -> None          # PayloadMismatch on divergence
def dedupe_events(events) -> list[RunEvent]          # identical (run_id,event_id)+content -> one (keep order/first); diff content -> DuplicateConflict
def verify_chain(events, *, anchor: str | None = None) -> None
```
`verify_chain`: empty list OK; genesis `prev_event_hash == ""`; **sequence
gap-free from 0**; each `prev_event_hash == previous payload_hash`; payload
binding per event; `anchor` = trusted tip hash → tip mismatch (or last_sequence <
expected) → `ChainBroken` (**tail truncation** / whole-chain replacement).
Ordering keys: `(run_id, sequence)` and `(run_id, event_id)`.

---

## 2. `egta.contracts.evaluation`

### Status & reasons (status, never exception)
```python
class CompletionStatus(StrEnum):   # COMPLETE, INCOMPLETE, BLOCKED, REVIEW, FAILED
class IncompleteReason(StrEnum):
    MANIFEST_MISMATCH, SNAPSHOT_MISMATCH, MODEL_MISMATCH, PROMPT_MISMATCH,
    CODE_MISMATCH, POLICY_MISMATCH, MISSING_RESULT, MISSING_USAGE
```
`MISSING_USAGE` is now a first-class member (D resolved; no longer PENDING).

**HOLD is not a system status.** `HOLD` is an `AdvisoryProposal.action` value
(a valid "do not trade" recommendation), distinct from `RunStatus` and from
`CompletionStatus`. It MUST NOT appear as a `CompletionStatus` member and is not
counted as a system failure/block. It may be expressed in an `EvaluationResult`
as a normal outcome (per `docs/code-governance/verification-constraints.md`, which
defines `OK`/`HOLD` as outcomes that DO count in the success denominator while
BLOCKED/INCOMPLETE/REVIEW/FAILED do not).

### `EvaluationResult` (§5.1 complete — D item 2)
Typed fields:
- `run_pair_id: str`, `case_id: str`, `variant: str`
- `manifest_hash: str` (**required**; mismatch ⇒ INCOMPLETE/MANIFEST_MISMATCH)
- `completion_status: CompletionStatus`
- `incomplete_reason: IncompleteReason | None` — **INCOMPLETE must have a reason;
  COMPLETE must be None** (validated)
- `metrics: dict[str, float]` (typed, default `{}`)
- `quality_labels: list[str]` (typed, default `[]`)
- `failures: list[str]` (typed, default `[]`)
- `winner: str | None`, `baseline_win: bool`, `enhanced_win: bool`

INCOMPLETE/BLOCKED/REVIEW/FAILED are **returned**, never raised; an INCOMPLETE
pair is **not counted as a win** (`baseline_win == enhanced_win == False`,
`winner is None`).

### `replay_events(events, *, anchor=None) -> ReplayState` (D item 1)
`ReplayState` full fields: `run_id: str`, `last_sequence: int`,
`chain_tip_hash: str`, `event_count: int`, `metrics: dict[str, float]`,
`events: list[RunEvent]` (ordered). Sorting by `(run_id, sequence)`,
dedupe by `(run_id, event_id)`, `anchor` applied (tip/last_sequence) → tail
truncation detected. Fully offline (no LLM/network).

### `RunSummary` (typed input to compare_runs — D item 1)
```python
class RunSummary(BaseModel):        # extra="forbid"
    run_id: str                              # required
    variant: str                             # required
    target_snapshot_id: str                  # required
    model_config_hash: str                   # required, 64 lower-hex
    prompt_hash: str                         # required, 64 lower-hex
    code_hash: str                           # required, 40 OR 64 lower-hex
    policy_hash: str                         # required, 64 lower-hex
    manifest_hash: str                       # required, 64 lower-hex
    has_result: bool = True                  # default
    has_usage: bool = True                   # default; False => MISSING_USAGE
    metrics: dict[str, float] = {}           # default
    quality_labels: list[str] = []           # default
```
Mandatory (no default) vs default shown above; hash formats validated. A bare
`dict` is rejected by `compare_runs`. `variant` is carried through to
`EvaluationResult.variant` (the run_id→variant mapping source is the
`RunSummary.variant` field; the implementation obtains it from the run manifest/
RunSpec when building summaries).

### `compare_runs(baseline: RunSummary, enhanced: RunSummary, rubric) -> EvaluationResult`
**Typed inputs only** (reject bare `dict`); accepts `RunSummary` (RunSpec
normalized into a `RunSummary` upstream). `rubric` is a typed
`QualityRubric`/`MetricDef` set and **must be used** (assert it influences
scoring/verification). Comparability requires matching `target_snapshot_id`,
`model_config_hash`, `prompt_hash`, `code_hash`, `policy_hash`. Any mismatch ⇒
INCOMPLETE with the specific reason (SNAPSHOT/MODEL/PROMPT/CODE/POLICY_MISMATCH);
a missing required variant/result ⇒ INCOMPLETE `MISSING_RESULT`; unknown usage ⇒
INCOMPLETE `MISSING_USAGE`. `manifest_hash` is **recomputed via
`compute_manifest_hash`** and compared to the recorded value; a mismatch ⇒
INCOMPLETE `MANIFEST_MISMATCH`. None of these count as a win. `variant` is
propagated to `EvaluationResult.variant`.

---

## 3. `ExperimentManifest` (B confirmations)
- `variants`: **all four B0/B1/B2/B3** mandatory, each non-empty; unknown key
  (e.g. `B9`) rejected.
- `metrics_rubric: dict[str, MetricDef]` — `MetricDef` requires seven fields
  `metric, operator, threshold, verification, source, aggregation, unit`;
  `operator` in an allowed set (`eq,lte,gte,lt,gt`); `threshold` numeric; `unit`
  non-empty string.
- **`quality_rubric: QualityRubric`** — independent field at the same level as
  `metrics_rubric`. Fields: `levels: list[str]` (≥3), `double_blind: bool`,
  `third_party_adjudication: bool`, `llm_judge_assist: bool`.
- **`code_hash: str`** — the complete Git commit SHA of the current experiment
  run (40/64 hex). **`policy_hash: str`** — matches `RunSpec.policy_hash`
  (64-hex). (B3 intentionally disables the budget-optimization switch; the
  test/covenant distinguishes *pre-declared variant differences* from *unstated
  configuration drift* — i.e. a code/policy mismatch **between comparable arms**
  is INCOMPLETE, not a silent difference.)
- **`manifest_hash: str`** — required. Computed by `compute_manifest_hash(m)`:
  ```python
  def compute_manifest_hash(m) -> str:
      data = m.model_dump(mode="json", exclude={"manifest_hash"})
      return sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
  ```
  (also exposed as `ExperimentManifest.recompute_hash()`). Deterministic over
  snapshot/model/prompt/code/policy/variants/rubrics. Verification: if
  `manifest_hash != compute_manifest_hash(m)` → construction rejects OR
  `compare_runs` returns INCOMPLETE/MANIFEST_MISMATCH (the implementation must do
  at least one; `compare_runs` recomputes and compares).
- **`ExperimentManifest` immutability:** `frozen=True`, `validate_assignment=True`
  (assignment after construction raises) — enforced by the implementation and
  tested (`test_manifest_is_frozen_assignment_rejected`).
- **Finalized by B (not PENDING):** `quality_rubric` independent; `code_hash` /
  `policy_hash` / `manifest_hash` in v1.
- **No PENDING (B/D) remain.** `MISSING_USAGE` is now a real enum member.

## 4. `RunEvent` (immutability & strictness — F-05/F-14/F-20, D item 10)
- **Immutable/frozen:** `frozen=True`, `validate_assignment=True` (assignment
  after construction raises).
- `sequence`: strict `int`; negative, bool, or string rejected.
- `status`/reason consistency: `OK` **must not** carry a `reason_code`;
  `BLOCKED` **must** have one (validated). `schema_version`/contract-version
  field present and validated.
- `duration_ms` (NFR-09): per-phase duration recorded, `>= 0` (strict int,
  non-negative). These are **enforced** (not deferred): the implementation must
  provide frozen RunEvent, `duration_ms >= 0`, `OK` without `reason_code`,
  `BLOCKED` with `reason_code`, and `schema_version` validation.

## 5. `RunEvent.metrics` validation
JSON-safe only: non-finite floats (`NaN`,`±inf`), non-serializable objects,
`bytes`, and a non-dict `metrics` are rejected at construction (`ValidationError`).
Nested non-JSON (inside list/dict) also rejected.

---

## 6. Approval binding (corrected, D item 13)
- `docs/approvals/test-hash-FR-05-contracts.txt` records **only**
  `test_content_commit`, `aggregate_sha256`, and **`spec_bundle_sha256`**
  (tests + this summary + trace + spec-registry combined). Any change updates the
  bundle hash ⇒ re-review.
- Authoritative reviewed head = GitHub review `commit_id`; merge commit in the
  external registry/CI artifact/PR comment. **Do not push the approval file after
  approval.**

---

## 7. Evidence contracts — `RunSpec`, `EvidenceItem`, `EvidencePack` (B, FR-01)

**Status:** spec frozen by PR #5 (test-first, no `src/`). The three types are
**not implemented anywhere yet** (checked across `main`, `spec/B-evidence-contracts`,
and E's `impl/FR-05-contracts`). B delivers them in a **separate implementation PR**
after #5 is approved and merged; that PR has **no number yet**. Until it lands,
`from egta.contracts import RunSpec, EvidenceItem, EvidencePack` raises
`ModuleNotFoundError` at collection — that is the intended RED, not a broken spec.
The shared `ReasonCode` is provided by E's contracts (`egta.contracts.events`,
extended to 13 codes in #6, still unmerged).

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
Tests reference `egta.contracts.events.ReasonCode`. E's #6 (unmerged) carries the
13 codes including `INVALID_TIME`, `STALE_DATA`, `VENDOR_UNAVAILABLE`,
`INVALID_CITATION`, `INTEGRITY_VIOLATION`; the six shared codes in
`test_existing_shared_codes_remain` all exist there.
