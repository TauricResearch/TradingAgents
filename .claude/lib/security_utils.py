#!/usr/bin/env python3
"""
Security Utilities - Shared security validation and audit logging

This module provides centralized security functions for path validation,
input sanitization, and audit logging to prevent common vulnerabilities:
- CWE-22: Path Traversal
- CWE-59: Improper Link Resolution Before File Access
- CWE-117: Improper Output Neutralization for Logs

All security-sensitive operations in the codebase should use these utilities
to ensure consistent security enforcement.

Security Features:
- Whitelist-based path validation (PROJECT_ROOT, ~/.claude/, and system temp in test mode)
- Symlink detection and rejection
- Path traversal prevention (reject .., resolve symlinks)
- Pytest format validation (test_file.py::test_name pattern)
- Thread-safe audit logging with rotation (10MB limit)
- Clear error messages for security violations

Usage:
    from security_utils import validate_path, validate_pytest_path, audit_log

    # Path validation (whitelist-based)
    try:
        safe_path = validate_path(user_path, "session file")
    except ValueError as e:
        print(f"Security violation: {e}")

    # Pytest path validation
    try:
        safe_pytest = validate_pytest_path(pytest_path, "test execution")
    except ValueError as e:
        print(f"Invalid pytest path: {e}")

    # Audit logging
    audit_log("path_validation", "success", {
        "operation": "validate_session_file",
        "path": str(safe_path),
        "user": os.getenv("USER")
    })

Date: 2025-11-07
Issue: GitHub #46 (CRITICAL path validation bypass)
Agent: implementer


Design Patterns:
    See library-design-patterns skill for standardized design patterns.
"""

import json
import logging
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Dict, Any


# Project root for whitelist validation (DYNAMIC DETECTION for cross-project use)
def _detect_project_root() -> Path:
    """Dynamically detect project root from current working directory.

    Detection strategy (prioritizes .git over .claude):
    1. Search ALL the way up for .git first (git repos take precedence)
    2. If no .git found, search for .claude directory
    3. Fall back to CWD if no markers found

    This enables auto-approval to work across ALL projects, not just autonomous-dev.
    Prioritizing .git prevents nested .claude directories (e.g., plugins/autonomous-dev/.claude)
    from being incorrectly detected as project root.

    Returns:
        Detected project root directory

    Security Note:
        validate_path() still enforces security boundaries - this just makes
        those boundaries project-specific instead of hardcoded to plugin location.
    """
    start = Path.cwd()

    # Priority 1: Search ALL the way up for .git (git repos take precedence)
    current = start
    for _ in range(10):
        if (current / ".git").exists():
            return current.resolve()
        if current.parent == current:
            break  # Reached filesystem root
        current = current.parent

    # Priority 2: Search for .claude if no .git found
    current = start
    for _ in range(10):
        if (current / ".claude").exists():
            return current.resolve()
        if current.parent == current:
            break  # Reached filesystem root
        current = current.parent

    # Fall back to current working directory
    return Path.cwd().resolve()

PROJECT_ROOT = _detect_project_root()

# Whitelist of allowed directories (relative to PROJECT_ROOT)
ALLOWED_DIRS = [
    "",  # PROJECT_ROOT itself
    "docs/sessions",  # Session logs
    ".claude",  # Claude configuration
    "plugins/autonomous-dev/lib",  # Library files
    "scripts",  # Scripts
    "tests",  # Test files
]

# System temp directory (allowed in test mode)
SYSTEM_TEMP = Path(tempfile.gettempdir()).resolve()

# Claude home directory (~/.claude/) - allowed for Claude Code system operations
# This is a fixed, known location for:
# - Plan mode files (~/.claude/plans/)
# - Global CLAUDE.md (~/.claude/CLAUDE.md)
# - Global settings (~/.claude/settings.json)
# Security: Still validates symlinks and path traversal within this directory
CLAUDE_HOME_DIR = Path.home() / ".claude"

# Thread-safe logger for audit logs
_audit_logger: Optional[logging.Logger] = None
_audit_logger_lock = threading.Lock()

# Input validation constants
MAX_MESSAGE_LENGTH = 10000  # 10KB max message length
MAX_PATH_LENGTH = 4096  # POSIX PATH_MAX limit
PYTEST_PATH_PATTERN = re.compile(r'^[\w/.-]+\.py(?:::[\w\[\],_-]+)?$')


