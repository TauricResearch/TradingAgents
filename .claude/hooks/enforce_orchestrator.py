#!/usr/bin/env python3
"""
Enforce Orchestrator Validation - PROJECT.md Gatekeeper (Phase 1)

Ensures orchestrator validated PROJECT.md alignment before implementation.

This prevents:
- Users bypassing /auto-implement
- Features implemented without PROJECT.md alignment check
- Work proceeding without strategic direction validation

Source of truth: PROJECT.md ARCHITECTURE (orchestrator PRIMARY MISSION)

Exit codes:
    0: Orchestrator validation found (or strict mode disabled)
    2: No orchestrator validation - BLOCKS commit

Usage:
    # As PreCommit hook (automatic in strict mode)
    python enforce_orchestrator.py
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
import subprocess


def is_strict_mode_enabled() -> bool:
    """Check if strict mode is enabled."""
    settings_file = Path(".claude/settings.local.json")
    if not settings_file.exists():
        return False

    try:
        with open(settings_file) as f:
            settings = json.load(f)
        return settings.get("strict_mode", False)
    except Exception:
        return False


def has_project_md() -> bool:
    """Check if PROJECT.md exists."""
    return Path(".claude/PROJECT.md").exists()


def check_orchestrator_in_sessions() -> bool:
    """
    Check for orchestrator activity in recent session files.

    Looks for evidence in last 3 session files or files from last hour.
    """
    sessions_dir = Path("docs/sessions")
    if not sessions_dir.exists():
        return False

    # Get recent session files (last 3 or last hour)
    cutoff_time = datetime.now() - timedelta(hours=1)
    recent_sessions = []

    for session_file in sessions_dir.glob("*.md"):
        # Check modification time
        mtime = datetime.fromtimestamp(session_file.stat().st_mtime)
        if mtime > cutoff_time:
            recent_sessions.append(session_file)

    # If no sessions in last hour, check last 3 files
    if not recent_sessions:
        all_sessions = sorted(sessions_dir.glob("*.md"),
                            key=lambda f: f.stat().st_mtime,
                            reverse=True)
        recent_sessions = all_sessions[:3]

    # Search for orchestrator evidence
    for session in recent_sessions:
        try:
            content = session.read_text().lower()

            # Look for orchestrator markers
            markers = [
                "orchestrator",
                "project.md alignment",
                "validates alignment",
                "alignment check",
            ]

            if any(marker in content for marker in markers):
                return True
        except Exception:
            continue

    return False


def check_commit_message() -> bool:
    """Check if commit message indicates orchestrator validation."""
    try:
        # Get the staged commit message if it exists
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=%B"],
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode == 0:
            commit_msg = result.stdout.lower()

            # Look for orchestrator markers in commit message
            if "orchestrator" in commit_msg or "project.md" in commit_msg:
                return True
    except Exception:
        pass

    return False


def get_staged_files() -> list:
    """Get list of staged files."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            check=True
        )
        return [f for f in result.stdout.strip().split('\n') if f]
    except Exception:
        return []


def is_docs_only_commit() -> bool:
    """Check if this is a documentation-only commit (allow without orchestrator)."""
    staged = get_staged_files()
    if not staged:
        return True

    # If all files are docs, markdown, or configs, allow
    doc_extensions = {'.md', '.txt', '.json', '.yml', '.yaml', '.toml'}
    doc_paths = {'docs/', 'README', 'CHANGELOG', 'LICENSE', '.claude/'}

    for file in staged:
        # Skip if it's a source file
        if file.startswith('src/') or file.startswith('lib/'):
            return False

        # Check extension
        ext = Path(file).suffix.lower()
        if ext and ext not in doc_extensions:
            return False

        # Check if in doc path
        if not any(file.startswith(path) for path in doc_paths):
            # Check if it's a hook or test file (allow)
            if not (file.startswith('hooks/') or file.startswith('tests/')):
                return False

    return True


def main():
    """Enforce orchestrator validation in strict mode."""

    # Only run on PreCommit
    try:
        data = json.loads(sys.stdin.read())
        if data.get("hook") != "PreCommit":
            sys.exit(0)
    except Exception:
        # If not running as hook, exit
        sys.exit(0)

    # Check if strict mode is enabled
    if not is_strict_mode_enabled():
        # Not in strict mode - no enforcement
        sys.exit(0)

    # Check if PROJECT.md exists
    if not has_project_md():
        # No PROJECT.md - can't enforce alignment
        print("ℹ️  No PROJECT.md found - orchestrator enforcement skipped",
              file=sys.stderr)
        sys.exit(0)

    # Check if this is a docs-only commit (allow without orchestrator)
    if is_docs_only_commit():
        print("ℹ️  Documentation-only commit - orchestrator not required",
              file=sys.stderr)
        sys.exit(0)

    # Check for orchestrator evidence
    has_orchestrator = (
        check_orchestrator_in_sessions() or
        check_commit_message()
    )

    if has_orchestrator:
        print("✅ Orchestrator validation detected", file=sys.stderr)
        sys.exit(0)

    # No orchestrator evidence - BLOCK
    print("\n" + "=" * 80, file=sys.stderr)
    print("❌ ORCHESTRATOR VALIDATION REQUIRED", file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    print(file=sys.stderr)
    print("Strict mode requires orchestrator to validate PROJECT.md alignment",
          file=sys.stderr)
    print("before implementation work begins.", file=sys.stderr)
    print(file=sys.stderr)
    print("PROJECT.md ARCHITECTURE (orchestrator PRIMARY MISSION):", file=sys.stderr)
    print("  1. Read PROJECT.md (GOALS, SCOPE, CONSTRAINTS)", file=sys.stderr)
    print("  2. Validate: Does feature serve GOALS?", file=sys.stderr)
    print("  3. Validate: Is feature IN SCOPE?", file=sys.stderr)
    print("  4. Validate: Respects CONSTRAINTS?", file=sys.stderr)
    print("  5. BLOCK if not aligned OR proceed with agent pipeline",
          file=sys.stderr)
    print(file=sys.stderr)
    print("No orchestrator activity found in:", file=sys.stderr)
    print("  - Recent session files (docs/sessions/)", file=sys.stderr)
    print("  - Commit message", file=sys.stderr)
    print(file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    print("HOW TO FIX", file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    print(file=sys.stderr)
    print("Option 1: Use /auto-implement (recommended):", file=sys.stderr)
    print("  /auto-implement \"your feature description\"", file=sys.stderr)
    print("  → orchestrator validates alignment automatically", file=sys.stderr)
    print("  → Full 7-agent pipeline executes", file=sys.stderr)
    print(file=sys.stderr)
    print("Option 2: Manual orchestrator invocation:", file=sys.stderr)
    print("  \"orchestrator: validate this feature against PROJECT.md\"", file=sys.stderr)
    print("  → Creates session file with validation evidence", file=sys.stderr)
    print(file=sys.stderr)
    print("Option 3: Disable strict mode (not recommended):", file=sys.stderr)
    print("  Edit .claude/settings.local.json:", file=sys.stderr)
    print('  {"strict_mode": false}', file=sys.stderr)
    print(file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    print("Strict mode enforces PROJECT.md as gatekeeper.", file=sys.stderr)
    print("This prevents scope drift and misaligned features.", file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    print(file=sys.stderr)

    sys.exit(2)  # Block commit


if __name__ == "__main__":
    main()
