#!/usr/bin/env python3
"""Independent GATE-01 approval-record checker for EGTA.

Verifies an approval record against git history and hashes: record shape,
approver identity, requirement registry membership, approved-test ancestry,
per-file and aggregate hashes, and test drift after approval. Exit codes:
0 clean, 1 violation, 2 tool or usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

KEY_RE = re.compile(r"^([A-Za-z_]+):\s*(.*)$")
FILE_RE = re.compile(r"^\s+([0-9a-fA-F]{64})\s{2}(\S.*?)\s*$")
REQUIREMENT_RE = re.compile(
    r"^\s*(?:-\s*)?id:\s*['\"]?([A-Z][A-Z0-9_-]*-\d+)['\"]?\s*$",
    re.MULTILINE,
)
TASK_REQUIREMENT_RE = re.compile(r"\b([A-Z]{2,}-\d{2,})\b")


class CheckerError(Exception):
    """A tool, git, or usage failure that is not a policy violation."""


@dataclass(frozen=True)
class Violation:
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class ApprovalRecord:
    test_content_commit: str
    reviewed_pr_head: str
    merge_commit: str
    approved_by: str
    approved_at: str
    requirement: str
    files: dict[str, str]
    aggregate: str


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            errors="replace",
        )
    except OSError as exc:
        raise CheckerError(f"git unavailable: {exc}") from exc
    if check and result.returncode != 0:
        message = result.stderr.strip() or f"git {' '.join(args)} failed"
        raise CheckerError(message)
    return result


def _commit_exists(repo: Path, revision: str) -> bool:
    result = _git(repo, "rev-parse", "--verify", f"{revision}^{{commit}}", check=False)
    return result.returncode == 0


def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    result = _git(
        repo, "merge-base", "--is-ancestor", ancestor, descendant, check=False
    )
    if result.returncode not in (0, 1):
        message = result.stderr.strip() or "git merge-base --is-ancestor failed"
        raise CheckerError(message)
    return result.returncode == 0


def _changed_paths(repo: Path, base: str, head: str) -> list[str]:
    output = _git(
        repo, "diff", "--name-only", "-z", "--no-renames", base, head
    ).stdout
    return [path for path in output.split("\0") if path]


def _file_bytes(repo: Path, revision: str, path: str) -> bytes | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "show", f"{revision}:{path}"],
            capture_output=True,
        )
    except OSError as exc:
        raise CheckerError(f"git unavailable: {exc}") from exc
    if result.returncode != 0:
        return None
    return result.stdout


def _file_hash(repo: Path, revision: str, path: str) -> str | None:
    content = _file_bytes(repo, revision, path)
    if content is None:
        return None
    return hashlib.sha256(content).hexdigest()


def _aggregate(files: dict[str, str]) -> str:
    payload = "".join(f"{digest}  {path}\n" for path, digest in sorted(files.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _resolve(repo: Path, path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return repo / candidate


def _parse_record(text: str) -> ApprovalRecord | None:
    fields: dict[str, str] = {}
    files: dict[str, str] = {}
    aggregate: str | None = None
    mode = "top"
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("files"):
            mode = "files"
            continue
        if stripped.startswith("aggregate_sha256"):
            mode = "aggregate"
            _, _, inline = stripped.partition(":")
            inline = inline.strip()
            if inline:
                aggregate = inline
                mode = "top"
            continue
        if mode == "files":
            match = FILE_RE.match(line)
            if match:
                files[match.group(2)] = match.group(1).lower()
                continue
            mode = "top"
        if mode == "aggregate":
            aggregate = stripped
            mode = "top"
            continue
        match = KEY_RE.match(stripped)
        if match:
            fields[match.group(1)] = match.group(2).strip()

    requirement = fields.get("requirement", "").strip()
    if not requirement:
        match = TASK_REQUIREMENT_RE.search(text)
        if match:
            requirement = match.group(1)
    record = ApprovalRecord(
        test_content_commit=fields.get("test_content_commit", "").strip(),
        reviewed_pr_head=fields.get("reviewed_pr_head", "").strip(),
        merge_commit=fields.get("merge_commit", "").strip(),
        approved_by=fields.get("approved_by", "").strip(),
        approved_at=fields.get("approved_at", "").strip(),
        requirement=requirement,
        files=files,
        aggregate=(aggregate or "").lower(),
    )
    if not (
        record.test_content_commit
        and record.reviewed_pr_head
        and record.approved_by
        and record.approved_at
        and record.requirement
        and record.files
        and record.aggregate
    ):
        return None
    return record


def _requirement_ids(text: str) -> set[str]:
    return {match.upper() for match in REQUIREMENT_RE.findall(text)}


def check_approval(
    repo: Path,
    record_path: str,
    implementation_base: str,
    implementation_head: str,
    registry_path: str,
    author: str,
) -> list[Violation]:
    if not repo.is_dir():
        raise CheckerError(f"repository path does not exist: {repo}")
    if not _commit_exists(repo, implementation_base):
        raise CheckerError(f"implementation base not found: {implementation_base}")
    if not _commit_exists(repo, implementation_head):
        raise CheckerError(f"implementation head not found: {implementation_head}")

    record_file = _resolve(repo, record_path)
    if not record_file.is_file():
        return [Violation("RECORD_MISSING", f"approval record not found: {record_path}")]
    record = _parse_record(record_file.read_text(encoding="utf-8", errors="replace"))
    if record is None:
        return [
            Violation(
                "RECORD_INVALID",
                "approval record is missing or has malformed required fields",
            )
        ]
    if "PENDING" in record.approved_by.upper() or "PENDING" in record.approved_at.upper():
        return [Violation("APPROVAL_PENDING", "approval record is still pending")]
    if author and author.lower() in record.approved_by.lower():
        return [
            Violation(
                "SELF_APPROVAL",
                f"approver field names the implementation author: {author}",
            )
        ]

    registry_file = _resolve(repo, registry_path)
    if not registry_file.is_file():
        return [
            Violation("REGISTRY_MISSING", f"requirements registry not found: {registry_path}")
        ]
    requirements = _requirement_ids(
        registry_file.read_text(encoding="utf-8", errors="replace")
    )
    if record.requirement.upper() not in requirements:
        return [
            Violation(
                "REQUIREMENT_UNKNOWN",
                f"{record.requirement} is not present in {registry_path}",
            )
        ]

    if not _commit_exists(repo, record.test_content_commit):
        return [
            Violation(
                "RECORD_INVALID",
                f"test_content_commit not found: {record.test_content_commit}",
            )
        ]
    if not _is_ancestor(repo, record.test_content_commit, implementation_base):
        return [
            Violation(
                "TEST_BASE_MISSING",
                "implementation base does not contain the approved test commit",
            )
        ]
    if not _commit_exists(repo, record.reviewed_pr_head):
        return [
            Violation(
                "REVIEWED_HEAD_MISSING",
                f"reviewed_pr_head not found: {record.reviewed_pr_head}",
            )
        ]
    if not _is_ancestor(repo, record.reviewed_pr_head, implementation_head):
        return [
            Violation(
                "REVIEWED_HEAD_MISSING",
                "reviewed PR head is not an ancestor of the implementation head",
            )
        ]

    for path, expected in sorted(record.files.items()):
        actual = _file_hash(repo, record.test_content_commit, path)
        if actual != expected:
            return [
                Violation(
                    "HASH_MISMATCH",
                    f"approved test hash mismatch for {path}",
                )
            ]
    if _aggregate(record.files) != record.aggregate:
        return [
            Violation(
                "AGGREGATE_MISMATCH",
                "aggregate_sha256 does not match the recorded per-file hash lines",
            )
        ]

    for path in _changed_paths(repo, implementation_base, implementation_head):
        if path.startswith("test/"):
            return [
                Violation(
                    "TEST_DRIFT",
                    f"implementation changes a test path after approval: {path}",
                )
            ]
    for path, expected in sorted(record.files.items()):
        if _file_hash(repo, implementation_head, path) != expected:
            return [
                Violation(
                    "TEST_DRIFT",
                    f"approved test content changed in the implementation: {path}",
                )
            ]
    return []


def _emit(violations: Sequence[Violation], json_output: bool) -> None:
    if json_output:
        payload = {
            "ok": not violations,
            "violations": [violation.as_dict() for violation in violations],
        }
        print(json.dumps(payload, sort_keys=True))
        return
    if not violations:
        print("OK: approval record verified")
        return
    for violation in violations:
        print(f"{violation.code}: {violation.message}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--record", required=True)
    parser.add_argument("--implementation-base", required=True)
    parser.add_argument("--implementation-head", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--author", required=True)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    try:
        violations = check_approval(
            Path(args.repo),
            args.record,
            args.implementation_base,
            args.implementation_head,
            args.registry,
            args.author,
        )
    except CheckerError as exc:
        print(f"TOOL_ERROR: {exc}", file=sys.stderr)
        return 2
    _emit(violations, args.json_output)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
