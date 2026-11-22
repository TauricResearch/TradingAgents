"""Pack-level tests for FR-01 / INV-02, driven by the E-01..E-31 fixtures.

This is the **spec / test-first** artifact (GATE-01). It fixes the observable
behaviour of ``egta.evidence.pack.build_pack`` and ``validate_claims`` before any
implementation exists. It must stay RED on the spec branch: ``egta.contracts``
does not yet export ``EvidenceItem`` / ``EvidencePack`` (B's PR #21) and
``egta.evidence.pack`` does not exist (A's implementation PR, which must descend
from this spec's merge commit).

Import strategy: the contract/implementation imports are performed *inside* a
session-scoped fixture, not at module import. That keeps the module collectable
under ``pytest -m "not spec"`` (so the existing ``test/offline/evidence`` suite
still collects cleanly) while ``pytest -m spec`` reaches the fixture and fails
there with a clear RED. A module-level import would abort collection for *every*
selection and break ``-m "not spec"``.

Scope: only the pack-level outcomes that the time-policy suite left "carried as
data". Pure time filtering (E-13..E-20, E-27, E-28, E-31) is already asserted by
``test_time_policy.py`` and is not re-tested here; a small representative slice is
re-checked through the pack API to prove time filtering is wired in.

Fixture -> assertion map:

    normal admit    E-01 E-02 E-03 E-04 E-05 E-06 E-08 E-09 E-10 E-12
    time wired in   E-07 (date-only admitted), E-16/E-17 (future/undated excluded)
    dedupe          E-21  (only E-21-1 survives; E-21-2 neither admitted nor excluded)
    conflict        E-22  (both retained, same non-empty conflict_group)
    tampered        E-23  (E-23-2 excluded INTEGRITY_VIOLATION, E-23-1 kept),
                    E-30  (single item excluded INTEGRITY_VIOLATION)
    provider fail   E-24, E-25 (items=[], provider exclusion VENDOR_UNAVAILABLE/unreachable)
    stale cache     E-26  (item excluded STALE_DATA/stale, never available)
    citation        E-29  (pack builds, validate_claims raises INVALID_CITATION)

Non-frozen decisions deferred to reviewer (see PR description): the exact
``conflict_group`` label for E-22 and the ``pack_hash`` algorithm (this spec passes
a fixed 64-hex placeholder and only asserts it is carried through unchanged).
"""

from __future__ import annotations

from datetime import date

import pytest

pytestmark = pytest.mark.spec

# A fixed, well-formed 64-hex placeholder. The algorithm is not frozen by the
# contract (#5); this spec only asserts the value is carried through unchanged.
PLACEHOLDER_PACK_HASH = "0" * 64


@pytest.fixture(scope="session")
def pack_api():
    """Import the contract types and the (to-be-implemented) pack API once.

    RED on the spec branch: this raises ``ImportError`` because ``egta.contracts``
    does not export the evidence types yet (B #21 unmerged) and
    ``egta.evidence.pack`` does not exist (A implementation unmerged). Importing
    here rather than at module scope keeps ``-m "not spec"`` collection clean.
    """
    from egta.contracts import (  # noqa: F401
        Availability,
        EvidenceItem,
        EvidencePack,
        ExcludedItem,
        RunSpec,
    )
    from egta.contracts.events import ReasonCode  # noqa: F401
    from egta.evidence.pack import build_pack, validate_claims  # noqa: F401

    class _Api:
        pass

    api = _Api()
    api.Availability = Availability
    api.EvidenceItem = EvidenceItem
    api.EvidencePack = EvidencePack
    api.ExcludedItem = ExcludedItem
    api.RunSpec = RunSpec
    api.ReasonCode = ReasonCode
    api.build_pack = staticmethod(build_pack)
    api.validate_claims = staticmethod(validate_claims)
    return api


def _run_spec(api, frozen_now, case: dict):
    """Build a RunSpec whose as_of equals the case's as_of instant."""
    return api.RunSpec(
        schema_version="1.0",
        run_id=f"run-{case['case_id']}",
        ticker="AAPL",
        as_of=case["as_of"],
        mode="enhanced",
        model_config_hash="1" * 64,
        prompt_hash="2" * 64,
        policy_hash="3" * 64,
        snapshot_id=f"snap-{case['case_id']}",
        limits={},
    )


def _admitted_local_ids(pack, run_spec) -> list[str]:
    prefix = f"{run_spec.run_id}-"
    return [item.evidence_id[len(prefix):] for item in pack.items]


