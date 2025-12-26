#!/usr/bin/env python3
"""
Session Quality Validation - Output-Based Enforcement

Validates that autonomous pipeline produced quality outputs by checking
session file content, not process execution.

This is Anthropic-compliant:
- Checks OUTPUTS (session content) not process (checkpoints)
- WARNS (exit 1) instead of BLOCKS (exit 2)
- TRUSTS the model to produce quality
- SIMPLE and FAST (< 1 second)
- DECLARATIVE patterns

Exit codes:
    0: Quality validated or not applicable
    1: Quality warnings detected (proceeds but warns)

Usage:
    # As PreCommit hook (automatic in strict mode)
    python validate_session_quality.py
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
import subprocess

# Declarative quality markers (Anthropic principle)
QUALITY_MARKERS = {
    "research": {
        "markers": [
            "patterns",
            "best practices",
            "sources",
            "recommendations",
            "security considerations",
            "github.com",
            "stackoverflow",
            ".io",
            "official",
        ],
        "minimum": 3,  # At least 3 markers for quality
        "description": "Research findings with patterns, sources, and recommendations",
    },
    "planning": {
        "markers": [
            "architecture",
            "components",
            "approach",
            "implementation",
            "design",
            "structure",
            "flow",
            "diagram",
        ],
        "minimum": 3,
        "description": "Implementation plan with architecture and approach",
    },
    "review": {
        "markers": [
            "code quality",
            "review",
            "issues",
            "recommendations",
            "approved",
            "changes requested",
            "concerns",
            "looks good",
        ],
        "minimum": 2,
        "description": "Code review with quality assessment",
    },
    "security": {
        "markers": [
            "security",
            "vulnerability",
            "secrets",
            "authentication",
            "authorization",
            "validation",
            "sanitization",
            "no issues found",
        ],
        "minimum": 1,
        "description": "Security assessment",
    },
}


def is_strict_mode_enabled() -> bool:
    """Check if strict mode is enabled."""
    settings_file = Path(".claude/settings.local.json")
    if not settings_file.exists():
        return False

    try:
        with open(settings_file) as f:
            settings = json.load(f)
        # Check both strict_mode field and presence of strict mode hooks
        return settings.get("strict_mode", False)
    except Exception:
        return False


def get_recent_sessions(hours: int = 2) -> list[Path]:
    """
    Get recent session files (last 2 hours or last 3 files).

    Args:
        hours: Time window in hours

    Returns:
        List of session file paths, sorted by modification time (newest first)
    """
    sessions_dir = Path("docs/sessions")
    if not sessions_dir.exists():
        return []

    cutoff_time = datetime.now() - timedelta(hours=hours)
    recent_sessions = []

    for session_file in sessions_dir.glob("*.md"):
        if not session_file.name.startswith("checkpoints"):
            mtime = datetime.fromtimestamp(session_file.stat().st_mtime)
            if mtime > cutoff_time:
                recent_sessions.append(session_file)

    # If no recent sessions, get last 3
    if not recent_sessions:
        all_sessions = [
            f for f in sessions_dir.glob("*.md")
            if not f.name.startswith("checkpoints")
        ]
        recent_sessions = sorted(
            all_sessions, key=lambda f: f.stat().st_mtime, reverse=True
        )[:3]

    return recent_sessions


def check_phase_quality(content: str, phase: str) -> tuple[bool, int, int]:
    """
    Check if a phase produced quality output.

    Args:
        content: Session file content (lowercase)
        phase: Phase name (research, planning, review, security)

    Returns:
        (passed, markers_found, minimum_required)
    """
    config = QUALITY_MARKERS[phase]
    markers = config["markers"]
    minimum = config["minimum"]

    markers_found = sum(1 for marker in markers if marker in content)

    return markers_found >= minimum, markers_found, minimum


def has_source_changes() -> bool:
    """Check if commit includes source code changes."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            check=True,
        )
        files = [f for f in result.stdout.strip().split("\n") if f]

        # Source files (not just docs/comments)
        source_patterns = [
            lambda f: f.startswith("src/"),
            lambda f: f.startswith("lib/"),
            lambda f: f.endswith(".py") and not f.startswith("tests/"),
            lambda f: f.endswith(".js") and not f.startswith("tests/"),
            lambda f: f.endswith(".ts") and not f.startswith("tests/"),
            lambda f: f.endswith(".go") and not f.startswith("tests/"),
            lambda f: f.endswith(".rs") and not f.startswith("tests/"),
        ]

        return any(
            any(pattern(f) for pattern in source_patterns)
            for f in files
        )
    except Exception:
        return False


