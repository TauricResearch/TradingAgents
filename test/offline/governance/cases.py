"""Test-case manifest for the Phase 7 permission and approval checkers.

Each case defines the CLI behaviour the independent checker must implement. The
checks themselves are tooling, not FR-04 runtime code; no risk-gate behaviour is
changed. The behavioural tests are expected RED until `tools/check_permissions.py`
and `tools/check_approval.py` are approved and implemented.
"""

from __future__ import annotations

from dataclasses import dataclass, field

BASE_FILES = {
    "README.md": "# governance fixture\n",
    ".opencode/rules.md": "# human-only rules\n",
    ".github/workflows/ci.yml": "name: CI\n",
    "src/egta/risk_gate/__init__.py": "",
    "src/egta/budget/governor.py": "",
    "src/egta/contracts/events.py": "",
    "docs/architecture/risk-policy.md": "# policy\n",
    "docs/approvals/test-hash-old.txt": "old\n",
}

APPROVAL_TEST_PATH = "test/offline/governance/fixture_test.py"
APPROVAL_TEST_CONTENT = "def test_fixture():\n    assert True\n"
REGISTRY_CONTENT = (
    "schema_version: '1.0'\n"
    "requirements:\n"
    "  - id: FR-04\n"
    "    type: functional\n"
    "  - id: FR-05\n"
    "    type: functional\n"
)


@dataclass(frozen=True)
class PermissionCase:
    test_id: str
    requirement_ids: tuple[str, ...]
    description: str
    role: str
    files: dict[str, str] = field(default_factory=dict)
    delete: tuple[str, ...] = ()
    expected_exit: int = 0
    expected_code: str | None = None
    json_output: bool = False
    classification: str = "negative"
    failure_mode: str = "unauthorized change must be rejected"


@dataclass(frozen=True)
class ApprovalCase:
    test_id: str
    requirement_ids: tuple[str, ...]
    description: str
    scenario: str
    expected_exit: int
    expected_code: str | None
    json_output: bool = False
    classification: str = "negative"
    failure_mode: str = "unverifiable approval must be rejected"


def _p(
    suffix: str,
    description: str,
    role: str,
    *,
    files: dict[str, str] | None = None,
    delete: tuple[str, ...] = (),
    expected_exit: int,
    expected_code: str | None,
    json_output: bool = False,
    classification: str = "negative",
    failure_mode: str = "unauthorized change must be rejected",
) -> PermissionCase:
    return PermissionCase(
        test_id=f"T-GOV-PERM-{suffix}",
        requirement_ids=("GATE-02", "NFR-07", "D3"),
        description=description,
        role=role,
        files=files or {},
        delete=delete,
        expected_exit=expected_exit,
        expected_code=expected_code,
        json_output=json_output,
        classification=classification,
        failure_mode=failure_mode,
    )


def _a(
    suffix: str,
    description: str,
    scenario: str,
    *,
    expected_exit: int,
    expected_code: str | None,
    json_output: bool = False,
    classification: str = "negative",
    failure_mode: str = "unverifiable approval must be rejected",
) -> ApprovalCase:
    return ApprovalCase(
        test_id=f"T-GOV-APPR-{suffix}",
        requirement_ids=("GATE-01", "NFR-07"),
        description=description,
        scenario=scenario,
        expected_exit=expected_exit,
        expected_code=expected_code,
        json_output=json_output,
        classification=classification,
        failure_mode=failure_mode,
    )