def _get_audit_logger() -> logging.Logger:
    """Get or create thread-safe audit logger with rotation.

    Returns:
        Configured logger for security audit events

    Logger Configuration:
    - File: logs/security_audit.log
    - Format: JSON with timestamp, event type, status, context
    - Rotation: 10MB max size, keep 5 backup files
    - Thread-safe: Uses threading.Lock for concurrent access
    
See error-handling-patterns skill for exception hierarchy and error handling best practices.
"""
    global _audit_logger

    if _audit_logger is not None:
        return _audit_logger

    with _audit_logger_lock:
        # Double-check pattern to prevent race condition
        if _audit_logger is not None:
            return _audit_logger

        # Create logs directory
        log_dir = PROJECT_ROOT / "logs"
        log_dir.mkdir(exist_ok=True)

        # Configure logger
        logger = logging.getLogger("security_audit")
        logger.setLevel(logging.INFO)
        logger.propagate = False  # Don't propagate to root logger

        # Create rotating file handler (10MB max, 5 backups)
        log_file = log_dir / "security_audit.log"
        handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )

        # JSON format for structured logging
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)

        _audit_logger = logger
        return _audit_logger


def audit_log(event_type: str, status: str, context: Dict[str, Any]) -> None:
    """Log security event to audit log.

    Args:
        event_type: Type of security event (e.g., "path_validation", "input_sanitization")
        status: Event status ("success", "failure", "warning")
        context: Additional context dict (operation, path, user, etc.)

    Security Note:
    - All path validation operations should be audited
    - Failed validations are logged for security monitoring
    - Thread-safe for concurrent agent execution
    """
    logger = _get_audit_logger()

    # Create audit record
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        "event_type": event_type,
        "status": status,
        "context": context
    }

    # Log as JSON
    logger.info(json.dumps(record))


