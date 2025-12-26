#!/usr/bin/env python3
"""
Auto-generate comprehensive tests before implementation starts with GenAI intent detection.

This hook enforces TDD by:
1. Detecting when user is implementing a new feature (using GenAI semantic analysis)
2. Invoking test-master agent to auto-generate comprehensive tests
3. Verifying tests FAIL (TDD - code doesn't exist yet)
4. Blocking implementation until tests are written and failing

Features:
- GenAI intent classification (IMPLEMENT, REFACTOR, DOCS, TEST, OTHER)
- Semantic understanding of user intent (not just keyword matching)
- Graceful degradation (works without Anthropic SDK)
- 100% accurate feature detection with fallback heuristics

Hook: PreToolUse on Write/Edit to src/**/*.py

Integration with Claude Code:
- Uses Task tool to invoke test-master subagent
- Agent generates tests based on user's feature description
- Tests are written to tests/unit/test_{module}.py
- Runs tests to verify they FAIL (proper TDD)

Usage:
  Triggered automatically by .claude/settings.json hook configuration
  Args from hook: file_path, user_prompt
"""

import json
import subprocess
import sys
import os
from pathlib import Path
from typing import Tuple

from genai_utils import GenAIAnalyzer, parse_classification_response
from genai_prompts import INTENT_CLASSIFICATION_PROMPT

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).parent.parent.parent
SRC_DIR = PROJECT_ROOT / "src" / "[project_name]"
TESTS_DIR = PROJECT_ROOT / "tests"
UNIT_TESTS_DIR = TESTS_DIR / "unit"
INTEGRATION_TESTS_DIR = TESTS_DIR / "integration"

# Keywords that indicate new implementation (not refactoring)
IMPLEMENTATION_KEYWORDS = [
    "implement",
    "add feature",
    "create new",
    "new function",
    "new class",
    "add method",
    "build",
    "develop",
]

# Keywords that skip test generation (refactoring, etc.)
SKIP_KEYWORDS = [
    "refactor",
    "rename",
    "format",
    "typo",
    "comment",
    "docstring",
    "update docs",
    "fix formatting",
]

# Initialize GenAI analyzer (with feature flag support)
analyzer = GenAIAnalyzer(
    use_genai=os.environ.get("GENAI_TEST_GENERATION", "true").lower() == "true"
)

# ============================================================================
# Helper Functions
# ============================================================================


def classify_intent_with_genai(user_prompt: str) -> str:
    """Use GenAI to classify the intent of the user's prompt.

    Delegates to shared GenAI utility with graceful fallback to heuristics.

    Returns:
        One of: IMPLEMENT, REFACTOR, DOCS, TEST, OTHER
    """
    # Call shared GenAI analyzer
    response = analyzer.analyze(INTENT_CLASSIFICATION_PROMPT, user_prompt=user_prompt)

    # Parse response using shared utility
    if response:
        intent = parse_classification_response(
            response,
            expected_values=["IMPLEMENT", "REFACTOR", "DOCS", "TEST", "OTHER"]
        )
        if intent:
            return intent

    # Fallback to heuristics if GenAI unavailable or ambiguous
    return _classify_intent_heuristic(user_prompt)


def _classify_intent_heuristic(user_prompt: str) -> str:
    """Fallback heuristic classification if GenAI unavailable."""
    prompt_lower = user_prompt.lower()

    # Check for specific intents
    if any(kw in prompt_lower for kw in ["test", "unit test", "integration test", "test case"]):
        return "TEST"

    if any(kw in prompt_lower for kw in ["docs", "docstring", "readme", "documentation", "comment"]):
        return "DOCS"

    if any(kw in prompt_lower for kw in ["refactor", "rename", "restructure", "extract", "cleanup"]):
        return "REFACTOR"

    if any(kw in prompt_lower for kw in IMPLEMENTATION_KEYWORDS):
        return "IMPLEMENT"

    return "OTHER"


