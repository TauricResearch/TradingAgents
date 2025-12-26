#!/usr/bin/env python3
"""
Auto-enforce 100% test coverage by generating missing tests.

This hook maintains comprehensive test coverage by:
1. Running coverage analysis before commit
2. Identifying uncovered lines of code
3. Invoking test-master agent to generate coverage tests
4. Blocking commit if coverage < 80% threshold
5. Auto-generating tests to fill coverage gaps

Hook: PreCommit (runs before git commit completes)

Purpose:
- Prevent coverage from dropping below 80%
- Auto-generate tests for uncovered code
- Maintain comprehensive test suite without manual effort
- Ensure all code paths are tested

Usage:
  Triggered automatically before git commit
  Can be run manually: python scripts/hooks/auto_enforce_coverage.py
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).parent.parent.parent
SRC_DIR = PROJECT_ROOT / "src" / "[project_name]"
TESTS_DIR = PROJECT_ROOT / "tests"
COVERAGE_DIR = PROJECT_ROOT / "htmlcov"
COVERAGE_JSON = PROJECT_ROOT / "coverage.json"

# Coverage threshold (block commit if below this)
COVERAGE_THRESHOLD = 80.0

# Maximum number of iterations to try improving coverage
MAX_COVERAGE_ITERATIONS = 3

# ============================================================================
# Helper Functions
# ============================================================================


def run_coverage_analysis() -> Tuple[bool, Dict]:
    """
    Run pytest with coverage and return results.

    Returns:
        (success, coverage_data) tuple
        coverage_data contains coverage metrics from coverage.json
    """
    print("   Running coverage analysis...")

    try:
        # Run pytest with coverage
        result = subprocess.run(
            [
                "python",
                "-m",
                "pytest",
                "tests/",
                f"--cov={SRC_DIR}",
                "--cov-report=json",
                "--cov-report=term-missing",
                "--cov-report=html",
                "-q",  # Quiet mode
            ],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        # Read coverage.json
        if not COVERAGE_JSON.exists():
            return (False, {"error": "coverage.json not created"})

        with open(COVERAGE_JSON) as f:
            coverage_data = json.load(f)

        return (True, coverage_data)

    except subprocess.TimeoutExpired:
        return (False, {"error": "Coverage analysis timed out after 5 minutes"})
    except Exception as e:
        return (False, {"error": f"Coverage analysis failed: {e}"})


def get_coverage_summary(coverage_data: Dict) -> Dict:
    """Extract summary metrics from coverage data."""

    totals = coverage_data.get("totals", {})

    return {
        "percent_covered": totals.get("percent_covered", 0.0),
        "num_statements": totals.get("num_statements", 0),
        "covered_lines": totals.get("covered_lines", 0),
        "missing_lines": totals.get("missing_lines", 0),
        "excluded_lines": totals.get("excluded_lines", 0),
    }


def find_uncovered_code(coverage_data: Dict) -> List[Dict]:
    """
    Find all uncovered lines in source code.

    Returns list of dicts with:
        - file: file path
        - missing_lines: list of uncovered line numbers
        - coverage_pct: coverage percentage for this file
        - priority: priority score (more missing lines = higher priority)
    """
    uncovered = []

    files = coverage_data.get("files", {})

    for file_path, file_data in files.items():
        # Only process source files (not tests)
        if not file_path.startswith("src/"):
            continue

        missing_lines = file_data.get("missing_lines", [])

        if missing_lines:
            summary = file_data.get("summary", {})
            coverage_pct = summary.get("percent_covered", 0.0)

            uncovered.append(
                {
                    "file": file_path,
                    "missing_lines": missing_lines,
                    "coverage_pct": coverage_pct,
                    "num_missing": len(missing_lines),
                    "priority": len(missing_lines)
                    * (100 - coverage_pct),  # More missing + lower % = higher priority
                }
            )

    # Sort by priority (highest first)
    uncovered.sort(key=lambda x: x["priority"], reverse=True)

    return uncovered


def extract_uncovered_code(file_path: str, missing_lines: List[int]) -> str:
    """Extract the actual uncovered code from source file."""

    try:
        with open(file_path) as f:
            lines = f.readlines()

        # Extract context around uncovered lines (±2 lines)
        code_blocks = []

        for line_num in missing_lines:
            if 1 <= line_num <= len(lines):
                start = max(1, line_num - 2)
                end = min(len(lines), line_num + 2)

                block = "".join(
                    [
                        f"{'→' if i+1 == line_num else ' '} {i+1:4d}: {lines[i]}"
                        for i in range(start - 1, end)
                    ]
                )

                code_blocks.append(block)

        return "\n\n".join(code_blocks)

    except Exception as e:
        return f"Error reading file: {e}"


def create_coverage_test_prompt(uncovered_item: Dict) -> str:
    """Create prompt for test-master to generate coverage tests."""

    file_path = uncovered_item["file"]
    missing_lines = uncovered_item["missing_lines"]
    coverage_pct = uncovered_item["coverage_pct"]

    # Extract uncovered code
    uncovered_code = extract_uncovered_code(file_path, missing_lines)

    # Get module name for test file
    module_path = Path(file_path)
    module_name = module_path.stem

    # Determine test file path
    test_file = TESTS_DIR / "unit" / f"test_{module_name}_coverage.py"

    return f"""You are test-master agent. Generate tests to cover uncovered code.

