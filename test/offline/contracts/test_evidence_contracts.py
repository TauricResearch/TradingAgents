"""Offline contract tests for the shared evidence types (FR-01 / INV-02).

These are SPEC tests: they target the public types the team agreed on

    from egta.contracts import RunSpec, EvidenceItem, EvidencePack

and the shared ``ReasonCode``. On this branch there is no ``src/``
implementation, so collection fails at import with ``ModuleNotFoundError`` --
that is the intended test-first signal, not a defect in the tests.

Scope is the TYPES, not the date-filtering algorithm. A owns the UTC closed-
interval filter and its boundary tests (e.g. their fixture E-31). Here we only
show that the public types can REPRESENT a date-only item admitted on the same
UTC date as the cutoff, with ``availability="available"`` and
``reason_code=None``.

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


# ---------------------------------------------------------------------------
# 5. Date-only representation: same-UTC-date item can be a valid pack member.
#    (The filtering algorithm and boundary belong to A; this asserts the TYPE.)
# ---------------------------------------------------------------------------


def test_date_only_item_on_cutoff_date_represented_as_available():
    """A's E-31: a date-only bar whose date equals the as_of UTC date is admissible.

    The public type must be able to carry this as ``available`` with no reason
    code. The decision that it IS admissible is A's filter; here we only show the
    types can represent the admitted outcome without inventing a time.
    """
    spec = _run_spec(as_of=_utc())
    item = _evidence_item(
        evidence_id="run01-E-31-1",
        source_uri="yfinance://AAPL/2026-11-11",
        published_at="2026-11-11",  # date-only, allowed on the item
        availability="available",
        reason_code=None,
    )
    pack = EvidencePack(
        run_id=spec.run_id,
        snapshot_id=spec.snapshot_id,
        items=[item],
        excluded_items=[],
        cutoff=spec.as_of,
        pack_hash=SHA,
    )
    assert pack.items[0].availability == "available"
    assert pack.items[0].reason_code is None


def test_date_only_item_keeps_date_precision_in_public_json():
    """The public JSON form keeps day precision: no invented time or offset."""
    item = _evidence_item(published_at="2026-11-11", availability="available", reason_code=None)
    assert item.model_dump(mode="json")["published_at"] == "2026-11-11"


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
