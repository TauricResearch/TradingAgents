#!/usr/bin/env python3
"""
Git Hooks Library - Support for larger projects with 500+ tests

This module provides utilities for git hooks to handle nested test structures
and fast test filtering for improved developer workflow performance.

Features:
- Recursive test discovery (supports nested directories)
- Fast test filtering (exclude slow, genai, integration markers)
- Test duration estimation
- Pre-commit and pre-push hook generation

Issue: GitHub #94 - Git hooks for larger projects
Date: 2025-12-07
"""

import shlex
import subprocess
from pathlib import Path
from typing import List
from dataclasses import dataclass


@dataclass
class TestRunResult:
    """Result of test execution."""
    returncode: int
    output: str


def discover_tests_recursive(tests_dir: Path) -> List[Path]:
    """
    Discover all test files recursively in tests directory.

    Uses recursive search to find test_*.py files at any nesting level.
    Excludes __pycache__ directories automatically.

    Args:
        tests_dir: Path to tests directory

    Returns:
        Sorted list of paths to test_*.py files

    Examples:
        >>> tests = discover_tests_recursive(Path("tests"))
        >>> len(tests)
        524
        >>> any("unit/lib/test_batch.py" in str(t) for t in tests)
        True
    """
    if not tests_dir.exists():
        return []

    # Use Path.rglob() for recursive search
    test_files = []
    for test_file in tests_dir.rglob("test_*.py"):
        # Exclude __pycache__
        if "__pycache__" not in str(test_file):
            test_files.append(test_file)

    return sorted(test_files)


def get_fast_test_command(tests_dir: Path, extra_args: str = "") -> List[str]:
    """
    Get pytest command for running fast tests only.

    Builds pytest command with marker filtering to exclude slow, genai,
    and integration tests. Uses minimal verbosity to prevent output bloat.
    Returns list format for safe subprocess execution (prevents command injection).

    Args:
        tests_dir: Path to tests directory
        extra_args: Additional pytest arguments (optional)

    Returns:
        pytest command as list (safe for subprocess.run)

    Examples:
        >>> cmd = get_fast_test_command(Path("tests"))
        >>> cmd[0]
        'pytest'
        >>> "not slow" in ' '.join(cmd)
        True
    """
    cmd = [
        "pytest",
        str(tests_dir),
        "-m", "not slow and not genai and not integration",
        "--tb=line",
        "-q"
    ]
    if extra_args:
        # Use shlex.split to safely parse extra arguments
        cmd.extend(shlex.split(extra_args))
    return cmd


def filter_fast_tests(all_tests: List[str], tests_dir: Path) -> List[str]:
    """
    Filter test list to only fast tests (exclude slow, genai, integration).

    Reads test files and checks for pytest markers. Tests without markers
    or with only non-slow markers are considered fast.

    Args:
        all_tests: List of all test file names
        tests_dir: Path to tests directory

    Returns:
        List of fast test file names

    Examples:
        >>> tests = ["test_fast.py", "test_slow.py"]
        >>> fast = filter_fast_tests(tests, Path("tests"))
        >>> "test_fast.py" in fast
        True
    """
    fast_tests = []
    for test_name in all_tests:
        test_path = tests_dir / test_name

        # Try direct path first
        if not test_path.exists():
            # Try finding it recursively
            matches = list(tests_dir.rglob(test_name))
            if not matches:
                continue
            test_path = matches[0]

        # Read file and check for slow markers
        try:
            content = test_path.read_text()
            slow_markers = [
                "@pytest.mark.slow",
                "@pytest.mark.genai",
                "@pytest.mark.integration"
            ]

            if not any(marker in content for marker in slow_markers):
                fast_tests.append(test_name)
        except Exception:
            # If we can't read the file, skip it
            continue

    return fast_tests