PERM_CASES = [
    _p(
        "01",
        "allowed risk_gate file for build-d",
        "build-d",
        files={"src/egta/risk_gate/new_rule.py": "x = 1\n"},
        expected_exit=0,
        expected_code=None,
        classification="positive",
        failure_mode="allowed module file must pass",
    ),
    _p(
        "02",
        "allowed D-owned risk policy doc",
        "build-d",
        files={"docs/architecture/risk-policy.md": "# updated policy\n"},
        expected_exit=0,
        expected_code=None,
        classification="positive",
        failure_mode="allowed D doc must pass",
    ),
    _p(
        "03",
        "other module source path",
        "build-d",
        files={"src/egta/budget/new.py": "x = 1\n"},
        expected_exit=1,
        expected_code="PATH_NOT_ALLOWED",
    ),
    _p(
        "04",
        "human-only rules file",
        "build-d",
        files={".opencode/rules.md": "# changed by agent\n"},
        expected_exit=1,
        expected_code="HUMAN_ONLY",
    ),
    _p(
        "05",
        "CI workflow change",
        "build-d",
        files={".github/workflows/ci.yml": "name: changed\n"},
        expected_exit=1,
        expected_code="PROTECTED_PATH",
    ),
    _p(
        "06",
        "contracts change",
        "build-d",
        files={"src/egta/contracts/events.py": "# changed\n"},
        expected_exit=1,
        expected_code="CONTRACT_PROTECTED",
    ),
    _p(
        "07",
        "approval record change",
        "build-d",
        files={"docs/approvals/test-hash-old.txt": "changed\n"},
        expected_exit=1,
        expected_code="APPROVAL_PROTECTED",
    ),
    _p(
        "08",
        "cross-module private import",
        "build-d",
        files={
            "src/egta/risk_gate/bad.py": "from egta.budget.governor import reserve\n"
        },
        expected_exit=1,
        expected_code="CROSS_MODULE_IMPORT",
    ),
    _p(
        "09",
        "allowed contracts import",
        "build-d",
        files={
            "src/egta/risk_gate/ok.py": "from egta.contracts.events import RunEvent\n"
        },
        expected_exit=0,
        expected_code=None,
        classification="positive",
        failure_mode="public contracts import must pass",
    ),
    _p(
        "10",
        "dotenv credential reference",
        "build-d",
        files={"src/egta/risk_gate/bad.py": "ENV_FILE = '.env'\n"},
        expected_exit=1,
        expected_code="CREDENTIAL_REFERENCE",
    ),
    _p(
        "11",
        "ssh credential path reference",
        "build-d",
        files={"src/egta/risk_gate/bad.py": "KEY = '~/.ssh/id_rsa'\n"},
        expected_exit=1,
        expected_code="CREDENTIAL_REFERENCE",
    ),
    _p(
        "12",
        "delete human-only file",
        "build-d",
        delete=(".opencode/rules.md",),
        expected_exit=1,
        expected_code="HUMAN_ONLY",
    ),
    _p(
        "13",
        "human role edits rules",
        "human",
        files={".opencode/rules.md": "# human edit\n"},
        expected_exit=0,
        expected_code=None,
        classification="positive",
        failure_mode="human-maintained rules may be edited by the human role",
    ),
    _p(
        "14",
        "verify role edits source",
        "verify",
        files={"src/egta/risk_gate/verified.py": "x = 1\n"},
        expected_exit=1,
        expected_code="ROLE_NOT_ALLOWED",
    ),
    _p(
        "15",
        "clean diff",
        "build-d",
        expected_exit=0,
        expected_code=None,
        classification="positive",
        failure_mode="no changes must pass",
    ),
    _p(
        "16",
        "JSON violation output",
        "build-d",
        files={"src/egta/budget/new.py": "x = 1\n"},
        expected_exit=1,
        expected_code="PATH_NOT_ALLOWED",
        json_output=True,
    ),
]


APPROVAL_CASES = [
    _a(
        "01",
        "valid approval record and implementation",
        "valid",
        expected_exit=0,
        expected_code=None,
        classification="positive",
        failure_mode="valid approval must pass",
    ),
    _a(
        "02",
        "missing approval record",
        "missing_record",
        expected_exit=1,
        expected_code="RECORD_MISSING",
    ),
    _a(
        "03",
        "approval still pending",
        "pending",
        expected_exit=1,
        expected_code="APPROVAL_PENDING",
    ),
    _a(
        "04",
        "self approval",
        "self_approval",
        expected_exit=1,
        expected_code="SELF_APPROVAL",
    ),
    _a(
        "05",
        "requirement id not in registry",
        "unknown_requirement",
        expected_exit=1,
        expected_code="REQUIREMENT_UNKNOWN",
    ),
    _a(
        "06",
        "requirements registry missing",
        "missing_registry",
        expected_exit=1,
        expected_code="REGISTRY_MISSING",
    ),
    _a(
        "07",
        "per-file test hash mismatch",
        "hash_mismatch",
        expected_exit=1,
        expected_code="HASH_MISMATCH",
    ),
    _a(
        "08",
        "aggregate test hash mismatch",
        "aggregate_mismatch",
        expected_exit=1,
        expected_code="AGGREGATE_MISMATCH",
    ),
    _a(
        "09",
        "implementation base does not contain approved tests",
        "test_base_missing",
        expected_exit=1,
        expected_code="TEST_BASE_MISSING",
    ),
    _a(
        "10",
        "implementation modifies approved test",
        "test_drift",
        expected_exit=1,
        expected_code="TEST_DRIFT",
    ),
    _a(
        "11",
        "valid JSON output",
        "valid",
        expected_exit=0,
        expected_code=None,
        json_output=True,
        classification="positive",
        failure_mode="valid JSON report must pass",
    ),
    _a(
        "12",
        "reviewed head missing",
        "reviewed_head_missing",
        expected_exit=1,
        expected_code="RECORD_INVALID",
    ),
    _a(
        "13",
        "approved_by missing",
        "approved_by_missing",
        expected_exit=1,
        expected_code="RECORD_INVALID",
    ),
    _a(
        "14",
        "aggregate field missing",
        "record_malformed",
        expected_exit=1,
        expected_code="RECORD_INVALID",
    ),
    _a(
        "15",
        "implementation adds an unapproved test file",
        "extra_test_changed",
        expected_exit=1,
        expected_code="TEST_DRIFT",
    ),
    _a(
        "16",
        "reviewed head is not an ancestor",
        "reviewed_head_not_ancestor",
        expected_exit=1,
        expected_code="REVIEWED_HEAD_MISSING",
    ),
]


ALL_GOV_CASES = [*PERM_CASES, *APPROVAL_CASES]
CASES_BY_CATEGORY = {"PERM": PERM_CASES, "APPR": APPROVAL_CASES}
