"""Meta-test: validate the Phase 7 governance test manifest without the tools."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

from cases import ALL_GOV_CASES, APPROVAL_CASES, CASES_BY_CATEGORY, PERM_CASES

EXPECTED_COUNTS = {"PERM": 16, "APPR": 16}
MODULES = {
    "PERM": "test_permissions",
    "APPR": "test_approval",
}
REQUIRED_REQUIREMENTS = {"GATE-01", "GATE-02", "NFR-07", "D3"}
ID_PATTERN = re.compile(r"^T-GOV-(PERM|APPR)-\d{2}$")
ALLOWED_STATUSES = {0, 1}


def test_manifest_has_32_unique_cases():
    assert len(ALL_GOV_CASES) == 32
    ids = [case.test_id for case in ALL_GOV_CASES]
    assert len(ids) == len(set(ids))
    for case in ALL_GOV_CASES:
        assert ID_PATTERN.match(case.test_id), case.test_id


def test_manifest_category_counts_and_coverage():
    assert set(CASES_BY_CATEGORY) == set(EXPECTED_COUNTS)
    for category, expected in EXPECTED_COUNTS.items():
        cases = CASES_BY_CATEGORY[category]
        assert len(cases) == expected, category
        assert any(case.classification == "positive" for case in cases), category
        assert any(case.classification == "negative" for case in cases), category
    covered = {
        requirement
        for case in ALL_GOV_CASES
        for requirement in case.requirement_ids
    }
    assert covered >= REQUIRED_REQUIREMENTS


def test_manifest_fields_are_complete():
    for case in ALL_GOV_CASES:
        assert case.requirement_ids, case.test_id
        assert case.description, case.test_id
        assert case.expected_exit in ALLOWED_STATUSES, case.test_id
        assert (case.expected_code is None) or isinstance(case.expected_code, str)
        assert case.classification in {"positive", "negative"}, case.test_id
        assert case.failure_mode, case.test_id
        if case.classification == "positive":
            assert case.expected_exit == 0, case.test_id
        else:
            assert case.expected_exit != 0, case.test_id


def test_every_case_is_wired_to_one_test_module():
    wired = []
    for category, module_name in MODULES.items():
        module = importlib.import_module(module_name)
        assert list(module.CASES) == list(CASES_BY_CATEGORY[category]), module_name
        wired.extend(module.CASES)
    assert [case.test_id for case in wired] == [case.test_id for case in ALL_GOV_CASES]


def test_permission_and_approval_manifests_are_distinct():
    assert len(PERM_CASES) == 16
    assert len(APPROVAL_CASES) == 16
    assert not ({case.test_id for case in PERM_CASES} & {case.test_id for case in APPROVAL_CASES})


def test_spec_files_do_not_hide_failures_with_xfail_or_skip():
    directory = Path(__file__).resolve().parent
    for path in directory.glob("test_*.py"):
        if path.name == Path(__file__).name:
            continue
        text = path.read_text(encoding="utf-8")
        assert "xfail" not in text, path.name
        assert "mark.skip" not in text, path.name
        assert "pytest.skip" not in text, path.name
