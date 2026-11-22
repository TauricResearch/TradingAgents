"""Phase 7 approval checker specification (16 cases, expected RED until tools land)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from cases import (
    APPROVAL_CASES,
    APPROVAL_TEST_CONTENT,
    APPROVAL_TEST_PATH,
    REGISTRY_CONTENT,
)
from harness import run_approval

CASES = APPROVAL_CASES
RECORD_PATH = "docs/approvals/test-hash-FR-04-governance.txt"
REGISTRY_PATH = "docs/req/requirements.yaml"


def _digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _aggregate(file_digest: str) -> str:
    line = f"{file_digest}  {APPROVAL_TEST_PATH}\n"
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def _record(
    test_commit: str,
    *,
    file_digest: str,
    aggregate: str,
    approved_by: str = "A (@yuxiangdu39)",
    approved_at: str = "2026-11-22T00:00:00Z",
    reviewed_head: str | None = None,
    requirement: str = "FR-04",
    omit_reviewed_head: bool = False,
    omit_approved_by: bool = False,
    omit_aggregate: bool = False,
) -> str:
    reviewed = reviewed_head if reviewed_head is not None else test_commit
    lines = [
        "PR/task: FR-04 governance tools",
        f"requirement: {requirement}",
        "branch: spec/FR-04-governance-tools",
        f"test_content_commit: {test_commit}",
        f"merge_commit: {test_commit}",
    ]
    if not omit_reviewed_head:
        lines.append(f"reviewed_pr_head: {reviewed}")
    lines.append("files (per-file SHA-256):")
    lines.append(f"  {file_digest}  {APPROVAL_TEST_PATH}")
    if not omit_aggregate:
        lines.append("aggregate_sha256:")
        lines.append(f"  {aggregate}")
    if not omit_approved_by:
        lines.append(f"approved_by: {approved_by}")
    lines.append(f"approved_at: {approved_at}")
    return "\n".join(lines) + "\n"


def build_approval_repo(case, git_repo):
    root_commit = git_repo.commit({"README.md": "root\n"}, "root")
    test_commit = git_repo.commit(
        {
            APPROVAL_TEST_PATH: APPROVAL_TEST_CONTENT,
            REGISTRY_PATH: REGISTRY_CONTENT,
        },
        "tests",
    )
    file_digest = _digest(APPROVAL_TEST_CONTENT)
    aggregate = _aggregate(file_digest)

    scenario = case.scenario
    approved_by = "A (@yuxiangdu39)"
    approved_at = "2026-11-22T00:00:00Z"
    reviewed_head: str | None = None
    requirement = "FR-04"
    omit_reviewed = False
    omit_approved = False
    omit_aggregate = False
    author = "ZFebron491001"

    if scenario == "pending":
        approved_by = "PENDING"
        approved_at = "PENDING"
    elif scenario == "self_approval":
        author = "yuxiangdu39"
    elif scenario == "unknown_requirement":
        requirement = "FR-99"
    elif scenario == "hash_mismatch":
        file_digest = "0" * 64
        aggregate = _aggregate(file_digest)
    elif scenario == "aggregate_mismatch":
        aggregate = "0" * 64
    elif scenario == "reviewed_head_missing":
        omit_reviewed = True
    elif scenario == "approved_by_missing":
        omit_approved = True
    elif scenario == "record_malformed":
        omit_aggregate = True
    elif scenario == "reviewed_head_not_ancestor":
        reviewed_head = "f" * 40

    record = _record(
        test_commit,
        file_digest=file_digest,
        aggregate=aggregate,
        approved_by=approved_by,
        approved_at=approved_at,
        reviewed_head=reviewed_head,
        requirement=requirement,
        omit_reviewed_head=omit_reviewed,
        omit_approved_by=omit_approved,
        omit_aggregate=omit_aggregate,
    )

    if scenario != "missing_record":
        record_commit = git_repo.commit({RECORD_PATH: record}, "approval record")
    else:
        record_commit = test_commit

    if scenario == "test_drift":
        head = git_repo.commit(
            {
                APPROVAL_TEST_PATH: "def test_fixture():\n    assert False\n",
            },
            "test drift",
        )
    elif scenario == "extra_test_changed":
        head = git_repo.commit(
            {
                "src/egta/risk_gate/impl.py": "x = 1\n",
                "test/offline/governance/extra_test.py": "def test_extra():\n    assert True\n",
            },
            "impl plus test",
        )
    else:
        head = git_repo.commit({"src/egta/risk_gate/impl.py": "x = 1\n"}, "impl")

    if scenario == "test_base_missing":
        base = root_commit
    elif scenario == "missing_record":
        base = test_commit
    else:
        base = record_commit
    registry: str | Path = git_repo.path / REGISTRY_PATH
    if scenario == "missing_registry":
        registry = git_repo.path / "docs/req/missing.yaml"
    return record_commit, base, head, registry, author


@pytest.mark.parametrize("case", CASES, ids=[case.test_id for case in CASES])
def test_approval(case, git_repo):
    _, base, head, registry, author = build_approval_repo(case, git_repo)
    result = run_approval(
        git_repo,
        RECORD_PATH,
        base,
        head,
        registry,
        author=author,
        json_output=case.json_output,
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
    if case.json_output and result.returncode == 0:
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