def is_lightweight_change() -> bool:
    """
    Check if this is a lightweight change that doesn't need full validation.

    Lightweight changes:
    - Docs-only (README, docs/, *.md)
    - Comments-only
    - Formatting-only
    - Typo fixes
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            check=True,
        )
        files = [f for f in result.stdout.strip().split("\n") if f]

        # Check commit message for lightweight indicators
        try:
            msg_result = subprocess.run(
                ["git", "log", "-1", "--pretty=%B"],
                capture_output=True,
                text=True,
                check=True,
            )
            commit_msg = msg_result.stdout.lower()

            if any(
                pattern in commit_msg
                for pattern in [
                    "docs:",
                    "chore:",
                    "typo",
                    "comment",
                    "formatting",
                    "style:",
                ]
            ):
                return True
        except Exception:
            pass

        # Only docs/markdown files
        if all(
            f.startswith("docs/")
            or f == "README.md"
            or f.endswith(".md")
            or f.startswith("templates/")
            for f in files
            if f
        ):
            return True

    except Exception:
        pass

    return False


def main():
    """Validate session quality."""

    # Read hook input
    try:
        data = json.loads(sys.stdin.read())
        if data.get("hook") != "PreCommit":
            sys.exit(0)
    except Exception:
        sys.exit(0)

    # Only run in strict mode
    if not is_strict_mode_enabled():
        sys.exit(0)

    # Allow lightweight changes without validation
    if is_lightweight_change():
        print("ℹ️  Lightweight change - skipping session validation", file=sys.stderr)
        sys.exit(0)

    # Only validate if source code changed
    if not has_source_changes():
        sys.exit(0)

    # Get recent session files
    session_files = get_recent_sessions()

    if not session_files:
        print("ℹ️  No recent session files found - first commit?", file=sys.stderr)
        sys.exit(0)  # Allow (might be first commit or manual work)

    # Read session content
    session_content = "\n".join(
        f.read_text() for f in session_files
    ).lower()

    # Check each phase
    warnings = {}
    for phase, config in QUALITY_MARKERS.items():
        passed, found, minimum = check_phase_quality(session_content, phase)
        if not passed:
            warnings[phase] = {
                "found": found,
                "minimum": minimum,
                "description": config["description"],
            }

    # If warnings found, show them
    if warnings:
        print("\n" + "=" * 80, file=sys.stderr)
        print("⚠️  SESSION QUALITY WARNINGS", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(
            "\nSome SDLC phases appear incomplete based on session file content:",
            file=sys.stderr,
        )
        print(file=sys.stderr)

        for phase, info in warnings.items():
            print(f"  ⚠️  {phase.upper()}", file=sys.stderr)
            print(f"     Expected: {info['description']}", file=sys.stderr)
            print(
                f"     Found: {info['found']}/{info['minimum']} quality markers",
                file=sys.stderr,
            )
            print(file=sys.stderr)

        print("=" * 80, file=sys.stderr)
        print("WHAT THIS MEANS", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(
            "\nSession files may be missing some quality evidence.",
            file=sys.stderr,
        )
        print(
            "This could mean agents skipped steps or produced thin outputs.",
            file=sys.stderr,
        )
        print(file=sys.stderr)

        print("=" * 80, file=sys.stderr)
        print("OPTIONS", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(file=sys.stderr)
        print("1. Review session files to verify quality:", file=sys.stderr)
        print(f"   Recent sessions: {len(session_files)} files", file=sys.stderr)
        for sf in session_files[:3]:
            print(f"   - docs/sessions/{sf.name}", file=sys.stderr)
        print(file=sys.stderr)

        print("2. Re-run with /auto-implement for complete pipeline:", file=sys.stderr)
        print("   /auto-implement \"your feature description\"", file=sys.stderr)
        print(file=sys.stderr)

        print("3. Proceed anyway (you're in control):", file=sys.stderr)
        print("   This is a WARNING, not a block", file=sys.stderr)
        print("   You can commit and address later", file=sys.stderr)
        print(file=sys.stderr)

        print("=" * 80, file=sys.stderr)
        print("Session quality validation encourages thoroughness.", file=sys.stderr)
        print("You decide whether to proceed or improve quality first.", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(file=sys.stderr)

        # Exit 1 = WARNING (allow but show to user)
        # This is Anthropic principle: warn, don't block
        sys.exit(1)

    # All quality checks passed
    print("✅ Session quality validated", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
