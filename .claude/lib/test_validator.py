#!/usr/bin/env python3
"""
Test Validator - Execute tests and validate TDD workflow.

Runs pytest, parses results, enforces TDD red phase validation, detects syntax
errors, and validates coverage thresholds. Critical for quality gates before
code review and commit.

Key Features:
1. Execute pytest with minimal verbosity (--tb=line -q, Issue #90)
2. Parse pytest output for pass/fail/error counts
3. Enforce TDD red phase (tests must fail before implementation)
4. Detect syntax errors vs runtime errors
5. Validate coverage thresholds
6. Validation gate for blocking commits

Usage:
    from test_validator import (
        run_tests,
        validate_red_phase,
        run_validation_gate
    )

    # Run tests
    result = run_tests(Path("tests"))

    # TDD red phase validation (before implementation)
    validate_red_phase(result)  # Raises if tests pass prematurely

    # Validation gate (after implementation)
    gate_result = run_validation_gate(Path("tests"))
    if not gate_result["gate_passed"]:
        # Block commit

Date: 2025-12-25
Issue: #161 (Enhanced test-master for 3-tier coverage)
Agent: implementer
Phase: TDD Green (making tests pass)
"""

import re
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Any


def run_tests(
    test_path: Path,
    timeout: int = 300,
    pytest_args: List[str] = None
) -> Dict[str, Any]:
    """Execute pytest and return results.

    Runs pytest with minimal verbosity (--tb=line -q) to prevent subprocess
    pipe deadlock (Issue #90). Reduces output from ~2,300 lines to ~50 lines.

    Args:
        test_path: Path to test directory or file
        timeout: Timeout in seconds (default 5 minutes)
        pytest_args: Optional custom pytest arguments

    Returns:
        Dict with test results:
        {
            "success": bool,
            "passed": int,
            "failed": int,
            "errors": int,
            "skipped": int,
            "total": int,
            "stdout": str,
            "stderr": str,
            "no_tests_collected": bool
        }

    Raises:
        TimeoutError: If tests exceed timeout
        RuntimeError: If pytest not installed

    Example:
        >>> result = run_tests(Path("tests"))
        >>> result["passed"]
        42
    """
    # Default pytest args (minimal verbosity)
    if pytest_args is None:
        pytest_args = ["--tb=line", "-q"]

    # Build command
    cmd = ["pytest", str(test_path)] + pytest_args

    try:
        # Execute pytest
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False  # Handle return codes manually
        )

        # Parse output
        parsed = parse_pytest_output(result.stdout)
        parsed["stdout"] = result.stdout
        parsed["stderr"] = result.stderr

        # Check for no tests collected (pytest returns 5)
        if result.returncode == 5:
            parsed["no_tests_collected"] = True
            parsed["success"] = False
        else:
            parsed["no_tests_collected"] = False
            # Success if returncode is 0
            parsed["success"] = result.returncode == 0

        return parsed

    except FileNotFoundError:
        raise RuntimeError(
            "pytest not installed. Install with: pip install pytest"
        )
    except subprocess.TimeoutExpired:
        raise TimeoutError(
            f"Tests exceeded timeout of {timeout} seconds ({timeout // 60} minutes)"
        )


def parse_pytest_output(output: str) -> Dict[str, int]:
    """Parse pytest output for test counts.

    Extracts counts from pytest summary line:
    "10 passed, 2 failed, 1 error in 1.23s"

    Args:
        output: pytest stdout

    Returns:
        Dict with counts: {passed, failed, errors, skipped, total}

    Example:
        >>> output = "10 passed, 2 failed, 1 error in 1.23s"
        >>> parse_pytest_output(output)
        {"passed": 10, "failed": 2, "errors": 1, "skipped": 0, "total": 13}
    """
    result = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "total": 0
    }

    # Try to find summary line (last line with counts)
    # Pattern: "N passed, M failed, K error in X.XXs"
    summary_pattern = r'(\d+)\s+passed|(\d+)\s+failed|(\d+)\s+error|(\d+)\s+skipped'
    matches = re.findall(summary_pattern, output, re.IGNORECASE)

    for match in matches:
        if match[0]:  # passed
            result["passed"] = int(match[0])
        elif match[1]:  # failed
            result["failed"] = int(match[1])
        elif match[2]:  # error
            result["errors"] = int(match[2])
        elif match[3]:  # skipped
            result["skipped"] = int(match[3])

    # Try to find "collected N items"
    collected_pattern = r'collected\s+(\d+)\s+items?'
    collected_match = re.search(collected_pattern, output, re.IGNORECASE)
    if collected_match:
        result["total"] = int(collected_match.group(1))
    else:
        # Fallback: sum counts
        result["total"] = result["passed"] + result["failed"] + result["errors"]

    return result


