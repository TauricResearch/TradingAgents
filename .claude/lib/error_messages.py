#!/usr/bin/env python3
"""
Centralized error messaging framework for autonomous-dev plugin.

Provides consistent, helpful error messages following the pattern:
- WHERE: Current context (Python env, directory, hook/script)
- WHAT: What went wrong
- HOW: Step-by-step fix instructions
- LEARN MORE: Link to documentation

All errors include error codes (ERR-XXX) for searchability.


Design Patterns:
    See library-design-patterns skill for standardized design patterns.
"""

import os
import sys
from pathlib import Path
from typing import Optional, List


# Error code registry
class ErrorCode:
    """Error code constants for autonomous-dev plugin."""

    # Installation & Setup (ERR-100s)
    FORMATTER_NOT_FOUND = "ERR-101"
    PROJECT_MD_MISSING = "ERR-102"
    GITHUB_TOKEN_INVALID = "ERR-103"
    PYTHON_VERSION_MISMATCH = "ERR-104"
    DEPENDENCY_MISSING = "ERR-105"

    # Hook Errors (ERR-200s)
    HOOK_EXECUTION_FAILED = "ERR-201"
    HOOK_NOT_EXECUTABLE = "ERR-202"
    HOOK_TIMEOUT = "ERR-203"

    # Validation Errors (ERR-300s)
    VALIDATION_FAILED = "ERR-301"
    TEST_COVERAGE_LOW = "ERR-302"
    SECURITY_ISSUE_FOUND = "ERR-303"
    COMMAND_INVALID = "ERR-304"

    # File/Directory Errors (ERR-400s)
    FILE_NOT_FOUND = "ERR-401"
    DIRECTORY_NOT_FOUND = "ERR-402"
    PERMISSION_DENIED = "ERR-403"
    FILE_PARSE_ERROR = "ERR-404"

    # Configuration Errors (ERR-500s)
    CONFIG_MISSING = "ERR-501"
    CONFIG_INVALID = "ERR-502"
    ENVIRONMENT_MISMATCH = "ERR-503"


class ErrorContext:
    """Captures current execution context for error messages."""

    def __init__(self):
        self.python_path = sys.executable
        self.python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        self.working_dir = Path.cwd()
        self.script_name = Path(sys.argv[0]).name if sys.argv else "unknown"
        self.hook_type = os.environ.get('HOOK_TYPE', None)

    def format(self) -> str:
        """Format context for error messages."""
        lines = [
            "Where you are:",
            f"  • Python: {self.python_path} (v{self.python_version})",
            f"  • Working directory: {self.working_dir}",
        ]

        if self.hook_type:
            lines.append(f"  • Hook: {self.script_name} ({self.hook_type})")
        else:
            lines.append(f"  • Script: {self.script_name}")

        return "\n".join(lines)


class ErrorMessage:
    """Builder for structured, helpful error messages."""

    def __init__(
        self,
        code: str,
        title: str,
        what_wrong: str,
        how_to_fix: List[str],
        learn_more: Optional[str] = None,
        context: Optional[ErrorContext] = None
    ):
        self.code = code
        self.title = title
        self.what_wrong = what_wrong
        self.how_to_fix = how_to_fix
        self.learn_more = learn_more
        self.context = context or ErrorContext()

    def format(self, include_context: bool = True) -> str:
        """Format complete error message."""
        lines = [
            "",
            "=" * 70,
            f"ERROR: {self.title} [{self.code}]",
            "=" * 70,
            ""
        ]

        if include_context:
            lines.append(self.context.format())
            lines.append("")

        lines.append("What's wrong:")
        lines.append(f"  • {self.what_wrong}")
        lines.append("")

        lines.append("How to fix:")
        for i, step in enumerate(self.how_to_fix, 1):
            # Multi-line steps
            step_lines = step.split('\n')
            lines.append(f"  {i}. {step_lines[0]}")
            for extra_line in step_lines[1:]:
                lines.append(f"     {extra_line}")
        lines.append("")

        if self.learn_more:
            lines.append(f"Learn more: {self.learn_more}")
            lines.append("")

        lines.append("=" * 70)
        lines.append("")

        return "\n".join(lines)

    def print(self, include_context: bool = True, file=sys.stderr):
        """Print error message to stderr."""
        print(self.format(include_context=include_context), file=file)


# Common error message templates
def formatter_not_found_error(formatter_name: str, python_path: str) -> ErrorMessage:
    """Standard error for missing formatters (black, isort, etc.)"""
    return ErrorMessage(
        code=ErrorCode.FORMATTER_NOT_FOUND,
        title=f"{formatter_name} not found",
        what_wrong=f"{formatter_name} formatter not installed in current Python environment",
        how_to_fix=[
            f"Install in current environment:\n{python_path} -m pip install {formatter_name}",
            "OR use project virtualenv:\nsource venv/bin/activate\npip install {formatter_name}",
            "OR skip formatting for this commit:\ngit commit --no-verify"
        ],
        learn_more="docs/TROUBLESHOOTING.md#issue-1-hooks-not-running"
    )


