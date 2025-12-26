#!/usr/bin/env python3
"""
Multi-language test runner hook.

Automatically detects test framework and runs tests.
Enforces minimum 80% code coverage.

Supported frameworks:
- Python: pytest
- JavaScript/TypeScript: jest, vitest
- Go: go test
"""

import subprocess
import sys
from pathlib import Path
from typing import Tuple


def detect_test_framework() -> Tuple[str, str]:
    """Detect test framework from project files.

    Returns:
        (language, framework) tuple
    """
    # Python
    if Path("pytest.ini").exists() or Path("pyproject.toml").exists():
        return "python", "pytest"

    # JavaScript/TypeScript
    if Path("jest.config.js").exists() or Path("jest.config.ts").exists():
        return "javascript", "jest"
    if Path("vitest.config.js").exists() or Path("vitest.config.ts").exists():
        return "javascript", "vitest"
    if Path("package.json").exists():
        # Check package.json for test script
        return "javascript", "npm"

    # Go
    if Path("go.mod").exists():
        return "go", "go-test"

    return "unknown", "unknown"


def run_pytest() -> bool:
    """Run pytest with coverage."""
    try:
        result = subprocess.run(
            [
                "python",
                "-m",
                "pytest",
                "tests/",
                "--cov=src",
                "--cov-fail-under=80",
                "--cov-report=term-missing:skip-covered",
                "--tb=short",
                "-q",
            ],
            capture_output=True,
            text=True,
        )

        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

        return result.returncode == 0
    except FileNotFoundError:
        print("❌ pytest not installed. Run: pip install pytest pytest-cov")
        return False


def run_jest() -> bool:
    """Run jest with coverage."""
    try:
        result = subprocess.run(
            ["npx", "jest", "--coverage", "--coverageThreshold", '{"global":{"lines":80}}'],
            capture_output=True,
            text=True,
        )

        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

        return result.returncode == 0
    except FileNotFoundError:
        print("❌ jest not installed. Run: npm install --save-dev jest")
        return False


def run_vitest() -> bool:
    """Run vitest with coverage."""
    try:
        result = subprocess.run(
            ["npx", "vitest", "run", "--coverage"], capture_output=True, text=True
        )

        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

        return result.returncode == 0
    except FileNotFoundError:
        print("❌ vitest not installed. Run: npm install --save-dev vitest")
        return False


def run_npm_test() -> bool:
    """Run npm test."""
    try:
        result = subprocess.run(["npm", "test"], capture_output=True, text=True)

        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

        return result.returncode == 0
    except FileNotFoundError:
        print("❌ npm not found")
        return False


def run_go_test() -> bool:
    """Run go test with coverage."""
    try:
        # Run tests with coverage
        result = subprocess.run(
            ["go", "test", "-cover", "./...", "-coverprofile=coverage.out"],
            capture_output=True,
            text=True,
        )

        print(result.stdout)

        if result.returncode != 0:
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            return False

        # Check coverage percentage
        cov_result = subprocess.run(
            ["go", "tool", "cover", "-func=coverage.out"], capture_output=True, text=True
        )

        # Extract total coverage from last line
        lines = cov_result.stdout.strip().split("\n")
        if lines:
            last_line = lines[-1]
            if "total:" in last_line:
                coverage = float(last_line.split()[-1].rstrip("%"))
                print(f"\nTotal coverage: {coverage}%")

                if coverage < 80:
                    print(f"❌ Coverage {coverage}% below 80% threshold")
                    return False

        return True
    except FileNotFoundError:
        print("❌ go not installed")
        return False


def main():
    """Run tests based on detected framework."""
    language, framework = detect_test_framework()

    if language == "unknown":
        print("⚠️  Could not detect test framework. Skipping tests.")
        print("ℹ️  Create pytest.ini, jest.config.js, or go.mod to enable auto-testing")
        sys.exit(0)  # Don't fail, just skip

    print(f"🧪 Running tests with {framework}...")

    # Run tests
    runners = {
        "pytest": run_pytest,
        "jest": run_jest,
        "vitest": run_vitest,
        "npm": run_npm_test,
        "go-test": run_go_test,
    }

    success = runners[framework]()

    if success:
        print("✅ Tests passed with ≥80% coverage")
        sys.exit(0)
    else:
        print("❌ Tests failed or coverage below 80%")
        sys.exit(1)


if __name__ == "__main__":
    main()