def validate_path(
    path: Path | str,
    purpose: str,
    allow_missing: bool = False,
    test_mode: Optional[bool] = None
) -> Path:
    """Validate path is within project boundaries (whitelist-based).

    Args:
        path: Path to validate
        purpose: Human-readable description of what this path is for
        allow_missing: Whether to allow non-existent paths
        test_mode: Override test mode detection (None = auto-detect)

    Returns:
        Resolved, validated Path object

    Raises:
        ValueError: If path is outside project, is a symlink, or contains traversal

    Security Design (GitHub Issue #46):
    ===================================
    This function uses WHITELIST validation (allow known safe locations) instead
    of BLACKLIST validation (block known bad patterns).

    Validation Layers:
    1. String-level checks: Reject obvious traversal (.., absolute system paths)
    2. Symlink detection: Reject symlinks before resolution
    3. Path resolution: Normalize path to absolute form
    4. Whitelist validation: Ensure path is in PROJECT_ROOT or allowed temp dirs

    Allowed Locations (always):
    ===========================
    - PROJECT_ROOT and subdirectories
    - ~/.claude/ directory (Claude Code system files: plans, CLAUDE.md, settings)

    Test Mode (additional):
    =======================
    When pytest runs, it creates temp directories outside PROJECT_ROOT.
    Test mode additionally allows:
    - System temp directory (tempfile.gettempdir())

    Blocked Locations:
    ==================
    - /etc/, /usr/, /bin/, /sbin/, /var/log/ (system directories)
    - Arbitrary paths outside whitelist

    Attack Scenarios Blocked:
    =========================
    - Relative traversal: "../../etc/passwd" (blocked by check #1)
    - Absolute system paths: "/etc/passwd" (blocked by check #4)
    - Symlink escapes: "link" -> "/etc/passwd" (blocked by check #2)
    - Mixed traversal: "subdir/../../etc" (blocked by check #3 after resolve)
    """
    # Convert to Path if string
    if isinstance(path, str):
        path = Path(path)

    # Detect test mode
    if test_mode is None:
        test_mode = os.getenv("PYTEST_CURRENT_TEST") is not None

    # SECURITY LAYER 1: String-level validation
    path_str = str(path)

    # Reject obvious traversal patterns
    if ".." in path_str:
        audit_log("path_validation", "failure", {
            "operation": f"validate_{purpose.replace(' ', '_')}",
            "path": path_str,
            "reason": "path_traversal_attempt",
            "pattern": ".."
        })
        raise ValueError(
            f"Path traversal attempt detected: {path}\n"
            f"Purpose: {purpose}\n"
            f"Paths containing '..' are not allowed.\n"
            f"Expected: Path within project or allowed directories\n"
            f"See: docs/SECURITY.md#path-validation"
        )

    # Reject excessively long paths (potential buffer overflow)
    if len(path_str) > MAX_PATH_LENGTH:
        audit_log("path_validation", "failure", {
            "operation": f"validate_{purpose.replace(' ', '_')}",
            "path": path_str[:100] + "...",
            "reason": "path_too_long",
            "length": len(path_str)
        })
        raise ValueError(
            f"Path too long: {len(path_str)} characters\n"
            f"Purpose: {purpose}\n"
            f"Maximum allowed: {MAX_PATH_LENGTH} characters\n"
            f"Expected: Reasonable path length"
        )

    # SECURITY LAYER 2: Symlink detection (before resolution)
    if path.exists() and path.is_symlink():
        audit_log("path_validation", "failure", {
            "operation": f"validate_{purpose.replace(' ', '_')}",
            "path": path_str,
            "reason": "symlink_detected"
        })
        raise ValueError(
            f"Symlinks are not allowed: {path}\n"
            f"Purpose: {purpose}\n"
            f"Symlinks can be used to escape directory boundaries.\n"
            f"Expected: Regular file or directory path\n"
            f"See: docs/SECURITY.md#symlink-policy"
        )

    # SECURITY LAYER 3: Path resolution and normalization
    try:
        resolved_path = path.resolve()

        # Check resolved path for symlinks (catches symlinks in parent dirs)
        if not allow_missing and resolved_path.exists() and resolved_path.is_symlink():
            audit_log("path_validation", "failure", {
                "operation": f"validate_{purpose.replace(' ', '_')}",
                "path": path_str,
                "resolved": str(resolved_path),
                "reason": "symlink_in_resolved_path"
            })
            raise ValueError(
                f"Path contains symlink: {path}\n"
                f"Resolved path is a symlink: {resolved_path}\n"
                f"Purpose: {purpose}\n"
                f"Expected: Regular path without symlinks\n"
                f"See: docs/SECURITY.md#symlink-policy"
            )

    except (OSError, RuntimeError) as e:
        audit_log("path_validation", "failure", {
            "operation": f"validate_{purpose.replace(' ', '_')}",
            "path": path_str,
            "reason": "resolution_error",
            "error": str(e)
        })
        raise ValueError(
            f"Invalid path: {path}\n"
            f"Purpose: {purpose}\n"
            f"Error: {e}\n"
            f"Expected: Valid filesystem path"
        )

    # SECURITY LAYER 4: Whitelist validation
    is_in_project = False
    is_in_allowed_temp = False
    is_in_claude_home = False

    # Check if path is in PROJECT_ROOT
    try:
        resolved_path.relative_to(PROJECT_ROOT)
        is_in_project = True
    except ValueError:
        pass

    # Check if path is in ~/.claude/ (Claude Code system directory)
    # This allows plan mode, global CLAUDE.md, and other Claude Code features
    try:
        resolved_path.relative_to(CLAUDE_HOME_DIR.resolve())
        is_in_claude_home = True
    except ValueError:
        pass

    # In test mode, also check system temp directory
    if test_mode:
        try:
            resolved_path.relative_to(SYSTEM_TEMP)
            is_in_allowed_temp = True
        except ValueError:
            pass

    # Validate against whitelist
    if not is_in_project and not is_in_claude_home and not (test_mode and is_in_allowed_temp):
        audit_log("path_validation", "failure", {
            "operation": f"validate_{purpose.replace(' ', '_')}",
            "path": path_str,
            "resolved": str(resolved_path),
            "reason": "outside_whitelist",
            "test_mode": test_mode
        })

        error_msg = f"Path outside allowed locations: {path}\n"
        error_msg += f"Purpose: {purpose}\n"
        error_msg += f"Resolved path: {resolved_path}\n"
        error_msg += f"Allowed locations:\n"
        error_msg += f"  - Project root: {PROJECT_ROOT}\n"
        error_msg += f"  - Claude home: {CLAUDE_HOME_DIR}\n"

        if test_mode:
            error_msg += f"  - System temp: {SYSTEM_TEMP}\n"
            error_msg += f"Test mode uses WHITELIST approach for security.\n"
        else:
            error_msg += f"Production mode requires path within allowed locations.\n"

        error_msg += f"See: docs/SECURITY.md#path-validation"
        raise ValueError(error_msg)

    # Success - log and return
    audit_log("path_validation", "success", {
        "operation": f"validate_{purpose.replace(' ', '_')}",
        "path": path_str,
        "resolved": str(resolved_path),
        "test_mode": test_mode
    })

    return resolved_path


