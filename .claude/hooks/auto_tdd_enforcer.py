#!/usr/bin/env python3
"""
TDD Enforcer - Ensures tests are written BEFORE implementation.

Blocks implementation if:
1. No test file exists for the feature
2. Test file exists but all tests passing (tests should fail first in TDD!)

Allows implementation if:
1. Tests exist and are failing (proper TDD workflow)
2. User explicitly requests to skip TDD

Auto-invokes tester subagent to write failing tests first.

Hook Integration:
- Event: PreToolUse (before Write/Edit on src/ files)
- Trigger: Writing to src/**/*.py
- Action: Check if tests exist and are failing
"""

import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).parent.parent.parent
SRC_DIR = PROJECT_ROOT / "src" / "[project_name]"
TESTS_DIR = PROJECT_ROOT / "tests"
UNIT_TESTS_DIR = TESTS_DIR / "unit"
INTEGRATION_TESTS_DIR = TESTS_DIR / "integration"

# Patterns that indicate implementation (not just refactoring)
IMPLEMENTATION_KEYWORDS = [
    "implement",
    "add feature",
    "create new",
    "new function",
    "new class",
    "add method",
]

# Patterns that DON'T require TDD (refactoring, docs, etc.)
SKIP_TDD_KEYWORDS = [
    "refactor",
    "rename",
    "format",
    "typo",
    "comment",
    "docstring",
    "fix bug",  # Bug fixes can have tests after
    "update docs",
]

# ============================================================================
# Helper Functions
# ============================================================================


def get_test_file_for_module(module_path: Path) -> Path:
    """Get corresponding test file for source module.

    Example:
        src/[project_name]/trainer.py → tests/unit/test_trainer.py
        src/[project_name]/core/adapter.py → tests/unit/test_adapter.py
    """
    # Get the module name (last part of path before .py)
    module_name = module_path.stem

    # Test file naming convention: test_{module_name}.py
    test_name = f"test_{module_name}.py"

    # Try unit tests first, then integration tests
    unit_test_path = UNIT_TESTS_DIR / test_name
    integration_test_path = INTEGRATION_TESTS_DIR / test_name

    # Return unit test path (even if doesn't exist - it's the expected location)
    return unit_test_path


def tests_exist(test_file: Path) -> bool:
    """Check if test file exists."""
    return test_file.exists()


