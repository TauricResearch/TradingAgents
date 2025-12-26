#!/usr/bin/env python3
"""
Unified Documentation Auto-Fix Hook - Dispatcher for Documentation Updates

Consolidates 8 documentation auto-fix hooks into one dispatcher:
- auto_fix_docs.py (congruence checks, GenAI smart auto-fixing)
- auto_update_docs.py (API change detection, doc-syncer invocation)
- auto_add_to_regression.py (auto-create regression tests after feature)
- auto_generate_tests.py (auto-generate tests before implementation)
- auto_sync_dev.py (plugin development sync)
- auto_tdd_enforcer.py (enforce TDD workflow)
- auto_track_issues.py (auto-create GitHub issues from test failures)
- detect_doc_changes.py (detect doc changes needed)

Hook: Multiple lifecycles (PreCommit, PostToolUse, PreToolUse)

Environment Variables (opt-in/opt-out):
    AUTO_FIX_DOCS=true/false (default: true) - Congruence checks + GenAI auto-fix
    AUTO_UPDATE_DOCS=true/false (default: true) - API change detection
    AUTO_ADD_REGRESSION=true/false (default: false) - Auto-create regression tests
    AUTO_GENERATE_TESTS=true/false (default: false) - Auto-generate tests before implementation
    AUTO_SYNC_DEV=true/false (default: true) - Plugin development sync
    AUTO_TDD_ENFORCER=true/false (default: false) - Enforce TDD workflow
    AUTO_TRACK_ISSUES=true/false (default: false) - Auto-track GitHub issues
    DETECT_DOC_CHANGES=true/false (default: true) - Detect doc changes needed

Exit codes:
    0: All enabled checks passed
    1: One or more checks failed (non-blocking)
    2: Critical failure (blocks commit)

Usage:
    # As PreCommit hook (automatic)
    python unified_doc_auto_fix.py

    # Manual run with specific checks
    AUTO_FIX_DOCS=false python unified_doc_auto_fix.py
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Tuple, Optional

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
AUTO_FIX_DOCS = os.environ.get("AUTO_FIX_DOCS", "true").lower() == "true"
AUTO_UPDATE_DOCS = os.environ.get("AUTO_UPDATE_DOCS", "true").lower() == "true"
AUTO_ADD_REGRESSION = os.environ.get("AUTO_ADD_REGRESSION", "false").lower() == "true"
AUTO_GENERATE_TESTS = os.environ.get("AUTO_GENERATE_TESTS", "false").lower() == "true"
AUTO_SYNC_DEV = os.environ.get("AUTO_SYNC_DEV", "true").lower() == "true"
AUTO_TDD_ENFORCER = os.environ.get("AUTO_TDD_ENFORCER", "false").lower() == "true"
AUTO_TRACK_ISSUES = os.environ.get("AUTO_TRACK_ISSUES", "false").lower() == "true"
DETECT_DOC_CHANGES = os.environ.get("DETECT_DOC_CHANGES", "true").lower() == "true"

# ============================================================================
# Individual Check Functions
# ============================================================================

def check_fix_docs() -> Tuple[bool, str]:
    """
    Run documentation congruence checks and GenAI auto-fixing.

    Returns:
        (success, message) tuple
    """
    try:
        hook_path = Path(__file__).parent / "auto_fix_docs.py"
        if not hook_path.exists():
            return True, "[SKIP] auto_fix_docs.py not found"

        result = subprocess.run(
            [sys.executable, str(hook_path)],
            capture_output=True,
            text=True,
            timeout=120  # 2 minutes for GenAI analysis
        )

        if result.returncode == 0:
            return True, "[PASS] Documentation congruence checks"
        elif result.returncode == 1:
            return False, f"[FAIL] Documentation needs manual review\n{result.stderr}"
        else:
            return False, f"[FAIL] Documentation auto-fix failed\n{result.stderr}"

    except subprocess.TimeoutExpired:
        return False, "[FAIL] Documentation auto-fix timed out (120s)"
    except Exception as e:
        return True, f"[SKIP] Documentation auto-fix error: {e}"


def check_update_docs() -> Tuple[bool, str]:
    """
    Run API change detection and doc-syncer invocation.

    Returns:
        (success, message) tuple
    """
    try:
        hook_path = Path(__file__).parent / "auto_update_docs.py"
        if not hook_path.exists():
            return True, "[SKIP] auto_update_docs.py not found"

        result = subprocess.run(
            [sys.executable, str(hook_path)],
            capture_output=True,
            text=True,
            timeout=180  # 3 minutes for API analysis
        )

        if result.returncode == 0:
            return True, "[PASS] API documentation sync"
        else:
            return False, f"[FAIL] API documentation sync\n{result.stderr}"

    except subprocess.TimeoutExpired:
        return False, "[FAIL] API documentation sync timed out (180s)"
    except Exception as e:
        return True, f"[SKIP] API documentation sync error: {e}"


def check_add_regression() -> Tuple[bool, str]:
    """
    Auto-create regression tests after successful implementation.

    Returns:
        (success, message) tuple
    """
    try:
        hook_path = Path(__file__).parent / "auto_add_to_regression.py"
        if not hook_path.exists():
            return True, "[SKIP] auto_add_to_regression.py not found"

        result = subprocess.run(
            [sys.executable, str(hook_path)],
            capture_output=True,
            text=True,
            timeout=120  # 2 minutes for test generation
        )

        if result.returncode == 0:
            return True, "[PASS] Regression test creation"
        else:
            return False, f"[FAIL] Regression test creation\n{result.stderr}"

    except subprocess.TimeoutExpired:
        return False, "[FAIL] Regression test creation timed out (120s)"
    except Exception as e:
        return True, f"[SKIP] Regression test creation error: {e}"


def check_generate_tests() -> Tuple[bool, str]:
    """
    Auto-generate tests before implementation starts.

    Returns:
        (success, message) tuple
    """
    try:
        hook_path = Path(__file__).parent / "auto_generate_tests.py"
        if not hook_path.exists():
            return True, "[SKIP] auto_generate_tests.py not found"

        result = subprocess.run(
            [sys.executable, str(hook_path)],
            capture_output=True,
            text=True,
            timeout=180  # 3 minutes for test-master invocation
        )

        if result.returncode == 0:
            return True, "[PASS] Test generation"
        elif result.returncode == 1:
            return False, f"[FAIL] Test generation blocked\n{result.stderr}"
        else:
            return False, f"[FAIL] Test generation failed\n{result.stderr}"

    except subprocess.TimeoutExpired:
        return False, "[FAIL] Test generation timed out (180s)"
    except Exception as e:
        return True, f"[SKIP] Test generation error: {e}"


def check_sync_dev() -> Tuple[bool, str]:
    """
    Sync plugin development changes to installed location.

    Returns:
        (success, message) tuple
    """
    try:
        hook_path = Path(__file__).parent / "auto_sync_dev.py"
        if not hook_path.exists():
            return True, "[SKIP] auto_sync_dev.py not found"

        result = subprocess.run(
            [sys.executable, str(hook_path)],
            capture_output=True,
            text=True,
            timeout=60  # 1 minute for sync
        )

        if result.returncode == 0:
            return True, "[PASS] Plugin development sync"
        elif result.returncode == 1:
            return True, "[WARN] Plugin development sync recommended\n{result.stdout}"
        else:
            return False, f"[FAIL] Plugin development sync blocked\n{result.stderr}"

    except subprocess.TimeoutExpired:
        return False, "[FAIL] Plugin development sync timed out (60s)"
    except Exception as e:
        return True, f"[SKIP] Plugin development sync error: {e}"


def check_tdd_enforcer() -> Tuple[bool, str]:
    """
    Enforce TDD workflow - tests before implementation.

    Returns:
        (success, message) tuple
    """
    try:
        hook_path = Path(__file__).parent / "auto_tdd_enforcer.py"
        if not hook_path.exists():
            return True, "[SKIP] auto_tdd_enforcer.py not found"

        result = subprocess.run(
            [sys.executable, str(hook_path)],
            capture_output=True,
            text=True,
            timeout=60  # 1 minute for TDD check
        )

        if result.returncode == 0:
            return True, "[PASS] TDD enforcement"
        elif result.returncode == 1:
            return False, f"[FAIL] TDD enforcement - tests must be written first\n{result.stderr}"
        else:
            return False, f"[FAIL] TDD enforcement failed\n{result.stderr}"

    except subprocess.TimeoutExpired:
        return False, "[FAIL] TDD enforcement timed out (60s)"
    except Exception as e:
        return True, f"[SKIP] TDD enforcement error: {e}"


def check_track_issues() -> Tuple[bool, str]:
    """
    Auto-track GitHub issues from test failures.

    Returns:
        (success, message) tuple
    """
    try:
        hook_path = Path(__file__).parent / "auto_track_issues.py"
        if not hook_path.exists():
            return True, "[SKIP] auto_track_issues.py not found"

        result = subprocess.run(
            [sys.executable, str(hook_path)],
            capture_output=True,
            text=True,
            timeout=120  # 2 minutes for GitHub API
        )

        if result.returncode == 0:
            return True, "[PASS] GitHub issue tracking"
        else:
            return False, f"[FAIL] GitHub issue tracking\n{result.stderr}"

    except subprocess.TimeoutExpired:
        return False, "[FAIL] GitHub issue tracking timed out (120s)"
    except Exception as e:
        return True, f"[SKIP] GitHub issue tracking error: {e}"


def check_detect_doc_changes() -> Tuple[bool, str]:
    """
    Detect documentation changes needed.

    Returns:
        (success, message) tuple
    """
    try:
        hook_path = Path(__file__).parent / "detect_doc_changes.py"
        if not hook_path.exists():
            return True, "[SKIP] detect_doc_changes.py not found"

        result = subprocess.run(
            [sys.executable, str(hook_path)],
            capture_output=True,
            text=True,
            timeout=60  # 1 minute for detection
        )

        if result.returncode == 0:
            return True, "[PASS] Documentation change detection"
        else:
            return False, f"[FAIL] Documentation changes needed\n{result.stderr}"

    except subprocess.TimeoutExpired:
        return False, "[FAIL] Documentation change detection timed out (60s)"
    except Exception as e:
        return True, f"[SKIP] Documentation change detection error: {e}"


# ============================================================================
# Dispatcher Configuration
# ============================================================================

# Map of check functions and their configuration
CHECKS: Dict[str, Tuple[bool, Callable[[], Tuple[bool, str]]]] = {
    "fix_docs": (AUTO_FIX_DOCS, check_fix_docs),
    "update_docs": (AUTO_UPDATE_DOCS, check_update_docs),
    "add_regression": (AUTO_ADD_REGRESSION, check_add_regression),
    "generate_tests": (AUTO_GENERATE_TESTS, check_generate_tests),
    "sync_dev": (AUTO_SYNC_DEV, check_sync_dev),
    "tdd_enforcer": (AUTO_TDD_ENFORCER, check_tdd_enforcer),
    "track_issues": (AUTO_TRACK_ISSUES, check_track_issues),
    "detect_doc_changes": (DETECT_DOC_CHANGES, check_detect_doc_changes),
}


# ============================================================================
# Main Dispatcher
# ============================================================================

def main() -> int:
    """
    Run all enabled documentation auto-fix checks.

    Returns:
        Exit code: 0 (pass), 1 (non-blocking failure), 2 (critical failure)
    """
    results: List[Tuple[str, bool, str]] = []
    critical_failure = False

    # Run all enabled checks
    for check_name, (enabled, check_func) in CHECKS.items():
        if not enabled:
            results.append((check_name, True, f"[SKIP] {check_name} disabled"))
            continue

        try:
            success, message = check_func()
            results.append((check_name, success, message))

            # Track critical failures (exit code 2)
            if not success and "blocked" in message.lower():
                critical_failure = True

        except Exception as e:
            results.append((check_name, False, f"[ERROR] {check_name}: {e}"))

    # Print summary
    print("\n" + "=" * 80)
    print("Documentation Auto-Fix Summary")
    print("=" * 80)

    all_passed = True
    for check_name, success, message in results:
        if not success:
            all_passed = False
        print(f"\n{check_name}:")
        print(message)

    print("\n" + "=" * 80)

    # Return appropriate exit code
    if critical_failure:
        print("❌ CRITICAL: One or more checks blocked the commit")
        return 2
    elif not all_passed:
        print("⚠️  WARNING: Some checks failed (non-blocking)")
        return 1
    else:
        print("✅ All documentation auto-fix checks passed")
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n❌ Interrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}", file=sys.stderr)
        sys.exit(2)
