#!/usr/bin/env python3
"""Independent permission checker for EGTA role-scoped diffs.

Reads a git base/head pair, classifies changed paths by role, and rejects
human-only, protected, cross-module, and credential-bearing changes. Exit codes:
0 clean, 1 violation, 2 tool or usage error.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

HUMAN_ONLY_PATHS = {".opencode/rules.md"}
PROTECTED_PREFIXES = (".github/",)
APPROVAL_PREFIX = "docs/approvals/"
CONTRACT_PREFIX = "src/egta/contracts/"
OWN_MODULE = {
    "build-a": "egta.evidence",
    "build-b": "egta.budget",
    "build-c": "egta.deliberation",
    "build-d": "egta.risk_gate",
    "build-e": "egta.evaluation",
}
ALLOWED_PREFIXES = {
    "build-a": (
        "src/egta/evidence/",
        "test/offline/evidence/",
        "test/live/test_data_provider.py",
        "docs/req/",
        "docs/evidence/FR-01/",
        "docs/ai-use-log-A-fragment.yaml",
        "tools/check_requirements.py",
    ),
    "build-b": (
        "src/egta/budget/",
        "src/egta/adapters/",
        "src/egta/app/",
        "test/offline/budget/",
        "test/offline/adapters/",
        "test/offline/app/",
        "test/live/",
        "docs/architecture/architecture-blueprint.md",
        "docs/architecture/adr/001-modular-extension.md",
        "docs/evidence/FR-02/",
        "docs/ai-use-log-B-fragment.yaml",
    ),
    "build-c": (
        "src/egta/deliberation/",
        "prompts/",
        "test/offline/deliberation/",
        "docs/architecture/adr/002-context-and-deliberation.md",
        "docs/evidence/FR-03/",
        "docs/ai-use-log-C-fragment.yaml",
        "Prompt.md",
    ),
    "build-d": (
        "src/egta/risk_gate/",
        "test/offline/risk_gate/",
        "test/fixtures/security/",
        "tools/check_permissions.py",
        "tools/check_approval.py",
        "AGENTS.md",
        "docs/architecture/adr/003-risk-authority.md",
        "docs/architecture/invariants.md",
        "docs/architecture/permission-model.md",
        "docs/architecture/risk-policy.md",
        "docs/architecture/threat-model.md",
        "docs/code-governance/mcp-tool-manifest.md",
        "docs/evidence/FR-04/",
        "docs/ai-use-log-D-fragment.yaml",
    ),
    "build-e": (
        "src/egta/evaluation/",
        "test/offline/evaluation/",
        "test/offline/integration/",
        "test/live/",
        "docs/evidence/FR-05/",
        "docs/ai-use-log-E-fragment.yaml",
    ),
}
VERIFY_PREFIXES = (
    "docs/evidence/",
    "docs/review-memo.md",
    "docs/reviews/",
    "docs/verification/",
)
PLAN_PREFIXES = ("docs/",)
CREDENTIAL_SCAN_SUFFIXES = (
    ".bash",
    ".cfg",
    ".ini",
    ".json",
    ".jsonc",
    ".py",
    ".sh",
    ".toml",
    ".yaml",
    ".yml",
    ".zsh",
)
CREDENTIAL_PATTERNS = (
    re.compile(r"(?<![\w.])\." + "env" + r"(?!\.example)(?![\w.])"),
    re.compile(r"~/" + r"\.ssh(?:/|$)"),
    re.compile(r"/" + r"\.ssh/"),
    re.compile(r"\bid_" + r"(?:rsa|ed25519)\b"),
    re.compile(r"\bAWS_SECRET_" + r"ACCESS_KEY\b"),
    re.compile(r"\bOPENAI_" + r"API_KEY\b"),
    re.compile(r"\bANTHROPIC_" + r"API_KEY\b"),
)


class CheckerError(Exception):
    """A tool, git, or usage failure that is not a policy violation."""


@dataclass(frozen=True)
class Violation:
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


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


def _changed_paths(repo: Path, base: str, head: str) -> list[tuple[str, str]]:
    output = _git(
        repo, "diff", "--name-status", "-z", "--no-renames", base, head
    ).stdout
    parts = [part for part in output.split("\0") if part]
    if len(parts) % 2 != 0:
        raise CheckerError("unexpected git diff --name-status output")
    return [(parts[index], parts[index + 1]) for index in range(0, len(parts), 2)]


def _file_text(repo: Path, revision: str, path: str) -> str | None:
    result = _git(repo, "show", f"{revision}:{path}", check=False)
    if result.returncode != 0:
        return None
    return result.stdout


def _normalise_role(role: str) -> str:
    return role.strip().lower().replace("_", "-")


def _allowed_prefixes(role: str) -> tuple[str, ...] | None:
    if role == "verify":
        return VERIFY_PREFIXES
    if role == "plan":
        return PLAN_PREFIXES
    return ALLOWED_PREFIXES.get(role)


def _path_violation(role: str, path: str) -> str | None:
    if path in HUMAN_ONLY_PATHS:
        return "HUMAN_ONLY"
    if path.startswith(".opencode/"):
        return "PROTECTED_PATH"
    if path.startswith(PROTECTED_PREFIXES) or path == "CODEOWNERS":
        return "PROTECTED_PATH"
    if path.startswith(APPROVAL_PREFIX):
        return "APPROVAL_PROTECTED"
    if path.startswith(CONTRACT_PREFIX):
        return "CONTRACT_PROTECTED"
    prefixes = _allowed_prefixes(role)
    if prefixes is None:
        return "ROLE_NOT_ALLOWED"
    if any(path == prefix or path.startswith(prefix) for prefix in prefixes):
        return None
    if role.startswith("build-"):
        return "PATH_NOT_ALLOWED"
    return "ROLE_NOT_ALLOWED"


def _import_roots(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module)
    return roots


def _import_allowed(role: str, root: str) -> bool:
    if root == "egta":
        return True
    if root.startswith("egta.contracts"):
        return True
    own = OWN_MODULE.get(role)
    return bool(own and (root == own or root.startswith(f"{own}.")))


def _content_violations(
    repo: Path, role: str, head: str, changed: list[tuple[str, str]]
) -> list[Violation]:
    violations: list[Violation] = []
    for status, path in changed:
        if status == "D":
            continue
        if path.endswith("." + "env"):
            violations.append(
                Violation(
                    "CREDENTIAL_REFERENCE",
                    path,
                    "credential file must not be changed",
                )
            )
            continue
        content = _file_text(repo, head, path)
        if content is None:
            continue
        if path.endswith(CREDENTIAL_SCAN_SUFFIXES) and any(
            pattern.search(content) for pattern in CREDENTIAL_PATTERNS
        ):
            violations.append(
                Violation(
                    "CREDENTIAL_REFERENCE",
                    path,
                    "changed file references a credential path or secret name",
                )
            )
        if path.startswith("src/egta/") and path.endswith(".py"):
            for root in sorted(_import_roots(content)):
                if root.startswith("egta.") and not _import_allowed(role, root):
                    violations.append(
                        Violation(
                            "CROSS_MODULE_IMPORT",
                            path,
                            f"cross-module import {root} is not allowed for {role}",
                        )
                    )
    return violations


def check_permissions(
    repo: Path, base: str, head: str, role: str
) -> list[Violation]:
    if not repo.is_dir():
        raise CheckerError(f"repository path does not exist: {repo}")
    if not _commit_exists(repo, base):
        raise CheckerError(f"base revision not found: {base}")
    if not _commit_exists(repo, head):
        raise CheckerError(f"head revision not found: {head}")
    normalised = _normalise_role(role)
    if normalised == "human":
        return []
    if normalised not in {*OWN_MODULE, "verify", "plan"}:
        return [Violation("ROLE_NOT_ALLOWED", ".", f"unknown role: {role}")]
    changed = _changed_paths(repo, base, head)
    violations: list[Violation] = []
    seen: set[tuple[str, str]] = set()
    for status, path in changed:
        code = _path_violation(normalised, path)
        if code is not None and (code, path) not in seen:
            seen.add((code, path))
            violations.append(
                Violation(code, path, f"{status} change is not allowed for {normalised}")
            )
    for violation in _content_violations(repo, normalised, head, changed):
        key = (violation.code, violation.path)
        if key not in seen:
            seen.add(key)
            violations.append(violation)
    return violations


def _emit(violations: Sequence[Violation], json_output: bool) -> None:
    if json_output:
        payload = {
            "ok": not violations,
            "violations": [violation.as_dict() for violation in violations],
        }
        print(json.dumps(payload, sort_keys=True))
        return
    if not violations:
        print("OK: no permission violations")
        return
    for violation in violations:
        print(f"{violation.code}: {violation.path}: {violation.message}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    try:
        violations = check_permissions(
            Path(args.repo), args.base, args.head, args.role
        )
    except CheckerError as exc:
        print(f"TOOL_ERROR: {exc}", file=sys.stderr)
        return 2
    _emit(violations, args.json_output)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