def _build(api, load_case, frozen_now, case_id: str, *, conflict_key=None):
    case = load_case(case_id)
    run_spec = _run_spec(api, frozen_now, case)
    kwargs = {"pack_hash": PLACEHOLDER_PACK_HASH}
    if "provider_error" in case:
        kwargs["provider_error"] = case["provider_error"]
    if conflict_key is not None:
        kwargs["conflict_key"] = conflict_key
    pack = api.build_pack(run_spec, case["items"], **kwargs)
    assert isinstance(pack, api.EvidencePack), case_id
    return case, run_spec, pack


# --------------------------------------------------------------------------- #
# Normal admission
# --------------------------------------------------------------------------- #

NORMAL_CASES = ["E-01", "E-02", "E-03", "E-04", "E-05", "E-06", "E-08", "E-09", "E-10", "E-12"]


@pytest.mark.parametrize("case_id", NORMAL_CASES)
def test_normal_items_admitted(pack_api, load_case, frozen_now, case_id):
    api = pack_api
    case, run_spec, pack = _build(api, load_case, frozen_now, case_id)

    expected = case["expected"]["admitted"]
    assert _admitted_local_ids(pack, run_spec) == expected
    assert pack.excluded_items == []
    assert pack.run_id == run_spec.run_id
    assert pack.snapshot_id == run_spec.snapshot_id
    assert pack.cutoff == run_spec.as_of
    assert pack.pack_hash == PLACEHOLDER_PACK_HASH

    for item in pack.items:
        assert isinstance(item, api.EvidenceItem)
        assert item.availability == api.Availability.AVAILABLE
        # INV-02: an admitted item carries no refusal code.
        assert item.reason_code is None


# --------------------------------------------------------------------------- #
# Time filtering is wired into the pack API (representative slice)
# --------------------------------------------------------------------------- #

def test_date_only_before_cutoff_admitted(pack_api, load_case, frozen_now):
    api = pack_api
    case, run_spec, pack = _build(api, load_case, frozen_now, "E-07")
    assert _admitted_local_ids(pack, run_spec) == case["expected"]["admitted"]
    # Day precision survives to the public form (no invented timestamp).
    assert isinstance(pack.items[0].published_at, date)
    assert not hasattr(pack.items[0].published_at, "hour")


@pytest.mark.parametrize(
    "case_id, reason_name",
    [("E-16", "FUTURE_DATA"), ("E-17", "EVIDENCE_MISSING")],
)
def test_time_filtered_items_excluded(pack_api, load_case, frozen_now, case_id, reason_name):
    api = pack_api
    case, _run_spec_, pack = _build(api, load_case, frozen_now, case_id)
    assert pack.items == []
    excluded = pack.excluded_items
    assert len(excluded) == len(case["expected"]["excluded"])
    # E-16 (future) vs E-17 (undated) keep their distinct causes.
    assert excluded[0].reason_code == api.ReasonCode(reason_name)
    assert excluded[0].availability == api.Availability.UNAVAILABLE


# --------------------------------------------------------------------------- #
# Dedupe (E-21)
# --------------------------------------------------------------------------- #

def test_duplicate_keeps_canonical(pack_api, load_case, frozen_now):
    api = pack_api
    case, run_spec, pack = _build(api, load_case, frozen_now, "E-21")
    # Only the canonical copy is admitted.
    assert _admitted_local_ids(pack, run_spec) == ["E-21-1"]
    # The duplicate is silently collapsed: it is neither admitted nor an exclusion.
    excluded_ids = {e.case_local_id for e in pack.excluded_items}
    assert "E-21-2" not in excluded_ids
    assert pack.excluded_items == []


# --------------------------------------------------------------------------- #
# Conflict (E-22)
# --------------------------------------------------------------------------- #

def test_conflicting_items_share_group(pack_api, load_case, frozen_now):
    api = pack_api
    case, run_spec, pack = _build(api, load_case, frozen_now, "E-22")
    # Both retained, never silently overwritten.
    assert _admitted_local_ids(pack, run_spec) == ["E-22-1", "E-22-2"]
    groups = [item.conflict_group for item in pack.items]
    assert all(g is not None and g != "" for g in groups)
    assert groups[0] == groups[1]
    # The fixture fixes the expected group label; assert it exactly.
    expected_group = case["expected"]["conflict_groups"][0]["conflict_group"]
    assert groups[0] == expected_group


# --------------------------------------------------------------------------- #
# Integrity (E-23, E-30)
# --------------------------------------------------------------------------- #

