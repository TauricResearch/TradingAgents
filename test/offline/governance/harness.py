"""Helpers for the offline Phase 7 governance checker specification."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECK_PERMISSIONS = REPO_ROOT / "tools" / "check_permissions.py"
CHECK_APPROVAL = REPO_ROOT / "tools" / "check_approval.py"


class GitRepo:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self._git("init")
        self._git("config", "user.email", "agent@example.test")
        self._git("config", "user.name", "Agent")

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.path,
            check=True,
            capture_output=True,
            text=True,
        )

    @property
    def head(self) -> str:
        return self._git("rev-parse", "HEAD").stdout.strip()

    def commit(
        self,
        files: dict[str, str] | None = None,
        message: str = "change",
        delete: tuple[str, ...] = (),
    ) -> str:
        for relative, content in (files or {}).items():
            target = self.path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        for relative in delete:
            target = self.path / relative
            if target.exists():
                target.unlink()
        self._git("add", "-A")
        self._git("commit", "-m", message)
        return self.head


def run_permissions(
    repo: GitRepo,
    base: str,
    head: str,
    role: str = "build-d",
    json_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    args = [
        sys.executable,
        str(CHECK_PERMISSIONS),
        "--repo",
        str(repo.path),
        "--base",
        base,
        "--head",
        head,
        "--role",
        role,
    ]
    if json_output:
        args.append("--json")
    return subprocess.run(args, cwd=repo.path, capture_output=True, text=True)


def run_approval(
    repo: GitRepo,
    record: str,
    implementation_base: str,
    implementation_head: str,
    registry: str | Path,
    author: str = "ZFebron491001",
    json_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    args = [
        sys.executable,
        str(CHECK_APPROVAL),
        "--repo",
        str(repo.path),
        "--record",
        record,
        "--implementation-base",
        implementation_base,
        "--implementation-head",
        implementation_head,
        "--registry",
        str(registry),
        "--author",
        author,
    ]
    if json_output:
        args.append("--json")
    return subprocess.run(args, cwd=repo.path, capture_output=True, text=True)
