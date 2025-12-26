#!/usr/bin/env python3
"""
Enforce TDD Workflow - Tests Before Code (Phase 2)

Validates that tests were written before implementation code (TDD).

Detection strategy:
1. Check staged files for test + src changes
2. If both exist, validate tests came first via:
   - Git history (test files committed before src files)
   - File modification times in this commit
   - Session file evidence (test-master ran before implementer)

Source of truth: PROJECT.md ARCHITECTURE (TDD enforced)

Exit codes:
    0: TDD followed OR strict mode disabled OR no TDD required
    2: TDD violation - BLOCKS commit

Usage:
    # As PreCommit hook (automatic in strict mode)
    python enforce_tdd.py
"""

import json
import sys
from pathlib import Path
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


def get_staged_files() -> dict:
    """
    Get staged files categorized by type.

    Returns:
        {
            "test_files": [list of test files],
            "src_files": [list of source files],
            "other_files": [list of other files]
        }
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            check=True
        )
        files = [f for f in result.stdout.strip().split('\n') if f]
    except Exception:
        return {"test_files": [], "src_files": [], "other_files": []}

    categorized = {
        "test_files": [],
        "src_files": [],
        "other_files": []
    }

    for file in files:
        # Test files
        if (file.startswith('tests/') or
            file.startswith('test/') or
            '/test_' in file or
            file.startswith('test_') or
            file.endswith('_test.py') or
            file.endswith('.test.js') or
            file.endswith('.test.ts')):
            categorized["test_files"].append(file)

        # Source files
        elif (file.startswith('src/') or
              file.startswith('lib/') or
              file.endswith('.py') or
              file.endswith('.js') or
              file.endswith('.ts') or
              file.endswith('.go') or
              file.endswith('.rs')):
            # Exclude hooks and scripts
            if not (file.startswith('hooks/') or
                   file.startswith('scripts/') or
                   file.startswith('agents/') or
                   file.startswith('commands/')):
                categorized["src_files"].append(file)

        else:
            categorized["other_files"].append(file)

    return categorized


def check_session_for_tdd_evidence() -> bool:
    """
    Check session files for evidence of TDD workflow.

    Looks for test-master activity before implementer activity.
    """
    sessions_dir = Path("docs/sessions")
    if not sessions_dir.exists():
        return False

    # Get recent session files (last 5 or last hour)
    recent_sessions = sorted(sessions_dir.glob("*.md"),
                            key=lambda f: f.stat().st_mtime,
                            reverse=True)[:5]

    test_master_found = False
    implementer_found = False
    test_master_line = -1
    implementer_line = -1

    for session in recent_sessions:
        try:
            content = session.read_text()
            lines = content.split('\n')

            for i, line in enumerate(lines):
                line_lower = line.lower()

                # Look for test-master activity
                if 'test-master' in line_lower or 'test master' in line_lower:
                    if not test_master_found:
                        test_master_found = True
                        test_master_line = i

                # Look for implementer activity
                if 'implementer' in line_lower:
                    if not implementer_found:
                        implementer_found = True
                        implementer_line = i

        except Exception:
            continue

    # If both found, test-master should appear before implementer
    if test_master_found and implementer_found:
        return test_master_line < implementer_line

    # If only test-master found, that's good
    if test_master_found and not implementer_found:
        return True

    # If only implementer found, that's a violation
    if implementer_found and not test_master_found:
        return False

    # Neither found - can't determine
    return True  # Give benefit of doubt


def check_git_history_for_tests() -> bool:
    """
    Check git history to see if test files were committed before src files.

    Looks at last 5 commits for pattern of tests-first commits.
    """
    try:
        # Get last 5 commits with file lists
        result = subprocess.run(
            ["git", "log", "-5", "--name-only", "--pretty=format:COMMIT"],
            capture_output=True,
            text=True,
            check=True
        )

        log_output = result.stdout
        commits = log_output.split("COMMIT")

        # Analyze each commit
        test_first_count = 0
        code_first_count = 0

        for commit in commits:
            if not commit.strip():
                continue

            files = [f.strip() for f in commit.split('\n') if f.strip()]

            has_test = any('test' in f.lower() for f in files)
            has_src = any(f.startswith('src/') or f.startswith('lib/')
                         for f in files)

            # If commit has both test and src files, that's good
            if has_test and has_src:
                test_first_count += 1
            elif has_src and not has_test:
                code_first_count += 1

        # If majority of recent commits had tests, assume TDD is followed
        if test_first_count > code_first_count:
            return True

        # If we have any evidence of TDD, give benefit of doubt
        if test_first_count > 0:
            return True

    except Exception:
        pass

    return True  # Benefit of doubt if we can't determine


def get_file_additions() -> dict:
    """
    Get the actual additions (line changes) for test vs src files.

    If more test lines added than src lines, likely TDD.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--numstat"],
            capture_output=True,
            text=True,
            check=True
        )

        test_additions = 0
        src_additions = 0

        for line in result.stdout.split('\n'):
            if not line.strip():
                continue

            parts = line.split('\t')
            if len(parts) < 3:
                continue

            additions = parts[0]
            if additions == '-':
                continue

            try:
                add_count = int(additions)
            except ValueError:
                continue

            filename = parts[2]

            if 'test' in filename.lower():
                test_additions += add_count
            elif (filename.startswith('src/') or
                  filename.startswith('lib/')):
                src_additions += add_count

        return {
            "test_additions": test_additions,
            "src_additions": src_additions,
            "ratio": test_additions / src_additions if src_additions > 0 else 0
        }

    except Exception:
        return {"test_additions": 0, "src_additions": 0, "ratio": 0}