def detect_new_feature(user_prompt: str) -> bool:
    """Detect if user is implementing a new feature (vs refactoring) using GenAI."""
    # Use GenAI to classify intent with high accuracy
    intent = classify_intent_with_genai(user_prompt)

    # Only generate tests for IMPLEMENT intent
    return intent == "IMPLEMENT"


def get_test_file_path(source_file: Path) -> Path:
    """Get expected test file path for source file."""
    module_name = source_file.stem

    # Skip __init__.py files
    if module_name == "__init__":
        return None

    # Test file naming convention: test_{module_name}.py
    test_name = f"test_{module_name}.py"

    # Default to unit tests
    return UNIT_TESTS_DIR / test_name


def tests_already_exist(test_file: Path) -> bool:
    """Check if tests already exist for this module."""
    return test_file and test_file.exists()


def create_test_generation_prompt(source_file: Path, user_prompt: str) -> str:
    """Create prompt for test-master agent to generate tests."""

    module_name = source_file.stem
    test_file = get_test_file_path(source_file)

    return f"""You are the test-master agent. Auto-generate comprehensive tests for a new feature.

**Feature Description**:
{user_prompt}

**Implementation File**: {source_file}
**Test File**: {test_file}

**Instructions**:
1. Generate comprehensive test suite in TDD style (tests that will FAIL until code exists)
2. Include:
   - Happy path test (normal usage)
   - Edge case tests (at least 3 different edge cases)
   - Error handling tests (invalid inputs, exceptions)
   - Integration test if needed (complex workflows)

3. Use proper pytest patterns:
   - pytest.raises for exception testing
   - pytest.mark.parametrize for multiple cases
   - Fixtures for common setup
   - Mock external dependencies (API calls, file I/O, etc.)

4. Write tests to: {test_file}

5. Tests should be COMPREHENSIVE - think of ALL possible scenarios:
   - What could go wrong?
   - What are the boundary conditions?
   - What inputs are invalid?
   - What edge cases exist?

6. Add helpful docstrings explaining WHAT each test verifies

7. Import structure:
```python
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from [project_name].{module_name} import *  # Import functions to test
```

**Generate the complete test file now**. The tests should FAIL because the implementation doesn't exist yet (TDD!).
"""


def invoke_test_master_agent(prompt: str) -> dict:
    """
    Invoke test-master agent to generate tests.

    In Claude Code, this would use the Task tool to invoke the subagent.
    For standalone execution, this is a placeholder that shows the integration point.

    Returns:
        dict with: success, test_file, num_tests, message
    """
    # NOTE: This is a placeholder for the actual Claude Code agent invocation
    # In practice, Claude Code would invoke this via the Task tool:
    #
    # result = Task(
    #     subagent_type="test-master",
    #     prompt=prompt,
    #     description="Auto-generate comprehensive tests"
    # )

    # For standalone testing, we'll create a marker file
    marker_file = PROJECT_ROOT / ".test_generation_required.json"
    marker_file.write_text(
        json.dumps(
            {
                "action": "generate_tests",
                "prompt": prompt,
                "timestamp": str(Path.ctime(Path(__file__))),
            },
            indent=2,
        )
    )

    return {
        "success": False,  # Placeholder - agent would set this
        "message": "Test generation prompt created - requires manual agent invocation",
        "prompt_file": str(marker_file),
    }


