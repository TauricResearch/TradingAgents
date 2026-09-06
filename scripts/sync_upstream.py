#!/usr/bin/env python3
"""Fetch TauricResearch/TradingAgents and merge it into a dated sync branch.

Never force-syncs. Never uses -X ours / -X theirs. Stops on conflicts so they
can be resolved with docs/UPSTREAM_SYNC.md (keep every fork addition AND the
upstream fix).

Usage (from repo root):
    python scripts/sync_upstream.py
    python scripts/sync_upstream.py --check   # report only, no branch
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

UPSTREAM_URL = "https://github.com/TauricResearch/TradingAgents.git"
UPSTREAM_REF = "upstream/main"
FORK_ONLY_HINTS = (
    "scripts/decide.py",
    "scripts/service.py",
    "tradingagents/dataflows/indian_news.py",
    "tradingagents/agents/managers/decision_model.py",
    "tradingagents/agents/managers/factor_extractor.py",
    "docker-compose.yml",
    "Dockerfile",
    ".github/workflows/deploy.yml",
    ".github/workflows/build-image.yml",
)


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, text=True, capture_output=True)


def out(args: list[str]) -> str:
    return run(args).stdout.strip()


def ensure_upstream() -> None:
    remotes = out(["git", "remote"])
    if "upstream" not in remotes.splitlines():
        run(["git", "remote", "add", "upstream", UPSTREAM_URL])
    run(["git", "fetch", "upstream", "--tags", "--prune"])
    run(["git", "fetch", "origin", "--prune"])


def ahead_behind() -> tuple[int, int]:
    left, right = out(["git", "rev-list", "--left-right", "--count", f"origin/main...{UPSTREAM_REF}"]).split()
    return int(left), int(right)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report delta only")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    git_dir = run(["git", "-C", str(root), "rev-parse", "--git-dir"], check=False)
    if git_dir.returncode != 0:
        print("run this from the TradingAgents repo root", file=sys.stderr)
        return 2
    os.chdir(root)

    ensure_upstream()
    fork_only, upstream_only = ahead_behind()
    print(f"origin/main vs {UPSTREAM_REF}: {fork_only} fork-only, {upstream_only} upstream-only")
    if upstream_only == 0:
        print("already up to date with upstream/main")
        return 0

    print("incoming:")
    print(out(["git", "log", "--oneline", "--no-merges", f"origin/main..{UPSTREAM_REF}"]))
    if args.check:
        return 0

    stamp = dt.date.today().isoformat()
    branch = f"sync/upstream-{stamp}"
    status = out(["git", "status", "--porcelain"])
    if status:
        print("working tree is dirty — commit or stash first", file=sys.stderr)
        return 1

    run(["git", "checkout", "-B", branch, "origin/main"])
    merge = run(["git", "merge", "--no-edit", UPSTREAM_REF], check=False)
    if merge.returncode == 0:
        print(f"clean merge on {branch}")
        print(f"next: git push -u origin {branch} && gh pr create --fill")
        return 0

    conflicts = out(["git", "diff", "--name-only", "--diff-filter=U"]).splitlines()
    print(f"merge stopped with {len(conflicts)} conflict(s). Do not use -X ours/theirs.")
    print("see docs/UPSTREAM_SYNC.md — keep fork additions AND the upstream fix.")
    for path in conflicts:
        flag = "  (fork-only — keep ours)" if path in FORK_ONLY_HINTS else ""
        print(f"  {path}{flag}")
    print(f"resolve on {branch}, then: git add -u && git commit")
    return 1


if __name__ == "__main__":
    sys.exit(main())