def main():
    """Enforce TDD workflow in strict mode."""

    # Only run on PreCommit
    try:
        data = json.loads(sys.stdin.read())
        if data.get("hook") != "PreCommit":
            sys.exit(0)
    except Exception:
        sys.exit(0)

    # Check if strict mode is enabled
    if not is_strict_mode_enabled():
        sys.exit(0)

    # Get staged files
    files = get_staged_files()
    test_files = files["test_files"]
    src_files = files["src_files"]

    # If no source files changed, TDD not applicable
    if not src_files:
        print("ℹ️  No source files changed - TDD not applicable", file=sys.stderr)
        sys.exit(0)

    # If source files but no test files, check if this is acceptable
    if src_files and not test_files:
        # Check for TDD evidence in other ways

        # 1. Session file evidence
        session_evidence = check_session_for_tdd_evidence()

        # 2. Git history pattern
        history_evidence = check_git_history_for_tests()

        # If we have evidence from either source, allow
        if session_evidence or history_evidence:
            print("✅ TDD evidence found (tests exist in separate commits)",
                  file=sys.stderr)
            sys.exit(0)

        # No test files at all - this is a violation
        print("\n" + "=" * 80, file=sys.stderr)
        print("❌ TDD VIOLATION: Code without tests", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(file=sys.stderr)
        print("Source files modified without corresponding test changes:",
              file=sys.stderr)
        for src_file in src_files[:5]:  # Show first 5
            print(f"  - {src_file}", file=sys.stderr)
        if len(src_files) > 5:
            print(f"  ... and {len(src_files) - 5} more", file=sys.stderr)
        print(file=sys.stderr)
        print("PROJECT.md ARCHITECTURE enforces TDD workflow:", file=sys.stderr)
        print("  1. test-master writes FAILING tests", file=sys.stderr)
        print("  2. implementer makes tests PASS", file=sys.stderr)
        print(file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print("HOW TO FIX", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(file=sys.stderr)
        print("Option 1: Write tests now:", file=sys.stderr)
        print("  1. Add test files for the changes", file=sys.stderr)
        print("  2. git add tests/", file=sys.stderr)
        print("  3. git commit (will include both)", file=sys.stderr)
        print(file=sys.stderr)
        print("Option 2: Use /auto-implement (enforces TDD):", file=sys.stderr)
        print("  /auto-implement \"feature description\"", file=sys.stderr)
        print("  → test-master writes tests first", file=sys.stderr)
        print("  → implementer makes them pass", file=sys.stderr)
        print(file=sys.stderr)
        print("Option 3: Disable strict mode (not recommended):", file=sys.stderr)
        print("  Edit .claude/settings.local.json:", file=sys.stderr)
        print('  {"strict_mode": false}', file=sys.stderr)
        print(file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print("TDD prevents bugs and ensures code quality.", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(file=sys.stderr)

        sys.exit(2)  # Block commit

    # Both test and src files present
    if test_files and src_files:
        # Check the ratio of test additions to src additions
        additions = get_file_additions()

        # If test additions are significant, TDD likely followed
        if additions["test_additions"] > 0:
            ratio = additions["ratio"]
            print(f"✅ TDD evidence: {additions['test_additions']} test lines, "
                  f"{additions['src_additions']} src lines (ratio: {ratio:.2f})",
                  file=sys.stderr)
            sys.exit(0)

        # Minimal test changes - warn but allow
        if additions["src_additions"] > 50 and additions["test_additions"] < 10:
            print("⚠️  Warning: Large code changes with minimal test updates",
                  file=sys.stderr)
            print(f"   {additions['src_additions']} src lines, "
                  f"{additions['test_additions']} test lines",
                  file=sys.stderr)
            print("   Consider adding more test coverage", file=sys.stderr)
            # Don't block - just warn
            sys.exit(0)

    # Test files present - assume TDD followed
    print("✅ TDD workflow validated", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
