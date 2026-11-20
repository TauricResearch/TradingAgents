"""Meta-test: validate the FR-04 test manifest without importing the implementation.

This test is expected to stay green while ``src/egta/risk_gate`` is absent. The
behavioural tests are expected to fail red until the approved implementation exists.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

from cases import ALL_CASES, CASES_BY_CATEGORY, STATIC_SEC_IDS
from fakes import TEST_FIXTURE_PARAMETERS

EXPECTED_COUNTS = {"ACT": 22, "FND": 24, "EVD": 22, "IDM": 18, "ATM": 24, "SEC": 16}
MODULES = {
    "ACT": "test_actions_quantities",
    "FND": "test_funds_positions_costs",
    "EVD": "test_evidence_time_policy",
    "IDM": "test_identity_idempotency",
    "ATM": "test_atomicity_concurrency",
    "SEC": "test_security_boundaries",
}
REQUIRED_REQUIREMENTS = {
    "FR-04",
    "NFR-04",
    "NFR-05",
    "NFR-09",
    "INV-01",
    "INV-04",
    "INV-06",
    "INV-07",
}
ALLOWED_STATUSES = {"APPROVED", "REJECTED", "REVIEW", "BLOCKED"}
ALLOWED_REASONS = {
    None,
    "INVALID_OUTPUT",
    "POLICY_REJECTED",
    "EVIDENCE_MISSING",
    "FUTURE_DATA",
    "STALE_PORTFOLIO",
    "INCOMPATIBLE_STATE",
    "AUDIT_UNAVAILABLE",
    "INVALID_CITATION",
    "INTEGRITY_VIOLATION",
    "INVALID_TIME",
    "STALE_DATA",
    "VENDOR_UNAVAILABLE",
}
ALLOWED_COMPONENTS = {"rules", "policy", "service", "ledger"}
ALLOWED_KINDS = {"outcome", "idempotency", "atomicity", "security", "static"}
ID_PATTERN = re.compile(r"^T-RISK-(ACT|FND|EVD|IDM|ATM|SEC)-\d{2}$")

HASH_MISMATCH_IDS = {
    "T-RISK-EVD-02",
    "T-RISK-EVD-03",
    "T-RISK-EVD-04",
    "T-RISK-EVD-11",
    "T-RISK-EVD-15",
    "T-RISK-IDM-02",
    "T-RISK-IDM-05",
    "T-RISK-IDM-06",
    "T-RISK-IDM-07",
    "T-RISK-IDM-08",
    "T-RISK-IDM-09",
    "T-RISK-IDM-14",
}
MALFORMED_HASH_IDS = {"T-RISK-IDM-03", "T-RISK-IDM-04"}
AVAILABILITY_REASONS = {
    "T-RISK-EVD-21": "VENDOR_UNAVAILABLE",
    "T-RISK-EVD-22": "STALE_DATA",
}
HOLD_CASES = {"T-RISK-ACT-19", "T-RISK-ACT-20", "T-RISK-EVD-20"}


def _by_id() -> dict[str, object]:
    return {case.test_id: case for case in ALL_CASES}


def test_manifest_has_126_unique_identified_cases():
    assert len(ALL_CASES) == 126
    ids = [case.test_id for case in ALL_CASES]
    assert len(ids) == len(set(ids))
    for case in ALL_CASES:
        assert ID_PATTERN.match(case.test_id), case.test_id


def test_manifest_category_counts_and_coverage():
    assert set(CASES_BY_CATEGORY) == set(EXPECTED_COUNTS)
    for category, expected in EXPECTED_COUNTS.items():
        cases = CASES_BY_CATEGORY[category]
        assert len(cases) == expected, category
        assert {case.test_id.split("-")[2] for case in cases} == {category}
        assert any(case.classification == "positive" for case in cases), category
        assert any(case.classification == "negative" for case in cases), category
    covered = {
        requirement
        for category_cases in CASES_BY_CATEGORY.values()
        for case in category_cases
        for requirement in case.requirement_ids
    }
    assert covered >= REQUIRED_REQUIREMENTS


def test_manifest_fields_are_complete_and_consistent():
    for case in ALL_CASES:
        assert case.requirement_ids, case.test_id
        assert case.description, case.test_id
        assert isinstance(case.params, dict), case.test_id
        assert case.expected_status in ALLOWED_STATUSES, case.test_id
        assert case.expected_reason in ALLOWED_REASONS, case.test_id
        assert case.classification in {"positive", "negative"}, case.test_id
        assert case.component in ALLOWED_COMPONENTS, case.test_id
        assert case.failure_mode, case.test_id
        assert case.test_kind in ALLOWED_KINDS, case.test_id
        assert case.ledger_delta in {0, 1, 2, 3}, case.test_id
        assert case.version_delta in {0, 1, 2, 3}, case.test_id
        assert (case.expected_cash is None) or isinstance(case.expected_cash, str)
        assert (case.expected_positions is None) or isinstance(
            case.expected_positions, dict
        )
        assert (case.expected_raw_positions is None) or isinstance(
            case.expected_raw_positions, dict
        )
        if case.category == "ATM":
            assert case.params.get("scenario"), case.test_id
        if case.category == "SEC":
            assert case.params.get("scenario"), case.test_id


def test_classification_is_outcome_only():
    for case in ALL_CASES:
        expected = "positive" if case.expected_status == "APPROVED" else "negative"
        assert case.classification == expected, case.test_id


def test_static_inspection_split_is_explicit():
    static = [case for case in ALL_CASES if case.test_kind == "static"]
    assert {case.test_id for case in static} == STATIC_SEC_IDS
    assert len(static) == 7
    assert len(ALL_CASES) - len(static) == 119
    kinds = dict.fromkeys(ALLOWED_KINDS, 0)
    for case in ALL_CASES:
        kinds[case.test_kind] += 1
    assert kinds == {
        "outcome": 68,
        "idempotency": 18,
        "atomicity": 24,
        "security": 9,
        "static": 7,
    }


def test_hash_mismatch_rule_is_uniform():
    cases = _by_id()
    for test_id in HASH_MISMATCH_IDS:
        case = cases[test_id]
        assert case.expected_status == "REJECTED", test_id
        assert case.expected_reason == "INTEGRITY_VIOLATION", test_id
    for test_id in MALFORMED_HASH_IDS:
        case = cases[test_id]
        assert case.expected_status == "REJECTED", test_id
        assert case.expected_reason == "INVALID_OUTPUT", test_id


def test_availability_state_cases_are_explicit():
    cases = _by_id()
    for test_id, reason in AVAILABILITY_REASONS.items():
        case = cases[test_id]
        assert case.expected_status == "REVIEW", test_id
        assert case.expected_reason == reason, test_id
        assert case.ledger_delta == 0, test_id


def test_hold_evidence_rule_is_consistent():
    cases = _by_id()
    for test_id in ("T-RISK-ACT-19", "T-RISK-ACT-20"):
        case = cases[test_id]
        assert case.expected_status == "APPROVED", test_id
        assert case.ledger_delta == 0, test_id
    hold_without_pack = cases["T-RISK-EVD-20"]
    assert hold_without_pack.expected_status == "REVIEW"
    assert hold_without_pack.expected_reason == "EVIDENCE_MISSING"
    assert hold_without_pack.ledger_delta == 0


def test_fixture_parameters_are_marked_test_only():
    assert TEST_FIXTURE_PARAMETERS == {
        "price_freshness_seconds": 240,
        "fee_bps": "10",
        "slippage_bps": "0",
    }
    import fakes

    doc = (fakes.__doc__ or "").lower()
    assert "test fixture parameters are not product policy" in doc.replace("\n", " ")


def test_every_case_is_wired_to_exactly_one_test_module():
    wired = []
    for category, module_name in MODULES.items():
        module = importlib.import_module(module_name)
        assert list(module.CASES) == list(CASES_BY_CATEGORY[category]), module_name
        wired.extend(module.CASES)
    assert [case.test_id for case in wired] == [case.test_id for case in ALL_CASES]


def test_spec_files_do_not_hide_failures_with_xfail_or_skip():
    directory = Path(__file__).resolve().parent
    for path in directory.glob("test_*.py"):
        if path.name == Path(__file__).name:
            continue
        text = path.read_text(encoding="utf-8")
        assert "xfail" not in text, path.name
        assert "mark.skip" not in text, path.name
        assert "pytest.skip" not in text, path.name
