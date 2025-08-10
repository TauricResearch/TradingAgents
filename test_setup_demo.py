#!/usr/bin/env python3
"""
Demo script to test the testing infrastructure setup.

This script runs a few basic tests to verify the testing setup is working correctly.
"""

import sys
import subprocess
import os
from pathlib import Path


def run_command(cmd, description=""):
    """Run a command and return success status."""
    if description:
        print(f"\n🔄 {description}")

    print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"✅ {description or 'Command completed successfully'}")
            return True
        else:
            print("❌ Command failed:")
            print(result.stderr)
            return False
    except subprocess.TimeoutExpired:
        print("⏱️ Command timed out")
        return False
    except Exception as e:
        print(f"❌ Error running command: {e}")
        return False


def main():
    """Run setup verification tests."""
    print("🧪 TradingAgents Test Setup Verification")
    print("=" * 50)

    # Change to project directory
    project_dir = Path(__file__).parent
    os.chdir(project_dir)

    success_count = 0
    total_tests = 0

    # Test 1: Check if pytest is installed and can discover tests
    total_tests += 1
    if run_command(
        ["python", "-m", "pytest", "--version"], "Checking pytest installation"
    ):
        success_count += 1

    # Test 2: Test discovery
    total_tests += 1
    if run_command(
        ["python", "-m", "pytest", "tests/", "--collect-only", "-q"],
        "Testing test discovery",
    ):
        success_count += 1

    # Test 3: Check if mypy can run
    total_tests += 1
    if run_command(["python", "-m", "mypy", "--version"], "Checking mypy installation"):
        success_count += 1

    # Test 4: Run a simple syntax check on test files
    total_tests += 1
    if run_command(
        ["python", "-c", "import tests.conftest; print('Test imports work!')"],
        "Testing test imports",
    ):
        success_count += 1

    # Test 5: Check if we can import the main module
    total_tests += 1
    if run_command(
        [
            "python",
            "-c",
            "import tradingagents.config; print('Main module imports work!')",
        ],
        "Testing main module imports",
    ):
        success_count += 1

    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Setup Verification Results:")
    print(f"✅ Successful: {success_count}/{total_tests}")
    print(f"❌ Failed: {total_tests - success_count}/{total_tests}")

    if success_count == total_tests:
        print("\n🎉 All verification tests passed! Your test setup is ready.")
        print("\n📚 Next steps:")
        print("1. Install test dependencies: pip install -r requirements.txt")
        print("2. Run unit tests: make test-unit")
        print("3. Run all tests: make test")
        print("4. Generate coverage report: make test-coverage")
        return 0
    else:
        print("\n⚠️  Some verification tests failed. Please check the setup.")
        print("\n🔧 Troubleshooting:")
        print("1. Ensure you're in a virtual environment")
        print("2. Install dependencies: pip install -r requirements.txt")
        print("3. Check that all required packages are installed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