def validate_red_phase(test_result: Dict[str, Any]) -> None:
    """Validate TDD red phase - tests should fail before implementation.

    Ensures tests fail initially (no implementation exists yet). Blocks workflow
    if all tests pass prematurely.

    Args:
        test_result: Test result from run_tests()

    Raises:
        ValueError: If tests pass prematurely (TDD red phase violation)
        ValueError: If no tests found

    Example:
        >>> result = {"success": True, "passed": 10, "failed": 0, "errors": 0}
        >>> validate_red_phase(result)
        ValueError: TDD red phase violation: tests should fail before implementation
    """
    # Check for premature pass (all tests pass)
    # Note: Don't check total==0 here because test_result may not have "total" field
    passed = test_result.get("passed", 0)
    failed = test_result.get("failed", 0)
    errors = test_result.get("errors", 0)

    # If all tests pass (no failures or errors), that's a red phase violation
    if test_result.get("success", False) and failed == 0 and errors == 0 and passed > 0:
        raise ValueError(
            "TDD red phase violation: All tests pass, but implementation doesn't exist yet. "
            "Tests should fail initially (import errors, assertion failures) before implementation."
        )

    # Check for no tests (passed + failed + errors == 0)
    if passed == 0 and failed == 0 and errors == 0:
        raise ValueError(
            "No tests found. TDD requires tests to be written first."
        )

    # Valid red phase: Some failures or errors exist
    # (Import errors are expected when modules don't exist yet)


def detect_syntax_errors(pytest_output: str) -> Tuple[bool, List[str]]:
    """Detect syntax errors in test files.

    Distinguishes syntax/import errors from runtime errors (assertions, exceptions).

    Args:
        pytest_output: pytest stdout/stderr

    Returns:
        Tuple of (has_syntax_errors, error_details)

    Example:
        >>> output = "SyntaxError: invalid syntax on line 10"
        >>> has_errors, details = detect_syntax_errors(output)
        >>> has_errors
        True
    """
    errors = []
    has_syntax_errors = False

    # Patterns for syntax errors
    syntax_patterns = [
        r'SyntaxError:',
        r'ImportError:',
        r'ModuleNotFoundError:',
        r'IndentationError:',
        r'TabError:'
    ]

    # Search for syntax errors
    for pattern in syntax_patterns:
        matches = re.findall(f'({pattern}.*)', pytest_output, re.MULTILINE)
        if matches:
            has_syntax_errors = True
            errors.extend(matches)

    return has_syntax_errors, errors


def validate_test_syntax(test_result: Dict[str, Any]) -> None:
    """Validate test files for syntax errors.

    Blocks workflow if syntax errors detected (not runtime errors).

    Args:
        test_result: Test result from run_tests()

    Raises:
        SyntaxError: If test files contain syntax errors

    Example:
        >>> result = {"stderr": "SyntaxError: invalid syntax"}
        >>> validate_test_syntax(result)
        SyntaxError: Test files contain syntax errors
    """
    combined_output = test_result.get("stdout", "") + test_result.get("stderr", "")
    has_errors, details = detect_syntax_errors(combined_output)

    if has_errors:
        error_msg = "Test files contain syntax errors:\n" + "\n".join(details[:5])
        raise SyntaxError(error_msg)


def run_validation_gate(test_path: Path, timeout: int = 300) -> Dict[str, Any]:
    """Run validation gate before code review.

    Executes all tests and determines if commit should proceed. Blocks on:
    - Test failures
    - Syntax errors
    - No tests found

    Args:
        test_path: Path to test directory
        timeout: Test timeout in seconds

    Returns:
        Dict with validation results:
        {
            "gate_passed": bool,
            "all_tests_passed": bool,
            "block_commit": bool,
            "passed": int,
            "failed": int,
            "errors": int,
            "message": str
        }

    Example:
        >>> result = run_validation_gate(Path("tests"))
        >>> if not result["gate_passed"]:
        ...     print("Blocking commit")
    """
    # Run tests
    try:
        test_result = run_tests(test_path, timeout)
    except Exception as e:
        return {
            "gate_passed": False,
            "all_tests_passed": False,
            "block_commit": True,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "message": f"Test execution failed: {e}"
        }

    # Check syntax errors
    try:
        validate_test_syntax(test_result)
    except SyntaxError as e:
        return {
            "gate_passed": False,
            "all_tests_passed": False,
            "block_commit": True,
            "passed": test_result.get("passed", 0),
            "failed": test_result.get("failed", 0),
            "errors": test_result.get("errors", 0),
            "message": str(e)
        }

    # Check if all tests passed
    all_passed = test_result.get("success", False)
    block_commit = not all_passed

    return {
        "gate_passed": all_passed,
        "all_tests_passed": all_passed,
        "block_commit": block_commit,
        "passed": test_result.get("passed", 0),
        "failed": test_result.get("failed", 0),
        "errors": test_result.get("errors", 0),
        "message": "All tests passed" if all_passed else f"{test_result.get('failed', 0)} tests failed"
    }


def validate_coverage(coverage_output: str, threshold: float = 80.0) -> None:
    """Validate test coverage meets threshold.

    Parses pytest-cov output and blocks if coverage below threshold.

    Args:
        coverage_output: pytest --cov output
        threshold: Minimum coverage percentage (default 80%)

    Raises:
        ValueError: If coverage below threshold

    Example:
        >>> output = "TOTAL  100  15  85%"
        >>> validate_coverage(output, threshold=80)
        # Passes (85% >= 80%)
    """
    # Parse coverage from output
    # Format: "TOTAL  100  15  85%"
    pattern = r'TOTAL\s+\d+\s+\d+\s+(\d+)%'
    match = re.search(pattern, coverage_output)

    if not match:
        # Can't determine coverage, skip validation
        return

    coverage = int(match.group(1))

    if coverage < threshold:
        raise ValueError(
            f"Coverage below {threshold}%: {coverage}%. "
            f"Add more tests to reach {threshold}% coverage."
        )