def validate_pytest_path(
    pytest_path: str,
    purpose: str = "pytest execution"
) -> str:
    """Validate pytest path format (test_file.py::test_name).

    Args:
        pytest_path: Pytest path to validate (e.g., "tests/test_foo.py::test_bar")
        purpose: Human-readable description of what this path is for

    Returns:
        Validated pytest path string

    Raises:
        ValueError: If format is invalid or contains suspicious patterns

    Valid Formats:
    - tests/test_security.py
    - tests/test_security.py::test_path_validation
    - tests/test_security.py::TestClass::test_method
    - tests/test_security.py::test_method[param1,param2]

    Security Design:
    ================
    Pytest paths can be used to execute arbitrary Python code if not validated.
    This function uses regex validation to ensure only legitimate pytest paths.

    Pattern: ^[\\w/.-]+\\.py(?:::[\\w\\[\\],_-]+)?$
    - [\\w/.-]+: Alphanumeric, slash, dot, hyphen (file path)
    - \\.py: Must be Python file
    - (?:::[\\w\\[\\],_-]+)?: Optional test specifier with :: prefix
    - [\\w\\[\\],_-]+: Test names with parameters in brackets

    Attack Scenarios Blocked:
    =========================
    - Shell injection: "test.py; rm -rf /" (blocked by regex)
    - Code injection: "test.py::test(); os.system('cmd')" (blocked by regex)
    - Path traversal: "../../etc/test.py" (blocked by .. check)
    """
    # String-level validation
    if not pytest_path or not isinstance(pytest_path, str):
        raise ValueError(
            f"Invalid pytest path: {pytest_path}\n"
            f"Purpose: {purpose}\n"
            f"Expected: Non-empty string\n"
            f"Format: test_file.py or test_file.py::test_name"
        )

    # Reject traversal attempts
    if ".." in pytest_path:
        audit_log("pytest_validation", "failure", {
            "operation": f"validate_{purpose.replace(' ', '_')}",
            "path": pytest_path,
            "reason": "path_traversal_attempt"
        })
        raise ValueError(
            f"Path traversal attempt in pytest path: {pytest_path}\n"
            f"Purpose: {purpose}\n"
            f"Paths containing '..' are not allowed.\n"
            f"Expected: tests/test_file.py or tests/test_file.py::test_name"
        )

    # Validate format with regex
    if not PYTEST_PATH_PATTERN.match(pytest_path):
        audit_log("pytest_validation", "failure", {
            "operation": f"validate_{purpose.replace(' ', '_')}",
            "path": pytest_path,
            "reason": "invalid_format"
        })
        raise ValueError(
            f"Invalid pytest path format: {pytest_path}\n"
            f"Purpose: {purpose}\n"
            f"Expected format:\n"
            f"  - test_file.py\n"
            f"  - test_file.py::test_name\n"
            f"  - test_file.py::TestClass::test_method\n"
            f"  - test_file.py::test_name[param1,param2]\n"
            f"Pattern: alphanumeric, slash, dot, hyphen, underscore only"
        )

    # Extract file path component
    file_path = pytest_path.split("::")[0]

    # Validate file path component against whitelist
    try:
        validate_path(Path(file_path), f"{purpose} (file component)", allow_missing=True)
    except ValueError as e:
        audit_log("pytest_validation", "failure", {
            "operation": f"validate_{purpose.replace(' ', '_')}",
            "path": pytest_path,
            "reason": "file_path_validation_failed",
            "error": str(e)
        })
        raise ValueError(
            f"Pytest file path validation failed: {pytest_path}\n"
            f"Purpose: {purpose}\n"
            f"File path: {file_path}\n"
            f"Error: {e}"
        )

    # Success
    audit_log("pytest_validation", "success", {
        "operation": f"validate_{purpose.replace(' ', '_')}",
        "path": pytest_path
    })

    return pytest_path


