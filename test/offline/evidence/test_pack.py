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

Frozen decisions (resolved from D's review of #25):

* ``pack_hash`` is **computed by ``build_pack``**, never supplied by the caller.
  It is a 64-hex digest, deterministic for identical input, and content-bound
  (changing an item changes it). The exact algorithm is NOT frozen here; it must
  match D's ``egta.risk_gate.canonical.recompute_evidence_hash`` (see ADR-004).
* ``validate_claims`` accepts **full** evidence ids
  (``<run_id>-<case_local_id>``), matching the risk gate's index
  (``risk_gate/rules.py``) — not the fixture's case-local ids.
* A dangling citation raises the concrete ``egta.evidence.InvalidCitation``
  (a ``ReasonCode.INVALID_CITATION`` error), and the message names the bad id.
* E-22 ``conflict_group`` is supplied explicitly by the caller; the test asserts
  the group equals the supplied key (no underivable label is frozen).
* E-26 staleness is frozen as "``source_type == 'cache'`` is always stale"
  (no freshness threshold in this spec), with a fresh non-cache control.
* ``pack.items`` preserves input order (admitted items only).

Fixture -> assertion map:

    normal admit    E-01 E-02 E-03 E-04 E-05 E-06 E-08 E-09 E-10 E-12
    field mapping   E-01 E-07 E-10 (raw -> EvidenceItem source_uri/published_at/
                    fetched_at/excerpt/trust_label/content_hash)
    time wired in   E-07 (date-only admitted), E-16/E-17 (future/undated excluded)
    dedupe          E-21  (only E-21-1 survives; E-21-2 neither admitted nor excluded)
    conflict        E-22  (both retained, same caller-supplied conflict_group)
    tampered        E-23  (E-23-2 excluded INTEGRITY_VIOLATION, E-23-1 kept),
                    E-30  (single item excluded INTEGRITY_VIOLATION)
    provider fail   E-24, E-25 (items=[], provider exclusion VENDOR_UNAVAILABLE/unreachable)
    stale cache     E-26  (item excluded STALE_DATA/stale, never available)
    citation        E-29  (pack builds, validate_claims raises InvalidCitation)
"""

from __future__ import annotations

from datetime import date

import pytest

pytestmark = pytest.mark.spec


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
    from egta.evidence import InvalidCitation  # noqa: F401
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
    api.InvalidCitation = InvalidCitation
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


def _full_id(run_spec, case_local_id: str) -> str:
    return f"{run_spec.run_id}-{case_local_id}"


def _admitted_local_ids(pack, run_spec) -> list[str]:
    prefix = f"{run_spec.run_id}-"
    return [item.evidence_id[len(prefix):] for item in pack.items]


def _build(api, load_case, frozen_now, case_id: str, *, conflict_key=None):
    case = load_case(case_id)
    run_spec = _run_spec(api, frozen_now, case)
    kwargs = {}
    if "provider_error" in case:
        kwargs["provider_error"] = case["provider_error"]
    if conflict_key is not None:
        kwargs["conflict_key"] = conflict_key
    pack = api.build_pack(run_spec, case["items"], **kwargs)
    assert isinstance(pack, api.EvidencePack), case_id
    return case, run_spec, pack


# --------------------------------------------------------------------------- #
# Normal admission + raw -> EvidenceItem field mapping
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

    for item in pack.items:
        assert isinstance(item, api.EvidenceItem)
        assert item.availability == api.Availability.AVAILABLE
        # INV-02: an admitted item carries no refusal code.
        assert item.reason_code is None


FIELD_MAPPING_CASES = ["E-01", "E-07", "E-10"]


@pytest.mark.parametrize("case_id", FIELD_MAPPING_CASES)
def test_raw_fields_map_to_evidence_item(pack_api, load_case, frozen_now, case_id):
    """FR-01 core: every traceability field survives raw -> EvidenceItem intact."""
    api = pack_api
    case, run_spec, pack = _build(api, load_case, frozen_now, case_id)

    raw_by_local = {raw["case_local_id"]: raw for raw in case["items"]}
    assert pack.items, case_id
    for item in pack.items:
        local = item.evidence_id[len(run_spec.run_id) + 1:]
        raw = raw_by_local[local]
        assert item.evidence_id == _full_id(run_spec, local)
        assert item.source_uri == raw["source_uri"]
        assert item.fetched_at == datetimes(api, raw["fetched_at"])
        # date-only fixtures keep day precision; timestamp fixtures keep the instant
        assert item.published_at == datetimes(api, raw["published_at"])
        assert item.excerpt == raw["excerpt"]
        assert item.trust_label == raw["trust_label"]
        assert item.content_hash == raw["content_hash"]


def datetimes(api, raw_value):
    """Normalize a fixture timestamp exactly as the contract exposes it."""
    if isinstance(raw_value, str) and len(raw_value) == 10:
        return date.fromisoformat(raw_value)
    from datetime import datetime

    return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))


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
# Conflict (E-22) — caller supplies the group key, no underivable label frozen
# --------------------------------------------------------------------------- #

def test_conflicting_items_share_group(pack_api, load_case, frozen_now):
    api = pack_api
    conflict_key = "aapl-revenue-2026Q3"
    case, run_spec, pack = _build(
        api, load_case, frozen_now, "E-22", conflict_key=conflict_key
    )
    # Both retained, never silently overwritten.
    assert _admitted_local_ids(pack, run_spec) == ["E-22-1", "E-22-2"]
    groups = [item.conflict_group for item in pack.items]
    # The caller-supplied key is what the items carry; the derivation rule is not
    # frozen, so we assert exactly the value we passed in.
    assert all(g == conflict_key for g in groups)


def test_non_conflicting_has_no_group(pack_api, load_case, frozen_now):
    api = pack_api
    _case, _run_spec_, pack = _build(
        api, load_case, frozen_now, "E-01", conflict_key="unused-key"
    )
    # A single item is never grouped, even if a conflict_key parameter is passed.
    assert pack.items[0].conflict_group is None


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
# Stale cache (E-26) — frozen rule: source_type == "cache" is always stale
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


def test_fresh_non_cache_item_is_admitted(pack_api, load_case, frozen_now):
    """Boundary: staleness is keyed on ``source_type == 'cache'``, not age.

    A recent, non-cache item must be admitted even though its timestamps are
    otherwise identical in shape to E-26 — proving the rule is not "old == stale".
    """
    case = load_case("E-26")
    item = dict(case["items"][0])
    item["source_type"] = "yahoo_news"
    item["case_local_id"] = "E-26-fresh"
    api = pack_api
    run_spec = _run_spec(api, frozen_now, case)
    pack = api.build_pack(run_spec, [item])
    assert _admitted_local_ids(pack, run_spec) == ["E-26-fresh"]
    assert pack.items[0].availability == api.Availability.AVAILABLE


# --------------------------------------------------------------------------- #
# Citation validation (E-29) — full evidence_id convention, concrete error
# --------------------------------------------------------------------------- #

def test_dangling_citation_rejected(pack_api, load_case, frozen_now):
    api = pack_api
    case = load_case("E-29")
    run_spec = _run_spec(api, frozen_now, case)
    # The pack itself builds: E-29-1 is a well-formed admitted item.
    pack = api.build_pack(run_spec, case["items"])
    assert _admitted_local_ids(pack, run_spec) == case["expected"]["admitted"]

    # Claims cite FULL evidence ids (<run_id>-<case_local_id>), matching the risk
    # gate's index. A dangling full id must fail explicitly, naming the bad id.
    dangling = _full_id(run_spec, "E-99-does-not-exist")
    claim = {
        "claim_id": "C-29",
        "text": case["claim"]["text"],
        "evidence_ids": [_full_id(run_spec, "E-29-1"), dangling],
    }
    with pytest.raises(api.InvalidCitation) as excinfo:
        api.validate_claims(pack, [claim])
    assert api.ReasonCode.INVALID_CITATION.value in str(excinfo.value)
    assert dangling in str(excinfo.value)


def test_valid_citation_passes(pack_api, load_case, frozen_now):
    api = pack_api
    case = load_case("E-29")
    run_spec = _run_spec(api, frozen_now, case)
    pack = api.build_pack(run_spec, case["items"])

    # A claim that cites only the real full evidence id resolves cleanly.
    good_claim = {
        "claim_id": "C-ok",
        "text": "t",
        "evidence_ids": [_full_id(run_spec, "E-29-1")],
    }
    api.validate_claims(pack, [good_claim])


# --------------------------------------------------------------------------- #
# pack_hash is build-computed, deterministic, content-bound (not caller-supplied)
# --------------------------------------------------------------------------- #

def _is_hex64(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        c in "0123456789abcdef" for c in value
    )


def test_pack_hash_is_computed_hex64(pack_api, load_case, frozen_now):
    api = pack_api
    _case, _run_spec_, pack = _build(api, load_case, frozen_now, "E-01")
    assert _is_hex64(pack.pack_hash), pack.pack_hash


def test_pack_hash_is_deterministic(pack_api, load_case, frozen_now):
    api = pack_api
    _, _, first = _build(api, load_case, frozen_now, "E-01")
    _, _, second = _build(api, load_case, frozen_now, "E-01")
    assert first.pack_hash == second.pack_hash


def test_pack_hash_is_content_bound(pack_api, load_case, frozen_now):
    api = pack_api
    case, run_spec, baseline = _build(api, load_case, frozen_now, "E-01")
    mutated_items = [dict(raw) for raw in case["items"]]
    mutated_items[0]["excerpt"] = mutated_items[0]["excerpt"] + " (tampered)"
    mutated = api.build_pack(run_spec, mutated_items)
    assert mutated.pack_hash != baseline.pack_hash


def test_pack_items_preserve_input_order(pack_api, load_case, frozen_now):
    api = pack_api
    case, run_spec, pack = _build(api, load_case, frozen_now, "E-22")
    # Admitted items keep the fixture (input) order, not a sorted/derived order.
    assert _admitted_local_ids(pack, run_spec) == [
        raw["case_local_id"] for raw in case["items"]
    ]


# --------------------------------------------------------------------------- #
# Contract-shape guard
# --------------------------------------------------------------------------- #

def test_admitted_content_hash_matches_excerpt(pack_api, load_case, frozen_now):
    import hashlib

    api = pack_api
    case, _run_spec_, pack = _build(api, load_case, frozen_now, "E-01")
    item = pack.items[0]
    recomputed = hashlib.sha256(item.excerpt.encode("utf-8")).hexdigest()
    assert recomputed == item.content_hash