def test_tampered_item_excluded(pack_api, load_case, frozen_now):
    api = pack_api
    case, run_spec, pack = _build(api, load_case, frozen_now, "E-23")
    # The original is kept; only the forged copy is refused.
    assert _admitted_local_ids(pack, run_spec) == ["E-23-1"]
    assert len(pack.excluded_items) == 1
    bad = pack.excluded_items[0]
    expected = case["expected"]["excluded"][0]
    assert bad.case_local_id == expected["case_local_id"]
    assert bad.reason_code == api.ReasonCode.INTEGRITY_VIOLATION
    assert bad.availability == api.Availability.UNAVAILABLE


def test_single_tampered_item_excluded(pack_api, load_case, frozen_now):
    api = pack_api
    case, _run_spec_, pack = _build(api, load_case, frozen_now, "E-30")
    assert pack.items == []
    assert len(pack.excluded_items) == 1
    bad = pack.excluded_items[0]
    assert bad.case_local_id == "E-30-1"
    assert bad.reason_code == api.ReasonCode.INTEGRITY_VIOLATION
    assert bad.availability == api.Availability.UNAVAILABLE


# --------------------------------------------------------------------------- #
# Provider failure (E-24, E-25)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("case_id", ["E-24", "E-25"])
def test_provider_failure_becomes_provider_exclusion(pack_api, load_case, frozen_now, case_id):
    api = pack_api
    case, _run_spec_, pack = _build(api, load_case, frozen_now, case_id)
    assert pack.items == []
    assert len(pack.excluded_items) == 1
    provider = pack.excluded_items[0]
    assert isinstance(provider, api.ExcludedItem)
    assert provider.case_local_id == "provider"
    assert provider.reason_code == api.ReasonCode.VENDOR_UNAVAILABLE
    assert provider.availability == api.Availability.UNREACHABLE


# --------------------------------------------------------------------------- #
# Stale cache (E-26)
# --------------------------------------------------------------------------- #

def test_offline_cache_is_stale(pack_api, load_case, frozen_now):
    api = pack_api
    case, _run_spec_, pack = _build(api, load_case, frozen_now, "E-26")
    # The old cache item is readable but must never masquerade as fresh.
    assert pack.items == []
    assert len(pack.excluded_items) == 1
    stale = pack.excluded_items[0]
    expected = case["expected"]["excluded"][0]
    assert stale.case_local_id == expected["case_local_id"]
    assert stale.availability == api.Availability.STALE
    assert stale.availability != api.Availability.AVAILABLE
    assert stale.reason_code == api.ReasonCode.STALE_DATA


# --------------------------------------------------------------------------- #
# Citation validation (E-29)
# --------------------------------------------------------------------------- #

def test_dangling_citation_rejected(pack_api, load_case, frozen_now):
    api = pack_api
    case = load_case("E-29")
    run_spec = _run_spec(api, frozen_now, case)
    # The pack itself builds: E-29-1 is a well-formed admitted item.
    pack = api.build_pack(run_spec, case["items"], pack_hash=PLACEHOLDER_PACK_HASH)
    assert _admitted_local_ids(pack, run_spec) == case["expected"]["admitted"]

    # The claim cites a case_local_id that does not exist; validation must fail
    # explicitly rather than dropping the dangling id.
    claim = case["claim"]
    with pytest.raises(Exception) as excinfo:
        api.validate_claims(pack, [claim])
    assert api.ReasonCode.INVALID_CITATION.value in str(excinfo.value)


def test_valid_citation_passes(pack_api, load_case, frozen_now):
    api = pack_api
    case = load_case("E-29")
    run_spec = _run_spec(api, frozen_now, case)
    pack = api.build_pack(run_spec, case["items"], pack_hash=PLACEHOLDER_PACK_HASH)

    # A claim that cites only the real case_local_id resolves cleanly (no raise).
    good_claim = {"claim_id": "C-ok", "text": "t", "evidence_ids": ["E-29-1"]}
    api.validate_claims(pack, [good_claim])


# --------------------------------------------------------------------------- #
# Contract-shape guards (fail fast if B's #21 shape drifts)
# --------------------------------------------------------------------------- #

def test_pack_hash_is_carried_unchanged(pack_api, load_case, frozen_now):
    api = pack_api
    _case, _run_spec_, pack = _build(api, load_case, frozen_now, "E-01")
    # The contract does not define the algorithm; the pack must carry what it is given.
    assert pack.pack_hash == PLACEHOLDER_PACK_HASH


def test_admitted_content_hash_matches_excerpt(pack_api, load_case, frozen_now):
    import hashlib

    api = pack_api
    case, _run_spec_, pack = _build(api, load_case, frozen_now, "E-01")
    item = pack.items[0]
    recomputed = hashlib.sha256(item.excerpt.encode("utf-8")).hexdigest()
    assert recomputed == item.content_hash
