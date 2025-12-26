#!/usr/bin/env python3
"""
Unified Code Quality Hook - Dispatcher for Quality Checks

Consolidates 5 code quality hooks into one dispatcher:
- auto_format.py (code formatting)
- auto_test.py (test execution)
- security_scan.py (secret/vulnerability scanning)
- enforce_tdd.py (TDD workflow validation)
- auto_enforce_coverage.py (coverage enforcement)

Hook: PreCommit (runs before git commit completes)

Environment Variables (opt-in/opt-out):
    AUTO_FORMAT=true/false (default: true)
    AUTO_TEST=true/false (default: true)
    SECURITY_SCAN=true/false (default: true)
    ENFORCE_TDD=true/false (default: false, requires strict_mode)
    ENFORCE_COVERAGE=true/false (default: false)

Exit codes:
    0: All enabled checks passed
    1: One or more checks failed (non-blocking)
    2: Critical failure (blocks commit)

Usage:
    # As PreCommit hook (automatic)
    python unified_code_quality.py

    # Manual run with specific checks
    AUTO_FORMAT=false python unified_code_quality.py
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Tuple, Optional

# ============================================================================
# Dynamic Library Discovery
# ============================================================================

def find_lib_dir() -> Optional[Path]:
    """
    Find the lib directory dynamically.

    Searches:
    1. Relative to this file: ../lib
    2. In project root: plugins/autonomous-dev/lib
    3. In global install: ~/.autonomous-dev/lib

    Returns:
        Path to lib directory or None if not found
    """
    candidates = [
        Path(__file__).parent.parent / "lib",  # Relative to hooks/
        Path.cwd() / "plugins" / "autonomous-dev" / "lib",  # Project root
        Path.home() / ".autonomous-dev" / "lib",  # Global install
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


# Add lib to path
LIB_DIR = find_lib_dir()
if LIB_DIR:
    sys.path.insert(0, str(LIB_DIR))

# Optional imports with graceful fallback
try:
    from error_messages import formatter_not_found_error, print_warning
    HAS_ERROR_MESSAGES = True
except ImportError:
    HAS_ERROR_MESSAGES = False
    def print_warning(msg: str) -> None:
        print(f"⚠️  {msg}", file=sys.stderr)

# ============================================================================
# Configuration
# ============================================================================

# Check configuration from environment
AUTO_FORMAT = os.environ.get("AUTO_FORMAT", "true").lower() == "true"
AUTO_TEST = os.environ.get("AUTO_TEST", "true").lower() == "true"
SECURITY_SCAN = os.environ.get("SECURITY_SCAN", "true").lower() == "true"
ENFORCE_TDD = os.environ.get("ENFORCE_TDD", "false").lower() == "true"
ENFORCE_COVERAGE = os.environ.get("ENFORCE_COVERAGE", "false").lower() == "true"

# ============================================================================
# Individual Check Functions
# ============================================================================

def check_format() -> Tuple[bool, str]:
    """
    Run code formatting checks.

    Returns:
        (success, message) tuple
    """
    try:
        hook_path = Path(__file__).parent / "auto_format.py"
        if not hook_path.exists():
            return True, "[SKIP] auto_format.py not found"

        result = subprocess.run(
            [sys.executable, str(hook_path)],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            return True, "[PASS] Code formatting"
        else:
            return False, f"[FAIL] Code formatting\n{result.stderr}"

    except subprocess.TimeoutExpired:
        return False, "[FAIL] Code formatting timed out (60s)"
    except Exception as e:
        return True, f"[SKIP] Code formatting error: {e}"


def check_tests() -> Tuple[bool, str]:
    """
    Run test suite.

    Returns:
        (success, message) tuple
    """
    try:
        hook_path = Path(__file__).parent / "auto_test.py"
        if not hook_path.exists():
            return True, "[SKIP] auto_test.py not found"

        result = subprocess.run(
            [sys.executable, str(hook_path)],
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes for tests
        )

        if result.returncode == 0:
            return True, "[PASS] Test suite"
        else:
            return False, f"[FAIL] Test suite\n{result.stderr}"

    except subprocess.TimeoutExpired:
        return False, "[FAIL] Test suite timed out (300s)"
    except Exception as e:
        return True, f"[SKIP] Test suite error: {e}"


def check_security() -> Tuple[bool, str]:
    """
    Run security scanning.

    Returns:
        (success, message) tuple
    """
    try:
        hook_path = Path(__file__).parent / "security_scan.py"
        if not hook_path.exists():
            return True, "[SKIP] security_scan.py not found"

        result = subprocess.run(
            [sys.executable, str(hook_path)],
            capture_output=True,
            text=True,
            timeout=120  # 2 minutes for security scan
        )

        if result.returncode == 0:
            return True, "[PASS] Security scan"
        elif result.returncode == 2:
            # Exit code 2 = critical security issue (blocks commit)
            return False, f"[FAIL] Security scan (CRITICAL)\n{result.stdout}"
        else:
            return False, f"[FAIL] Security scan\n{result.stderr}"

    except subprocess.TimeoutExpired:
        return False, "[FAIL] Security scan timed out (120s)"
    except Exception as e:
        return True, f"[SKIP] Security scan error: {e}"


def check_tdd() -> Tuple[bool, str]:
    """
    Validate TDD workflow.

    Returns:
        (success, message) tuple
    """
    try:
        hook_path = Path(__file__).parent / "enforce_tdd.py"
        if not hook_path.exists():
            return True, "[SKIP] enforce_tdd.py not found"

        result = subprocess.run(
            [sys.executable, str(hook_path)],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            return True, "[PASS] TDD workflow"
        elif result.returncode == 2:
            # Exit code 2 = TDD violation (blocks commit)
            return False, f"[FAIL] TDD workflow (BLOCKS COMMIT)\n{result.stdout}"
        else:
            return False, f"[FAIL] TDD workflow\n{result.stderr}"

    except subprocess.TimeoutExpired:
        return False, "[FAIL] TDD workflow timed out (30s)"
    except Exception as e:
        return True, f"[SKIP] TDD workflow error: {e}"


def check_coverage() -> Tuple[bool, str]:
    """
    Enforce test coverage.

    Returns:
        (success, message) tuple
    """
    try:
        hook_path = Path(__file__).parent / "auto_enforce_coverage.py"
        if not hook_path.exists():
            return True, "[SKIP] auto_enforce_coverage.py not found"

        result = subprocess.run(
            [sys.executable, str(hook_path)],
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes for coverage
        )

        if result.returncode == 0:
            return True, "[PASS] Test coverage"
        elif result.returncode == 2:
            # Exit code 2 = coverage below threshold (blocks commit)
            return False, f"[FAIL] Test coverage (BLOCKS COMMIT)\n{result.stdout}"
        else:
            return False, f"[FAIL] Test coverage\n{result.stderr}"

    except subprocess.TimeoutExpired:
        return False, "[FAIL] Test coverage timed out (300s)"
    except Exception as e:
        return True, f"[SKIP] Test coverage error: {e}"


# ============================================================================
# Dispatcher
# ============================================================================

def run_quality_checks() -> int:
    """
    Run all enabled quality checks.

    Returns:
        Exit code (0=success, 1=failure, 2=critical)
    """
    print("🔍 Running code quality checks...")
    print()

    # Define checks with their configuration
    checks: List[Tuple[bool, str, Callable[[], Tuple[bool, str]]]] = [
        (AUTO_FORMAT, "Code Formatting", check_format),
        (AUTO_TEST, "Test Suite", check_tests),
        (SECURITY_SCAN, "Security Scan", check_security),
        (ENFORCE_TDD, "TDD Workflow", check_tdd),
        (ENFORCE_COVERAGE, "Test Coverage", check_coverage),
    ]

    # Track results
    results: List[Tuple[str, bool, str]] = []
    has_failures = False
    has_critical_failures = False

    # Run enabled checks
    for enabled, name, check_fn in checks:
        if not enabled:
            print(f"[SKIP] {name} (disabled)")
            continue

        print(f"Running {name}...", end=" ", flush=True)
        success, message = check_fn()
        results.append((name, success, message))

        if success:
            print("✓")
        else:
            print("✗")
            has_failures = True

            # Check if this is a critical failure (blocks commit)
            if "BLOCKS COMMIT" in message or "CRITICAL" in message:
                has_critical_failures = True

    # Print summary
    print()
    print("=" * 60)
    print("QUALITY CHECK SUMMARY")
    print("=" * 60)

    for name, success, message in results:
        print()
        print(f"{name}:")
        print(f"  {message}")

    print()

    # Determine exit code
    if has_critical_failures:
        print("❌ Critical failures detected - COMMIT BLOCKED")
        return 2
    elif has_failures:
        print("⚠️  Some checks failed - review above")
        return 1
    else:
        print("✅ All quality checks passed")
        return 0


# ============================================================================
# Main Entry Point
# ============================================================================

def main() -> int:
    """Main entry point."""
    try:
        # Check if any checks are enabled
        if not any([AUTO_FORMAT, AUTO_TEST, SECURITY_SCAN, ENFORCE_TDD, ENFORCE_COVERAGE]):
            print("[SKIP] All quality checks disabled")
            return 0

        return run_quality_checks()

    except KeyboardInterrupt:
        print("\n⚠️  Quality checks interrupted by user")
        return 1
    except Exception as e:
        print(f"⚠️  Unexpected error in quality checks: {e}", file=sys.stderr)
        # Don't block commit on infrastructure errors
        return 0


if __name__ == "__main__":
    sys.exit(main())
