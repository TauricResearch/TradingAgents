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
class SequenceConflict(AuditContractError):    # (run_id, sequence, existing_event_id, incoming_event_id)
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
- **Uniqueness / exception mapping:** `DuplicateConflict` ONLY for a differing
  `(run_id, event_id)`; `SequenceConflict` for a differing
  `(run_id, sequence)` (fields `run_id, sequence, existing_event_id,
  incoming_event_id`); `AuditUnavailable` ONLY when the store/anchor is
  unavailable. A real storage failure (e.g. mid-process after the event insert)
  → `AuditUnavailable`, transaction rolled back (no partial rows/receipt).
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
    CODE_MISMATCH, POLICY_MISMATCH, MISSING_RESULT, MISSING_USAGE, MISSING_METRIC
```
`MISSING_USAGE` and `MISSING_METRIC` are first-class members (D resolved). `MISSING_METRIC` = no observation for a rubric metric.

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
INCOMPLETE `MISSING_USAGE`; no observed value for a rubric metric ⇒ INCOMPLETE
`MISSING_METRIC`. Optional `manifest: ExperimentManifest | None = None`: when
supplied, `compute_manifest_hash(manifest)` must equal **both** sides'
`manifest_hash`, else INCOMPLETE `MANIFEST_MISMATCH`. Check order: manifest →
snapshot/model/prompt/code/policy → result/usage → rubric observation (so the
manifest counterexample still yields `MANIFEST_MISMATCH`). None of these count as
a win. `variant` is propagated to `EvaluationResult.variant`.

**D#4 scope:** winner/composite scoring is **deferred (debt)**; `winner`/
`baseline_win`/`enhanced_win` stay `None`/`False` until debt closure (owner E,
due 2026-11-22T18:00+08:00, verifier D; winner not reported before FR-05 is
reported). Required now: typed rubric validation (`TypeAdapter(dict[str,
MetricDef])`), observation existence (`MISSING_METRIC`), and applying
operator/threshold per metric (scored value = the **observed** value, not the
threshold).

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