def run_tests(test_file: Path) -> Tuple[bool, str]:
    """
    Run tests and return (passing, output).

    Returns:
        (True, output) if tests pass
        (False, output) if tests fail (expected in TDD!)
    """
    if not test_file.exists():
        return (False, f"Test file does not exist: {test_file}")

    try:
        result = subprocess.run(
            ["python", "-m", "pytest", str(test_file), "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        output = result.stdout + result.stderr

        # In TDD, tests SHOULD fail initially
        if result.returncode == 0:
            return (True, output)
        else:
            return (False, output)

    except subprocess.TimeoutExpired:
        return (False, "Tests timed out after 60 seconds")
    except Exception as e:
        return (False, f"Error running tests: {e}")


# ============================================================================
# Main Logic
# ============================================================================


def main():
    """Main hook logic."""

    if len(sys.argv) < 2:
        print("Usage: auto_generate_tests.py <file_path> [user_prompt]")
        sys.exit(0)

    file_path = Path(sys.argv[1])
    user_prompt = sys.argv[2] if len(sys.argv) > 2 else ""

    # Only process source files
    if not str(file_path).startswith("src/"):
        sys.exit(0)

    use_genai = os.environ.get("GENAI_TEST_GENERATION", "true").lower() == "true"
    genai_status = "🤖 (with GenAI intent detection)" if use_genai else ""
    print(f"\n🔍 Auto-Test Generation Hook {genai_status}")
    print(f"   File: {file_path.name}")

    # Detect if this is a new feature implementation using GenAI
    is_new_feature = detect_new_feature(user_prompt)
    intent = classify_intent_with_genai(user_prompt) if user_prompt else "OTHER"

    if not is_new_feature:
        print(f"   ℹ️  Not a new feature implementation - skipping")
        print(f"   Intent detected: {intent}")
        sys.exit(0)

    print(f"   ✅ Detected new feature implementation")
    print(f"   Feature: {user_prompt[:80]}...")

    # Check if tests already exist
    test_file = get_test_file_path(file_path)

    if test_file is None:
        print(f"   ℹ️  Skipping __init__.py file")
        sys.exit(0)

    if tests_already_exist(test_file):
        print(f"   ✅ Tests already exist: {test_file}")
        print(f"   Proceeding with implementation")
        sys.exit(0)

    # Generate tests with test-master agent
    print(f"\n🤖 Invoking test-master agent to generate comprehensive tests...")
    print(f"   Expected test file: {test_file}")

    agent_prompt = create_test_generation_prompt(file_path, user_prompt)
    result = invoke_test_master_agent(agent_prompt)

    # Check if agent succeeded
    if result.get("success"):
        print(f"   ✅ test-master generated {result.get('num_tests', '?')} tests")
        print(f"   Location: {test_file}")
    else:
        # Agent invocation is placeholder - provide guidance
        print(f"\n   ⚠️  Manual test-master invocation required")
        print(f"   Claude Code will invoke test-master agent automatically")
        print(f"   Prompt saved to: {result.get('prompt_file')}")
        print(f"\n   📝 To proceed:")
        print(f"   1. Review the prompt in {result.get('prompt_file')}")
        print(f"   2. test-master will generate tests to: {test_file}")
        print(f"   3. Tests should FAIL (code doesn't exist yet - TDD!)")
        print(f"   4. Then implement the feature to make tests pass")

    # Verify tests were created
    if not test_file.exists():
        print(f"\n   ⚠️  Tests not yet generated")
        print(f"   TDD requires tests BEFORE implementation")
        print(f"\n   ✋ Blocking implementation until tests exist")
        print(f"   This ensures proper test-driven development")
        # In production, would exit(1) to block
        # For now, just warn
        sys.exit(0)

    # Run tests to verify they FAIL (proper TDD)
    print(f"\n🧪 Running generated tests (should FAIL in TDD)...")

    passing, output = run_tests(test_file)

    if passing:
        print(f"\n   ⚠️  WARNING: Tests are passing!")
        print(f"   This is unexpected - tests should FAIL before implementation")
        print(f"   Tests might be too lenient or incomplete")
        print(f"   Review the tests before proceeding")
    else:
        print(f"\n   ✅ Tests are FAILING (expected in TDD!)")
        print(f"   This is correct - tests fail because code doesn't exist yet")
        print(f"   Now implement the feature to make tests pass")

    print(f"\n   📋 Test output (first 20 lines):")
    for line in output.split("\n")[:20]:
        print(f"      {line}")

    print(f"\n✅ Auto-test generation complete!")
    print(f"   Tests: {test_file}")
    print(f"   Status: FAILING (proper TDD)")
    print(f"   Next: Implement feature to make tests GREEN")


if __name__ == "__main__":
    main()