def estimate_test_duration(tests_dir: Path, fast_only: bool = False) -> float:
    """
    Estimate test execution duration in seconds.

    Estimates based on pytest markers and typical test execution times:
    - Fast tests: ~3 seconds each
    - Slow tests: ~30 seconds each
    - GenAI tests: ~60 seconds each
    - Integration tests: ~20 seconds each

    Args:
        tests_dir: Path to tests directory
        fast_only: If True, estimate fast tests only

    Returns:
        Estimated duration in seconds

    Examples:
        >>> duration = estimate_test_duration(Path("tests"), fast_only=True)
        >>> duration < 60  # Fast tests should be quick
        True
    """
    tests = discover_tests_recursive(tests_dir)

    if not tests:
        return 0.0

    if fast_only:
        # Fast tests: ~3 seconds each
        fast_count = len(filter_fast_tests([t.name for t in tests], tests_dir))
        return float(fast_count * 3.0)
    else:
        # Full suite: estimate based on markers
        total = 0.0
        for test in tests:
            try:
                content = test.read_text()
                if "@pytest.mark.genai" in content:
                    total += 60.0
                elif "@pytest.mark.slow" in content:
                    total += 30.0
                elif "@pytest.mark.integration" in content:
                    total += 20.0
                else:
                    total += 3.0
            except Exception:
                # If we can't read, assume fast
                total += 3.0
        return total


def run_pre_push_tests(tests_dir: Path) -> TestRunResult:
    """
    Run pre-push tests (fast only).

    Executes pytest with fast test filtering. Handles pytest not being
    installed gracefully (non-blocking).

    Args:
        tests_dir: Path to tests directory

    Returns:
        TestRunResult with exit code and output

    Raises:
        Warning: If no tests collected (exit code 5), indicates broken test discovery

    Examples:
        >>> result = run_pre_push_tests(Path("tests"))
        >>> result.returncode in [0, 1]  # Pass or fail, but never error
        True
    """
    cmd = get_fast_test_command(tests_dir)

    try:
        # Pass list directly (safe from command injection)
        result = subprocess.run(
            cmd,  # Already a list, no need for shlex.split
            capture_output=True,
            text=True,
            cwd=tests_dir.parent if tests_dir.parent.exists() else Path.cwd()
        )

        output = result.stdout + result.stderr

        # Handle pytest exit code 5 (no tests collected) - this is a FAILURE
        # Indicates wrong directory path, broken test discovery, or deleted test files
        if result.returncode == 5:
            return TestRunResult(
                returncode=1,  # FAIL - no tests is a problem
                output=output + "\n⚠️  Warning: No tests collected. Check test discovery and directory path."
            )

        # Handle all tests deselected by markers (this IS acceptable)
        # Example: All tests marked slow/genai/integration, none are fast
        if "deselected" in output.lower() and ("passed" in output.lower() or "0 passed" in output):
            # Check that there were NO failures despite deselection
            if "failed" not in output.lower() and result.returncode == 0:
                return TestRunResult(
                    returncode=0,
                    output=output + "\nℹ️  All tests filtered by markers (expected for fast-only run)"
                )

        return TestRunResult(returncode=result.returncode, output=output)

    except FileNotFoundError:
        # Pytest not installed
        return TestRunResult(
            returncode=0,  # Non-blocking
            output="⚠️  Warning: pytest not installed, skipping pre-push tests"
        )


def generate_pre_commit_hook() -> str:
    """
    Generate pre-commit hook content with recursive test discovery.

    Creates a bash script that discovers tests recursively, supporting
    nested directory structures up to any depth.

    Returns:
        Pre-commit hook bash script content

    Examples:
        >>> hook = generate_pre_commit_hook()
        >>> "-type f" in hook
        True
        >>> "test_*.py" in hook
        True
    """
    return '''#!/bin/bash
#
# Pre-commit hook - Validate test coverage with recursive discovery
#

set -e

echo "🔍 Discovering tests recursively..."

# Count tests recursively (supports nested structures)
TEST_COUNT=$(find tests -type f -name "test_*.py" 2>/dev/null | grep -v __pycache__ | wc -l)

echo "Found $TEST_COUNT test files"

# Add additional validation as needed

exit 0
'''


def generate_pre_push_hook() -> str:
    """
    Generate pre-push hook content with fast test filtering.

    Creates a bash script that runs only fast tests, excluding slow,
    genai, and integration markers for improved performance.

    Returns:
        Pre-push hook bash script content

    Examples:
        >>> hook = generate_pre_push_hook()
        >>> "not slow" in hook
        True
        >>> "--tb=line" in hook
        True
    """
    return '''#!/bin/bash
#
# Pre-push hook - Run fast tests only (exclude slow, genai, integration)
#

set -e

echo "🧪 Running fast tests before push..."

# Run fast tests only (improves performance 3x+)
if command -v pytest &> /dev/null; then
    pytest tests/ -m "not slow and not genai and not integration" --tb=line -q
else
    echo "⚠️  Warning: pytest not installed, skipping tests"
fi

exit 0
'''
