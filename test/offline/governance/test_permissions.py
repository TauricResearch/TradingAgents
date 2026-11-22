"""Phase 7 permission checker specification (16 cases, expected RED until tools land)."""

from __future__ import annotations

import pytest
from cases import BASE_FILES, PERM_CASES
from harness import run_permissions

CASES = PERM_CASES


@pytest.mark.parametrize("case", CASES, ids=[case.test_id for case in CASES])
def test_permissions(case, git_repo):
    base = git_repo.commit(BASE_FILES, "base")
    if case.files or case.delete:
        head = git_repo.commit(case.files, "case", delete=case.delete)
    else:
        head = base
    result = run_permissions(
        git_repo, base, head, role=case.role, json_output=case.json_output
    )
    output = result.stdout + result.stderr
    assert result.returncode == case.expected_exit, (
        f"{case.test_id}: expected exit {case.expected_exit}, "
        f"got {result.returncode}\n{output}"
    )
    if case.expected_code is not None:
        assert case.expected_code in output, (
            f"{case.test_id}: expected code {case.expected_code!r}\n{output}"
        )
