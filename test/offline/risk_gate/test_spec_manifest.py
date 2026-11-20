"""Meta-test: validate the FR-04 test manifest without importing the implementation.

This test is expected to stay green while ``src/egta/risk_gate`` is absent. The
behavioural tests are expected to fail red until the approved implementation exists.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

from cases import ALL_CASES, CASES_BY_CATEGORY

EXPECTED_COUNTS = {"ACT": 22, "FND": 24, "EVD": 20, "IDM": 18, "ATM": 24, "SEC": 16}
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
}
ALLOWED_COMPONENTS = {"rules", "policy", "service", "ledger"}
ID_PATTERN = re.compile(r"^T-RISK-(ACT|FND|EVD|IDM|ATM|SEC)-\d{2}$")


def test_manifest_has_124_unique_identified_cases():
    assert len(ALL_CASES) == 124
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
        if category != "SEC":
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
        assert case.ledger_delta in {0, 1, 2, 3}, case.test_id
        assert case.version_delta in {0, 1, 2, 3}, case.test_id
        assert (case.expected_cash is None) or isinstance(case.expected_cash, str)
        if case.category == "ATM":
            assert case.params.get("scenario"), case.test_id
        if case.category == "SEC":
            assert case.params.get("scenario"), case.test_id


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