def project_md_missing_error(expected_path: Path) -> ErrorMessage:
    """Standard error for missing PROJECT.md"""
    return ErrorMessage(
        code=ErrorCode.PROJECT_MD_MISSING,
        title="PROJECT.md not found",
        what_wrong=f"PROJECT.md file not found at: {expected_path}",
        how_to_fix=[
            "Create PROJECT.md from template:\n/setup",
            "OR copy template manually:\ncp .claude/templates/PROJECT.md PROJECT.md\nvim PROJECT.md",
            "OR skip PROJECT.md validation (not recommended):\nDISABLE_PROJECT_MD=1 [your command]"
        ],
        learn_more="docs/TROUBLESHOOTING.md#issue-3-projectmd-missing"
    )


def dependency_missing_error(
    package_name: str,
    required_for: str,
    python_path: str
) -> ErrorMessage:
    """Standard error for missing Python dependencies"""
    return ErrorMessage(
        code=ErrorCode.DEPENDENCY_MISSING,
        title=f"Dependency missing: {package_name}",
        what_wrong=f"{package_name} is required for {required_for}",
        how_to_fix=[
            f"Install dependency:\n{python_path} -m pip install {package_name}",
            "OR install all plugin dependencies:\npip install -r .claude/plugins/autonomous-dev/requirements.txt",
            f"OR disable {required_for}:\n[See documentation for disabling specific features]"
        ],
        learn_more="docs/TROUBLESHOOTING.md#dependency-issues"
    )


def validation_failed_error(
    what_failed: str,
    failures: List[str],
    fix_command: Optional[str] = None
) -> ErrorMessage:
    """Standard error for validation failures"""
    what_wrong = f"{what_failed}\n" + "\n".join(f"  - {f}" for f in failures)

    how_to_fix = []
    if fix_command:
        how_to_fix.append(f"Run fix command:\n{fix_command}")

    how_to_fix.extend([
        "Review failures above and fix manually",
        "OR skip validation (not recommended):\ngit commit --no-verify"
    ])

    return ErrorMessage(
        code=ErrorCode.VALIDATION_FAILED,
        title=f"{what_failed}",
        what_wrong=what_wrong,
        how_to_fix=how_to_fix,
        learn_more="docs/TROUBLESHOOTING.md#validation-failures"
    )


def file_not_found_error(file_path: Path, expected_purpose: str) -> ErrorMessage:
    """Standard error for missing files"""
    return ErrorMessage(
        code=ErrorCode.FILE_NOT_FOUND,
        title="File not found",
        what_wrong=f"Expected file not found: {file_path}\nPurpose: {expected_purpose}",
        how_to_fix=[
            f"Create the file:\ntouch {file_path}",
            "OR check if file moved:\nfind . -name '{}' -type f".format(file_path.name),
            "OR restore from git:\ngit checkout HEAD -- {}".format(file_path)
        ],
        learn_more="docs/TROUBLESHOOTING.md#file-not-found"
    )


def config_invalid_error(
    config_file: Path,
    errors: List[str],
    example_config: Optional[str] = None
) -> ErrorMessage:
    """Standard error for invalid configuration"""
    what_wrong = f"Configuration file has errors: {config_file}\n" + "\n".join(f"  - {e}" for e in errors)

    how_to_fix = []
    if example_config:
        how_to_fix.append(f"Use example configuration:\n{example_config}")

    how_to_fix.extend([
        f"Edit configuration:\nvim {config_file}",
        f"OR reset to defaults:\nmv {config_file} {config_file}.backup\n[regenerate config]"
    ])

    return ErrorMessage(
        code=ErrorCode.CONFIG_INVALID,
        title="Invalid configuration",
        what_wrong=what_wrong,
        how_to_fix=how_to_fix,
        learn_more="docs/TROUBLESHOOTING.md#configuration-errors"
    )


# Utility functions
def print_error(message: ErrorMessage, include_context: bool = True):
    """Print error message and exit with code 1."""
    message.print(include_context=include_context)
    sys.exit(1)


def print_warning(title: str, message: str, file=sys.stderr):
    """Print warning (non-fatal) message."""
    print("", file=file)
    print("⚠️  WARNING: {}".format(title), file=file)
    print(f"   {message}", file=file)
    print("", file=file)


def print_info(title: str, message: str):
    """Print informational message."""
    print("")
    print(f"ℹ️  {title}")
    print(f"   {message}")
    print("")


if __name__ == "__main__":
    # Demo error messages
    print("=" * 70)
    print("ERROR MESSAGE FRAMEWORK DEMO")
    print("=" * 70)
    print()

    # Example 1: Formatter not found
    err1 = formatter_not_found_error("black", sys.executable)
    err1.print()

    # Example 2: PROJECT.md missing
    err2 = project_md_missing_error(Path("PROJECT.md"))
    err2.print()

    # Example 3: Validation failed
    err3 = validation_failed_error(
        "Test coverage below minimum",
        ["src/module_a.py: 65% (needs 80%)", "src/module_b.py: 45% (needs 80%)"],
        fix_command="pytest --cov=src --cov-report=term-missing"
    )
    err3.print()

    print()
    print("=" * 70)
    print("See lib/error_messages.py for full API")
    print("=" * 70)