def run_tests(test_file: Path) -> Tuple[bool, str]:
    """Run tests and return (passing, output).

    Returns:
        (True, output) if tests pass
        (False, output) if tests fail
    """
    if not test_file.exists():
        return (False, "Test file does not exist")

    try:
        result = subprocess.run(
            ["python", "-m", "pytest", str(test_file), "-v", "--tb=short"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30,  # 30 second timeout
        )

        output = result.stdout + result.stderr

        # Tests PASSING = returncode 0
        # Tests FAILING = returncode != 0
        passing = (result.returncode == 0)

        return (passing, output)

    except subprocess.TimeoutExpired:
        return (False, "Tests timed out (>30 seconds)")
    except Exception as e:
        return (False, f"Error running tests: {e}")


def should_skip_tdd(user_prompt: str) -> bool:
    """Check if user request suggests we should skip TDD enforcement.

    Skip TDD for:
    - Refactoring
    - Renaming
    - Formatting
    - Documentation
    - Bug fixes (tests can come after for bugs)
    """
    prompt_lower = user_prompt.lower()

    for keyword in SKIP_TDD_KEYWORDS:
        if keyword in prompt_lower:
            return True

    return False


def is_implementation(user_prompt: str) -> bool:
    """Check if user request is implementing new functionality.

    Returns True for:
    - "implement X"
    - "add feature Y"
    - "create new Z"
    """
    prompt_lower = user_prompt.lower()

    for keyword in IMPLEMENTATION_KEYWORDS:
        if keyword in prompt_lower:
            return True

    return False


def detect_target_module(file_path: str) -> Optional[Path]:
    """Detect which module is being modified from file path.

    Args:
        file_path: Path to file being written (from $CLAUDE_FILE_PATHS)

    Returns:
        Path object if it's a source file, None otherwise
    """
    path = Path(file_path)

    # Only enforce TDD for source files in src/[project_name]/
    if "src/[project_name]" not in str(path):
        return None

    # Ignore test files
    if "test_" in path.name:
        return None

    # Ignore __init__.py (usually just imports)
    if path.name == "__init__.py":
        return None

    return path


def suggest_tester_invocation(feature_request: str, target_module: Path) -> str:
    """Generate suggestion for invoking tester subagent.

    Returns:
        Formatted message suggesting how to invoke tester
    """
    test_file = get_test_file_for_module(target_module)

    return f"""
╭─────────────────────────────────────────────────────────╮
│ 🧪 TDD ENFORCEMENT: Tests Required Before Implementation │
╰─────────────────────────────────────────────────────────╯

❌ No tests found for: {target_module.name}

Expected test file: {test_file.relative_to(PROJECT_ROOT)}

┌─────────────────────────────────────────────────────────┐
│ 📋 TDD Workflow (Required):                              │
│                                                           │
│ 1. Write FAILING tests first (tester subagent)          │
│ 2. Run tests (should FAIL - not implemented yet)        │
│ 3. Implement feature (make tests PASS)                  │
│ 4. Refactor if needed                                   │
└─────────────────────────────────────────────────────────┘

🤖 AUTO-INVOKE TESTER SUBAGENT:

The tester subagent can automatically:
✓ Write failing tests for: {feature_request}
✓ Create test file: {test_file.name}
✓ Run tests (will fail - not implemented)
✓ Commit tests
✓ Allow implementation to proceed

To invoke tester subagent, tell Claude:
"Invoke tester subagent to write tests for {feature_request}"

Or manually create tests first:
→ Create {test_file.relative_to(PROJECT_ROOT)}
→ Write tests that will fail (feature not implemented)
→ Run: pytest {test_file.relative_to(PROJECT_ROOT)} -v
→ Verify tests FAIL
→ Then proceed with implementation

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TDD = Test-Driven Development (Tests First, Then Code)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


# ============================================================================
# Main TDD Enforcement Logic
# ============================================================================


def enforce_tdd(user_prompt: str, file_path: str) -> int:
    """Enforce TDD workflow.

    Args:
        user_prompt: User's request
        file_path: File being written to

    Returns:
        0 = Allow implementation (tests exist and failing)
        1 = Block implementation (no tests or tests passing)
        2 = Suggest tester subagent (no tests, can auto-create)
    """

    # Detect target module
    target_module = detect_target_module(file_path)
    if target_module is None:
        # Not a source file, allow
        return 0

    # Check if we should skip TDD enforcement
    if should_skip_tdd(user_prompt):
        print(f"⏭️  Skipping TDD enforcement (refactoring/docs/bug fix)")
        return 0

    # Check if this is new implementation
    if not is_implementation(user_prompt):
        # Not implementing new features, allow
        return 0

    # Get corresponding test file
    test_file = get_test_file_for_module(target_module)

    # Check if tests exist
    if not tests_exist(test_file):
        # No tests - suggest tester subagent
        print(suggest_tester_invocation(user_prompt, target_module))
        return 2

    # Tests exist - check if they're failing (proper TDD)
    passing, output = run_tests(test_file)

    if not passing:
        # Tests failing = proper TDD workflow ✅
        print(f"✅ TDD Compliant: Tests exist and failing")
        print(f"   Test file: {test_file.relative_to(PROJECT_ROOT)}")
        print(f"   → Proceed with implementation to make tests pass")
        return 0

    # Tests passing = NOT proper TDD ❌
    print(f"⚠️  TDD Violation: Tests exist but all passing")
    print(f"   Test file: {test_file.relative_to(PROJECT_ROOT)}")
    print()
    print("In TDD, tests should FAIL before implementation:")
    print("1. Write tests that will fail (feature not implemented)")
    print("2. Run tests (verify they FAIL)")
    print("3. Implement feature (make tests PASS)")
    print()
    print("Your tests are passing, which means either:")
    print("a) Feature is already implemented (refactoring, not new feature)")
    print("b) Tests are not comprehensive enough")
    print()
    print("If this is refactoring, ignore this warning.")
    print("If this is NEW functionality, add FAILING tests first.")

    return 1


def main():
    """Main entry point."""

    # Parse arguments
    if len(sys.argv) < 3:
        # Not enough arguments - allow (might be manual invocation)
        return 0

    user_prompt = sys.argv[1]
    file_path = sys.argv[2]

    # Enforce TDD
    exit_code = enforce_tdd(user_prompt, file_path)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