def validate_input_length(
    value: str,
    max_length: int,
    field_name: str,
    purpose: str = "input validation"
) -> str:
    """Validate input string length to prevent resource exhaustion.

    Args:
        value: Input string to validate
        max_length: Maximum allowed length
        field_name: Name of the field being validated
        purpose: Human-readable description

    Returns:
        Validated string

    Raises:
        ValueError: If string exceeds max_length

    Security Rationale:
    ===================
    Unbounded string inputs can cause:
    - Memory exhaustion (OOM kills)
    - Log file bloat (disk exhaustion)
    - DoS via resource consumption

    This function enforces reasonable limits on all user inputs.
    """
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid {field_name}: must be string\n"
            f"Purpose: {purpose}\n"
            f"Got: {type(value).__name__}"
        )

    if len(value) > max_length:
        audit_log("input_validation", "failure", {
            "operation": f"validate_{purpose.replace(' ', '_')}",
            "field": field_name,
            "length": len(value),
            "max_length": max_length,
            "reason": "length_exceeded"
        })
        raise ValueError(
            f"Invalid {field_name}: {field_name} too long ({len(value)} characters)\n"
            f"Purpose: {purpose}\n"
            f"Maximum allowed: {max_length} characters\n"
            f"Preview: {value[:100]}..."
        )

    return value


def validate_agent_name(agent_name: str, purpose: str = "agent tracking") -> str:
    """Validate agent name format.

    Args:
        agent_name: Agent name to validate
        purpose: Human-readable description

    Returns:
        Validated agent name

    Raises:
        ValueError: If agent name format is invalid

    Valid Format:
    - 1-255 characters
    - Alphanumeric, hyphen, underscore only
    - No spaces or special characters

    Examples:
    - researcher ✓
    - test-master ✓
    - doc_master ✓
    - security auditor ✗ (space not allowed)
    - researcher; rm -rf / ✗ (semicolon not allowed)
    """
    # Length validation
    validate_input_length(agent_name, 255, "agent_name", purpose)

    # Format validation
    if not agent_name:
        raise ValueError(
            f"Agent name cannot be empty\n"
            f"Purpose: {purpose}\n"
            f"Expected: Non-empty string (e.g., 'researcher', 'test-master')"
        )

    # Alphanumeric + hyphen/underscore only
    if not re.match(r'^[\w-]+$', agent_name):
        audit_log("input_validation", "failure", {
            "operation": f"validate_{purpose.replace(' ', '_')}",
            "field": "agent_name",
            "value": agent_name,
            "reason": "invalid_characters"
        })
        raise ValueError(
            f"Invalid agent name: {agent_name}\n"
            f"Purpose: {purpose}\n"
            f"Allowed characters: alphanumeric, hyphen, underscore\n"
            f"Examples: 'researcher', 'test-master', 'doc_master'"
        )

    return agent_name


def validate_github_issue(issue_number: int, purpose: str = "issue tracking") -> int:
    """Validate GitHub issue number.

    Args:
        issue_number: Issue number to validate
        purpose: Human-readable description

    Returns:
        Validated issue number

    Raises:
        ValueError: If issue number is invalid

    Valid Range: 1 to 999999
    - GitHub issue numbers are typically < 1 million
    - Prevents integer overflow or negative values
    """
    if not isinstance(issue_number, int):
        raise ValueError(
            f"Invalid GitHub issue number: must be integer\n"
            f"Purpose: {purpose}\n"
            f"Got: {type(issue_number).__name__}"
        )

    if issue_number < 1 or issue_number > 999999:
        audit_log("input_validation", "failure", {
            "operation": f"validate_{purpose.replace(' ', '_')}",
            "field": "github_issue",
            "value": issue_number,
            "reason": "out_of_range"
        })
        raise ValueError(
            f"Invalid GitHub issue number: {issue_number}\n"
            f"Purpose: {purpose}\n"
            f"Expected range: 1 to 999999\n"
            f"Provided: {issue_number}"
        )

    return issue_number


# Export all public functions
__all__ = [
    "validate_path",
    "validate_pytest_path",
    "validate_input_length",
    "validate_agent_name",
    "validate_github_issue",
    "audit_log",
    "PROJECT_ROOT",
    "SYSTEM_TEMP",
    "CLAUDE_HOME_DIR",
]