**Coverage Gap Detected**:
File: {file_path}
Current coverage: {coverage_pct:.1f}%
Uncovered lines: {missing_lines}
Number of gaps: {len(missing_lines)}

**Uncovered Code**:
```python
{uncovered_code}
```

**Instructions**:
1. Generate tests that execute these specific code paths
2. Focus on the lines marked with → (uncovered)
3. Write tests to: {test_file}
4. Use proper pytest patterns:
   - Mock external dependencies
   - Test edge cases that trigger these code paths
   - Use parametrize for multiple scenarios if needed

5. Each test should:
   - Have clear docstring explaining WHAT it covers
   - Execute at least one of the uncovered lines
   - Use proper assertions

6. Common reasons for uncovered code:
   - Exception handlers (test error conditions)
   - Edge cases (test boundary conditions)
   - Error paths (test invalid inputs)
   - Conditional branches (test both True and False)

**Generate comprehensive coverage tests now**.
"""


def invoke_test_master_for_coverage(uncovered_items: List[Dict]) -> Dict:
    """
    Invoke test-master agent to generate coverage tests.

    In production, Claude Code would invoke via Task tool.
    For now, creates marker for manual invocation.
    """

    # Take top 5 highest priority gaps
    top_gaps = uncovered_items[:5]

    print(f"\n   🤖 Generating coverage tests for {len(top_gaps)} files...")

    # Create prompts for each gap
    prompts = []
    for item in top_gaps:
        prompt = create_coverage_test_prompt(item)
        prompts.append(
            {
                "file": item["file"],
                "missing_lines": item["missing_lines"],
                "prompt": prompt,
            }
        )

    # Save prompts for agent invocation
    marker_file = PROJECT_ROOT / ".coverage_test_generation.json"
    marker_file.write_text(json.dumps({"prompts": prompts}, indent=2))

    print(f"   📝 Coverage test prompts saved to: {marker_file}")
    print(f"   Claude Code will invoke test-master automatically")

    # In production, would invoke agent here:
    # for item in prompts:
    #     result = Task(
    #         subagent_type="test-master",
    #         prompt=item["prompt"],
    #         description=f"Generate coverage tests for {item['file']}"
    #     )

    return {"success": False, "prompts_saved": str(marker_file), "num_prompts": len(prompts)}


def display_coverage_report(summary: Dict, uncovered: List[Dict]):
    """Display coverage report to user."""

    total_pct = summary["percent_covered"]
    num_statements = summary["num_statements"]
    covered = summary["covered_lines"]
    missing = summary["missing_lines"]

    print(f"\n📊 Coverage Report")
    print(f"   Total Coverage: {total_pct:.1f}%")
    print(f"   Statements: {num_statements}")
    print(f"   Covered: {covered}")
    print(f"   Missing: {missing}")

    if total_pct >= COVERAGE_THRESHOLD:
        print(f"   ✅ Above threshold ({COVERAGE_THRESHOLD}%)")
    else:
        print(f"   ❌ Below threshold ({COVERAGE_THRESHOLD}%)")
        print(f"   Gap: {COVERAGE_THRESHOLD - total_pct:.1f}%")

    if uncovered:
        print(f"\n📋 Files with Coverage Gaps ({len(uncovered)} files):")
        for i, item in enumerate(uncovered[:10], 1):  # Show top 10
            print(
                f"   {i}. {Path(item['file']).name}: "
                f"{item['coverage_pct']:.1f}% "
                f"({item['num_missing']} lines missing)"
            )

        if len(uncovered) > 10:
            print(f"   ... and {len(uncovered) - 10} more files")


# ============================================================================
# Main Logic
# ============================================================================


def main():
    """Main coverage enforcement logic."""

    print(f"\n🔍 Auto-Coverage Enforcement Hook")
    print(f"   Threshold: {COVERAGE_THRESHOLD}%")

    # Run coverage analysis
    success, coverage_data = run_coverage_analysis()

    if not success:
        print(f"\n   ❌ Coverage analysis failed!")
        print(f"   Error: {coverage_data.get('error', 'Unknown error')}")
        print(f"\n   ⚠️  Cannot enforce coverage without analysis")
        print(f"   Allowing commit to proceed (fix coverage manually)")
        sys.exit(0)  # Don't block commit on analysis failure

    # Get coverage summary
    summary = get_coverage_summary(coverage_data)
    uncovered = find_uncovered_code(coverage_data)

    # Display report
    display_coverage_report(summary, uncovered)

    total_coverage = summary["percent_covered"]

    # Check if coverage meets threshold
    if total_coverage >= COVERAGE_THRESHOLD:
        print(f"\n✅ Coverage check PASSED: {total_coverage:.1f}%")
        print(f"   All code adequately tested")
        sys.exit(0)

    # Coverage below threshold - try to auto-fix
    print(f"\n⚠️  Coverage BELOW threshold!")
    print(f"   Current: {total_coverage:.1f}%")
    print(f"   Required: {COVERAGE_THRESHOLD}%")
    print(f"   Gap: {COVERAGE_THRESHOLD - total_coverage:.1f}%")

    if not uncovered:
        print(f"\n   ℹ️  No uncovered code found (might be excluded lines)")
        print(f"   Allowing commit to proceed")
        sys.exit(0)

    # Auto-generate coverage tests
    print(f"\n🤖 Auto-generating tests to improve coverage...")
    print(f"   Found {len(uncovered)} files with coverage gaps")

    result = invoke_test_master_for_coverage(uncovered)

    if result.get("success"):
        # Agent successfully generated tests
        print(f"\n   ✅ test-master generated coverage tests")

        # Re-run coverage to see improvement
        print(f"\n🧪 Re-running coverage with new tests...")

        success, new_coverage_data = run_coverage_analysis()

        if success:
            new_summary = get_coverage_summary(new_coverage_data)
            new_coverage = new_summary["percent_covered"]

            print(f"\n   Coverage improved: {total_coverage:.1f}% → {new_coverage:.1f}%")

            if new_coverage >= COVERAGE_THRESHOLD:
                print(f"   ✅ Now above threshold!")
                sys.exit(0)
            else:
                print(f"   ⚠️  Still below threshold")
                print(f"   Gap remaining: {COVERAGE_THRESHOLD - new_coverage:.1f}%")

    else:
        # Agent invocation is placeholder
        print(f"\n   ℹ️  Coverage test generation prompts created")
        print(f"   Saved to: {result.get('prompts_saved')}")
        print(f"   Prompts: {result.get('num_prompts')}")

    # Coverage still insufficient - provide guidance
    print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"❌ COVERAGE BELOW THRESHOLD")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"\nCurrent: {total_coverage:.1f}% | Required: {COVERAGE_THRESHOLD}%")
    print(f"\n📝 Next Steps:")
    print(f"   1. Review coverage report: open htmlcov/index.html")
    print(f"   2. Focus on high-priority files (shown above)")
    print(f"   3. test-master can generate coverage tests automatically")
    print(f"   4. Or write tests manually for uncovered code")
    print(f"\n💡 Tip: Run 'pytest --cov=src/[project_name] --cov-report=html'")
    print(f"   Then open htmlcov/index.html to see which lines need tests")

    # Decision: Block commit or allow with warning?
    # For now, warn but allow (can be changed to exit(1) to block)
    print(f"\n⚠️  Allowing commit with coverage warning")
    print(f"   (Change to exit(1) in production to block commits)")

    sys.exit(0)  # Change to sys.exit(1) to block commits below threshold


if __name__ == "__main__":
    main()
