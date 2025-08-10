#!/usr/bin/env python3
"""
Test runner script for TradingAgents.

This script provides convenient commands for running different types of tests.
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path


def run_command(cmd, description=""):
    """Run a command and handle errors."""
    if description:
        print(f"\n🔄 {description}")
    
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)
    
    if result.returncode != 0:
        print(f"❌ Command failed with return code {result.returncode}")
        sys.exit(result.returncode)
    else:
        print(f"✅ {description or 'Command completed successfully'}")


def main():
    """Main entry point for test runner."""
    parser = argparse.ArgumentParser(description="TradingAgents Test Runner")
    parser.add_argument(
        "test_type",
        choices=["unit", "integration", "all", "coverage", "fast", "slow", "lint"],
        help="Type of tests to run"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose output"
    )
    parser.add_argument(
        "--parallel", "-p", action="store_true", help="Run tests in parallel"
    )
    parser.add_argument(
        "--file", "-f", help="Run specific test file"
    )
    parser.add_argument(
        "--pattern", "-k", help="Run tests matching pattern"
    )
    
    args = parser.parse_args()
    
    # Base pytest command
    base_cmd = ["python", "-m", "pytest"]
    
    if args.verbose:
        base_cmd.append("-v")
    
    if args.parallel:
        base_cmd.extend(["-n", "auto"])
    
    if args.pattern:
        base_cmd.extend(["-k", args.pattern])
    
    # Configure based on test type
    if args.test_type == "unit":
        cmd = base_cmd + ["tests/unit/", "-m", "unit"]
        run_command(cmd, "Running unit tests")
        
    elif args.test_type == "integration":
        cmd = base_cmd + ["tests/integration/", "-m", "integration"]
        run_command(cmd, "Running integration tests")
        
    elif args.test_type == "all":
        cmd = base_cmd + ["tests/"]
        run_command(cmd, "Running all tests")
        
    elif args.test_type == "coverage":
        cmd = base_cmd + [
            "tests/",
            "--cov=tradingagents",
            "--cov=cli",
            "--cov-report=html:htmlcov",
            "--cov-report=term-missing",
            "--cov-report=xml",
        ]
        run_command(cmd, "Running tests with coverage")
        print("\n📊 Coverage report generated:")
        print("  - HTML: htmlcov/index.html")
        print("  - XML: coverage.xml")
        
    elif args.test_type == "fast":
        cmd = base_cmd + ["tests/unit/", "-m", "unit", "--durations=10"]
        run_command(cmd, "Running fast unit tests")
        
    elif args.test_type == "slow":
        cmd = base_cmd + ["tests/", "-m", "slow", "--timeout=600"]
        run_command(cmd, "Running slow tests")
        
    elif args.test_type == "lint":
        # Run mypy
        cmd = ["python", "-m", "mypy", "tradingagents/", "cli/", "tests/"]
        run_command(cmd, "Running mypy type checking")
        
        # Run pytest on tests only for syntax
        cmd = base_cmd + ["tests/", "--collect-only"]
        run_command(cmd, "Validating test syntax")
        
    elif args.file:
        cmd = base_cmd + [args.file]
        run_command(cmd, f"Running tests in {args.file}")
    
    print("\n🎉 All tests completed successfully!")


if __name__ == "__main__":
    # Ensure we're in the project directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    main()