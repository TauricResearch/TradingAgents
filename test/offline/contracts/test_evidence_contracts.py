"""Offline contract tests for the shared evidence types (FR-01 / INV-02).

These are SPEC tests: they target the public types the team agreed on

    from egta.contracts import RunSpec, EvidenceItem, EvidencePack

and the shared ``ReasonCode``. On this branch there is no ``src/``
implementation, so collection fails at import with ``ModuleNotFoundError`` --
that is the intended test-first signal, not a defect in the tests.

Scope is the TYPES, not the date-filtering algorithm. A (PR #4) owns the UTC
filter and its boundary behaviour; here we only show that the public types can
REPRESENT the agreed outcomes.

Admissibility rules the tests below mirror (D's second review of PR #4, pinned
fixture E-31 at ``19da73a``; the algorithm stays A's responsibility):

- date-only, or ``time_granularity="day"``: admitted ONLY when the date is
  strictly earlier than the ``as_of`` UTC date;
- same UTC date as ``as_of``: excluded / ``availability="unavailable"`` with
  ``reason_code="FUTURE_DATA"`` (not ``INVALID_TIME``) - a same-day full bar
  cannot be proven published before ``as_of``;
- exact timestamp equality (``published_at == as_of``): admitted.

No ``skip``/``xfail`` and no in-test replacement types: if the public types are
missing or stop enforcing a rule, these tests fail.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from egta.contracts import EvidenceItem, EvidencePack, RunSpec
from egta.contracts.events import ReasonCode

# Opt-in spec marker: default `pytest` runs `tests/` only; this module is run
# explicitly with `-m spec test/offline/contracts` so RED placement is explicit,
# never hidden by testpaths omission. Requires the `spec` marker registration
# (present on current main's pyproject.toml).
pytestmark = pytest.mark.spec

SHA = "a" * 64

# The evidence-side reason codes A asked to be canonical for v1 (A->B list, #3),
# plus E's already-existing shared codes that must remain valid.
EVIDENCE_REASON_CODES = (
    "FUTURE_DATA",
    "EVIDENCE_MISSING",
    "INVALID_TIME",
    "STALE_DATA",
    "VENDOR_UNAVAILABLE",
    "INVALID_CITATION",
    "INTEGRITY_VIOLATION",
)
EXISTING_SHARED_CODES = (
    "BUDGET_DENIED",
    "INVALID_OUTPUT",
    "POLICY_REJECTED",
    "STALE_PORTFOLIO",
    "AUDIT_UNAVAILABLE",
    "INCOMPATIBLE_STATE",
)

# The four availability states A agreed on (A->B list, #6).
AVAILABILITY_VALUES = ("available", "stale", "unreachable", "unavailable")

EXCERPT = "Headline text that is cited."
# SHA-256 of EXCERPT itself (content_hash covers the excerpt, A->B list #10).
EXCERPT_HASH = hashlib.sha256(EXCERPT.encode("utf-8")).hexdigest()

# A confirmed RunSpec field set (plan 5.1). Every key is required.
RUN_SPEC_REQUIRED = (
    "schema_version",
    "run_id",
    "ticker",
    "as_of",
    "mode",
    "model_config_hash",
    "prompt_hash",
    "policy_hash",
    "snapshot_id",
    "limits",
)

# A confirmed EvidenceItem base field set (plan 5.1).
EVIDENCE_ITEM_REQUIRED = (
    "evidence_id",
    "source_uri",
    "published_at",
    "fetched_at",
    "content_hash",
    "excerpt",
    "availability",
    "trust_label",
)

# A confirmed EvidencePack field set (plan 5.1).
EVIDENCE_PACK_REQUIRED = (
    "run_id",
    "snapshot_id",
    "items",
    "excluded_items",
    "cutoff",
    "pack_hash",
)

# Meaningful limits for the sample (all three axes named, not empty).
LIMITS = {"max_calls": 12, "max_total_tokens": 40000, "max_cost_usd": "0.50"}


def _utc(y=2026, mo=11, d=11, h=0, mi=0, s=0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=UTC)


def _run_spec_dict() -> dict:
    return {
        "schema_version": "1.0",
        "run_id": "run01",
        "ticker": "AAPL",
        "as_of": _utc(),
        "mode": "enhanced",
        "model_config_hash": SHA,
        "prompt_hash": SHA,
        "policy_hash": SHA,
        "snapshot_id": "snap01",
        "limits": dict(LIMITS),
    }


def _evidence_item_dict() -> dict:
    return {
        "evidence_id": "run01-E-01-1",
        "source_uri": "yahoo-news://8f2c1d",
        "published_at": _utc(d=10, h=13, mi=5),
        "fetched_at": _utc(h=0, mi=5),
        "content_hash": EXCERPT_HASH,
        "excerpt": EXCERPT,
        "availability": "available",
        "trust_label": "secondary",
    }


def _evidence_pack_dict() -> dict:
    return {
        "run_id": "run01",
        "snapshot_id": "snap01",
        "items": [EvidenceItem(**_evidence_item_dict())],
        "excluded_items": [],
        "cutoff": _utc(),
        "pack_hash": SHA,
    }


def _run_spec(**overrides) -> RunSpec:
    base = _run_spec_dict()
    base.update(overrides)
    return RunSpec(**base)


def _evidence_item(**overrides) -> EvidenceItem:
    base = _evidence_item_dict()
    base.update(overrides)
    return EvidenceItem(**base)


def _evidence_pack(**overrides) -> EvidencePack:
    base = _evidence_pack_dict()
    base.update(overrides)
    return EvidencePack(**base)


def _missing_field_errors(exc: ValidationError) -> set[str]:
    """Field names whose errors are 'missing'-type (key absent), not value-type."""
    return {
        e["loc"][0]
        for e in exc.errors()
        if e["type"] == "missing" and e.get("loc")
    }


# ---------------------------------------------------------------------------
# 1. Public import and a minimal end-to-end construction sample (for A).
# ---------------------------------------------------------------------------


def test_public_types_construct_from_run_spec_and_one_item():
    """A can build a pack from a RunSpec plus one valid item through the public API."""
    spec = _run_spec(run_id="run01", snapshot_id="snap01")
    item = _evidence_item(evidence_id=f"{spec.run_id}-E-01-1")
    pack = EvidencePack(
        run_id=spec.run_id,
        snapshot_id=spec.snapshot_id,
        items=[item],
        excluded_items=[],
        cutoff=spec.as_of,
        pack_hash=SHA,
    )
    assert pack.run_id == spec.run_id
    assert pack.snapshot_id == spec.snapshot_id
    assert [i.evidence_id for i in pack.items] == ["run01-E-01-1"]
    assert pack.excluded_items == []
    # The supplied hash is carried unchanged; this test does NOT assert how a
    # pack_hash is computed (that algorithm is not agreed yet).
    assert pack.pack_hash == SHA


def test_evidence_id_is_carried_not_regenerated():
    """The public type stores the id it is given; it does not mint ids from run_id."""
    item = _evidence_item(evidence_id="run01-E-01-1")
    assert item.evidence_id == "run01-E-01-1"


# ---------------------------------------------------------------------------
# 2. RunSpec.as_of: timezone-aware UTC required; bare date / naive rejected.
# ---------------------------------------------------------------------------


def test_run_spec_accepts_aware_utc_as_of():
    spec = _run_spec(as_of=_utc())
    assert spec.as_of.utcoffset().total_seconds() == 0


def test_run_spec_rejects_naive_as_of():
    with pytest.raises(ValidationError):
        _run_spec(as_of=datetime(2026, 11, 11, 0, 0, 0))


def test_run_spec_rejects_date_only_as_of():
    """A bare date is not a valid as_of instant (evidence may be date-only; as_of may not)."""
    with pytest.raises(ValidationError):
        _run_spec(as_of="2026-11-11")


# ---------------------------------------------------------------------------
# 3. EvidenceItem: base fields, four availability values, unknown reason codes.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("availability", AVAILABILITY_VALUES)
def test_evidence_item_accepts_each_availability(availability):
    item = _evidence_item(availability=availability)
    assert item.availability == availability


def test_evidence_item_rejects_unknown_availability():
    with pytest.raises(ValidationError):
        _evidence_item(availability="maybe")


def test_evidence_item_normal_sample_has_no_reason_and_conflict_group_defaults_none():
    item = _evidence_item(availability="available")
    assert item.reason_code is None
    assert item.conflict_group is None


# -- 3a. Content integrity: two-layer responsibility (A's item 3).


def test_tampered_item_is_constructible_and_keeps_supplied_digest():
    """``EvidenceItem`` does NOT cross-validate ``content_hash`` against ``excerpt``.

    A's E-23-2 / E-30-1 are deliberate tampering fixtures: the excerpt was altered
    while ``content_hash`` keeps the ORIGINAL digest, expecting ``INTEGRITY_VIOLATION``
    at pack time. If the model enforced equality those fixtures could not be built.
    So: the item is constructible, the supplied digest is preserved, and no
    validation error is raised. This asserts CONSTRUCTION only - it does NOT mean
    integrity was checked. The evidence module recomputes and compares the digest
    when building the pack and reports ``INTEGRITY_VIOLATION`` on a mismatch.
    """
    original_digest = hashlib.sha256(b"original excerpt").hexdigest()
    item = _evidence_item(
        excerpt="excerpt altered after hashing",  # differs from original_digest
        content_hash=original_digest,
        availability="unavailable",
        reason_code="INTEGRITY_VIOLATION",
    )
    # Constructed without cross-field validation, and the digest is unchanged.
    assert item.content_hash == original_digest
    assert item.content_hash != hashlib.sha256(item.excerpt.encode("utf-8")).hexdigest()


# -- 3b. Reason codes: actually usable on an EvidenceItem, not just enum members.

# A's fixture E-13 is a future item: availability="unavailable", reason FUTURE_DATA.
@pytest.mark.parametrize(
    "availability,reason_code",
    [
        ("unavailable", "FUTURE_DATA"),      # A fixture E-13
        ("unavailable", "INVALID_TIME"),     # A fixture E-18
        ("unavailable", "EVIDENCE_MISSING"),  # A fixture E-17 / E-20
    ],
)
def test_evidence_item_accepts_reason_code_from_fixture(availability, reason_code):
    item = _evidence_item(availability=availability, reason_code=reason_code)
    assert item.reason_code == reason_code
    assert item.availability == availability


def test_evidence_item_rejects_misspelled_reason_code():
    with pytest.raises(ValidationError):
        _evidence_item(availability="unavailable", reason_code="FUTURE_DAT")


@pytest.mark.parametrize("code", EVIDENCE_REASON_CODES)
def test_evidence_reason_codes_are_public(code):
    assert code in {c.value for c in ReasonCode}


@pytest.mark.parametrize("code", EXISTING_SHARED_CODES)
def test_existing_shared_reason_codes_remain(code):
    assert code in {c.value for c in ReasonCode}


# ---------------------------------------------------------------------------
# 4. EvidencePack: excluded_items must be explicit (empty list is valid).
# ---------------------------------------------------------------------------


def test_evidence_pack_explicit_empty_excluded_items_is_valid():
    pack = _evidence_pack(excluded_items=[])
    assert pack.excluded_items == []


def test_evidence_pack_omitting_excluded_items_fails():
    with pytest.raises(ValidationError):
        EvidencePack(
            run_id="run01",
            snapshot_id="snap01",
            items=[_evidence_item()],
            cutoff=_utc(),
            pack_hash=SHA,
        )


# -- 4b. Non-empty excluded_items: the agreed 3-field shape (A item 4).
#    Entries are NOT EvidenceItem: no published_at, no full evidence_id.
#    ``case_local_id == "provider"`` marks a provider-level failure.
#    The public export name for this type is not frozen here; these tests
#    exercise it only through ``EvidencePack(excluded_items=[...])``.


@pytest.mark.parametrize(
    "entry",
    [
        # A's E-23-2: tampered excerpt -> integrity violation.
        {"case_local_id": "E-23-2", "availability": "unavailable", "reason_code": "INTEGRITY_VIOLATION"},
        # A's E-24/25: provider-level failure; local id is literally "provider".
        {"case_local_id": "provider", "availability": "unreachable", "reason_code": "VENDOR_UNAVAILABLE"},
        # A's E-17-1: missing published_at.
        {"case_local_id": "E-17-1", "availability": "unavailable", "reason_code": "EVIDENCE_MISSING"},
        # A's E-26-1: stale.
        {"case_local_id": "E-26-1", "availability": "stale", "reason_code": "STALE_DATA"},
    ],
    ids=["E-23-2", "provider", "E-17-1", "E-26-1"],
)
def test_evidence_pack_accepts_non_empty_excluded_entry(entry):
    pack = _evidence_pack(excluded_items=[entry])
    stored = pack.excluded_items[0]
    # Access by attribute or mapping; the contract fixes the three field names.
    as_map = stored if isinstance(stored, dict) else stored.model_dump()
    assert as_map["case_local_id"] == entry["case_local_id"]
    assert as_map["availability"] == entry["availability"]
    assert as_map["reason_code"] == entry["reason_code"]


def test_excluded_provider_entry_needs_no_published_at_or_evidence_id():
    """A provider-level failure carries EXACTLY the three agreed fields."""
    pack = _evidence_pack(
        excluded_items=[
            {"case_local_id": "provider", "availability": "unreachable", "reason_code": "VENDOR_UNAVAILABLE"}
        ]
    )
    stored = pack.excluded_items[0]
    as_map = stored if isinstance(stored, dict) else stored.model_dump()
    assert set(as_map.keys()) == {"case_local_id", "availability", "reason_code"}


# ---------------------------------------------------------------------------
# 5. Date-only same-UTC-date representation: excluded / unavailable, not
#    INVALID_TIME (D's second review of #4; fixture E-31 at 19da73a).
#    The filtering algorithm belongs to A; these assert the TYPE can carry
#    the agreed excluded outcome and keeps day precision.
# ---------------------------------------------------------------------------


def test_date_only_item_on_cutoff_date_represented_as_excluded():
    """A's E-31 (19da73a): a date-only bar whose date equals the as_of UTC date
    is conservatively excluded, so it is NOT an admitted item: ``items=[]`` and a
    single ``excluded_items`` entry with ``case_local_id="E-31-1"``,
    ``availability="unavailable"``, ``reason_code="FUTURE_DATA"`` (not
    ``INVALID_TIME``).

    The public type must be able to carry that pack shape; the decision that it IS
    excluded is A's filter. Here we only show the types can represent it.
    """
    spec = _run_spec(as_of=_utc())
    pack = EvidencePack(
        run_id=spec.run_id,
        snapshot_id=spec.snapshot_id,
        items=[],  # excluded, so no admitted item
        excluded_items=[
            {
                "case_local_id": "E-31-1",
                "availability": "unavailable",
                "reason_code": "FUTURE_DATA",
            }
        ],
        cutoff=spec.as_of,
        pack_hash=SHA,
    )
    assert pack.items == []
    entry = pack.excluded_items[0]
    as_map = entry if isinstance(entry, dict) else entry.model_dump()
    assert as_map["case_local_id"] == "E-31-1"
    assert as_map["availability"] == "unavailable"
    assert as_map["reason_code"] == "FUTURE_DATA"


def test_date_only_item_keeps_date_precision_in_public_json():
    """The public JSON form keeps day precision while carrying the excluded outcome.

    Same-date date-only is excluded/unavailable with ``FUTURE_DATA``; the JSON
    representation still keeps day precision (no invented time or offset).
    """
    item = _evidence_item(
        published_at="2026-11-11", availability="unavailable", reason_code="FUTURE_DATA"
    )
    assert item.model_dump(mode="json")["published_at"] == "2026-11-11"


# ---------------------------------------------------------------------------
# 5b. E-21 duplicate local ids: the TYPE can carry both; A's module dedupes.
#     (A's confirmation: E-21-1 and E-21-2 are distinct local ids; E-21-2 is the
#     duplicate copy of the same excerpt. Both map to full ids via run_id.)
# ---------------------------------------------------------------------------


def test_e21_duplicate_local_ids_are_distinct_and_construct():
    spec = _run_spec(run_id="run01")
    e21 = "Apple supplier orders point to a stronger quarter, report says."
    item_1 = _evidence_item(
        evidence_id=f"{spec.run_id}-E-21-1",
        excerpt=e21,
        availability="available",
        reason_code=None,
    )
    item_2 = _evidence_item(
        evidence_id=f"{spec.run_id}-E-21-2",
        excerpt=e21,  # same excerpt, different local id
        availability="available",
        reason_code=None,
    )
    assert item_1.evidence_id == "run01-E-21-1"
    assert item_2.evidence_id == "run01-E-21-2"
    assert item_1.evidence_id != item_2.evidence_id
    assert item_1.excerpt == item_2.excerpt
    # Both are representable; deduping the duplicate is A's evidence module's job
    # (its E-21 expected: admitted ["E-21-1"], duplicate dropped). NOT asserted
    # here: the model itself must not dedupe.


# ---------------------------------------------------------------------------
# 5c. as_of -> cutoff mapping: the evidence module passes the run/fixture as_of
#     into ``EvidencePack.cutoff`` (A item 5). This shows the type accepts it.
# ---------------------------------------------------------------------------


def test_pack_cutoff_carries_run_spec_as_of():
    spec = _run_spec(as_of=datetime(2026, 11, 11, 0, 0, 0, tzinfo=UTC))
    pack = EvidencePack(
        run_id=spec.run_id,
        snapshot_id=spec.snapshot_id,
        items=[_evidence_item()],
        excluded_items=[],
        cutoff=spec.as_of,  # same instant, passed through by the evidence module
        pack_hash=SHA,
    )
    assert pack.cutoff == spec.as_of
    assert pack.cutoff.utcoffset().total_seconds() == 0


# ---------------------------------------------------------------------------
# 6. Required fields: removing exactly one required key fails, and the error
#    points at that field. This distinguishes "key must be present" from
#    "value may be None" (null-value rules are NOT decided here).
# ---------------------------------------------------------------------------

_REQUIRED_CASES = [
    (RunSpec, _run_spec_dict, RUN_SPEC_REQUIRED),
    (EvidenceItem, _evidence_item_dict, EVIDENCE_ITEM_REQUIRED),
    (EvidencePack, _evidence_pack_dict, EVIDENCE_PACK_REQUIRED),
]


@pytest.mark.parametrize(
    "model_cls,make_dict,field",
    [(m, mk, f) for m, mk, fields in _REQUIRED_CASES for f in fields],
    ids=[f"{m.__name__}.{f}" for m, _, fields in _REQUIRED_CASES for f in fields],
)
def test_required_field_missing_points_at_that_field(model_cls, make_dict, field):
    data = make_dict()
    del data[field]
    with pytest.raises(ValidationError) as excinfo:
        model_cls(**data)
    missing = _missing_field_errors(excinfo.value)
    assert field in missing, (
        f"expected a 'missing' error for {field!r}; got {excinfo.value.errors()!r}"
    )


def test_required_key_presence_is_not_the_same_as_null_allowed():
    """Dropping a key fails as 'missing'; passing ``None`` is a *different* question.

    We do not freeze null-value rules here. This test only records that ``None``
    is not silently treated as 'missing' -- it must raise something (value or
    type error), which keeps 'key absent' and 'value None' distinguishable.
    """
    with pytest.raises(ValidationError) as excinfo:
        _run_spec(as_of=None)
    missing = _missing_field_errors(excinfo.value)
    # A present-but-None value must NOT be reported as a 'missing' key.
    assert "as_of" not in missing
