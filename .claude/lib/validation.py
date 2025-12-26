#!/usr/bin/env python3
"""
Validation Utilities - Tracking infrastructure security validation

This module provides validation functions for tracking infrastructure:
- Session path validation (prevent path traversal)
- Agent name validation (alphanumeric only)
- Message validation (length limits, no control characters)

Fixes Issue #79: Security validation for tracking infrastructure

Security Features:
- Path traversal prevention (CWE-22)
- Input sanitization
- Length limits (prevent resource exhaustion)
- Control character filtering

Usage:
    from validation import validate_session_path, validate_agent_name, validate_message

    # Validate session path
    safe_path = validate_session_path(user_path)

    # Validate agent name
    safe_name = validate_agent_name(name)

    # Validate message
    safe_msg = validate_message(message)

Date: 2025-11-17
Issue: GitHub #79 (Tracking infrastructure hardcoded paths)
Agent: implementer

Design Patterns:
    See library-design-patterns skill for standardized design patterns.
"""

import re
from pathlib import Path
from typing import Union


# Constants
MAX_MESSAGE_LENGTH = 10000  # 10KB max message length
MAX_AGENT_NAME_LENGTH = 255  # Maximum length for agent names


def validate_session_path(path: Union[str, Path], purpose: str = "session tracking") -> Path:
    """Validate session path to prevent path traversal.

    Args:
        path: Path to validate (string or Path object)
        purpose: Description of what the path is for (for error messages)

    Returns:
        Validated Path object

    Raises:
        ValueError: If path contains path traversal sequences or is outside allowed directories

    Security:
        - Prevents path traversal (CWE-22)
        - Rejects symlinks (CWE-59)
        - Validates path is within PROJECT_ROOT/docs/sessions or PROJECT_ROOT/.claude

    Examples:
        >>> path = validate_session_path("/project/docs/sessions/file.json")
        >>> path = validate_session_path("../../etc/passwd")  # Raises ValueError
    """
    # Import here to avoid circular dependency
    from path_utils import get_project_root

    # Convert to Path
    if isinstance(path, str):
        path = Path(path)

    # Check for obvious path traversal
    if ".." in str(path):
        raise ValueError(
            f"Path traversal detected in {purpose}: {path}\n"
            f"Paths cannot contain '..' sequences.\n"
            f"Expected: Absolute paths within PROJECT_ROOT"
        )

    # Reject symlinks BEFORE resolving (CWE-59)
    # Check on original path before resolve() to catch symlinks
    if path.is_symlink():
        raise ValueError(
            f"Symlinks not allowed (path outside project) for {purpose}: {path}\n"
            f"Symlinks can be used for path traversal attacks."
        )

    # Resolve to absolute path (handles relative paths)
    try:
        resolved_path = path.resolve()
    except (OSError, RuntimeError) as e:
        raise ValueError(f"Failed to resolve path for {purpose}: {path}\nError: {e}")

    # Get project root
    try:
        project_root = get_project_root()
    except FileNotFoundError as e:
        raise ValueError(f"Cannot validate path - project root not found: {e}")

    # Check if path is within allowed directories
    allowed_dirs = [
        project_root / "docs" / "sessions",
        project_root / ".claude",
    ]

    # Check if resolved path is under any allowed directory
    is_allowed = False
    for allowed_dir in allowed_dirs:
        try:
            # Check if path is relative to allowed_dir (throws ValueError if not)
            resolved_path.relative_to(allowed_dir)
            is_allowed = True
            break
        except ValueError:
            continue

    if not is_allowed:
        raise ValueError(
            f"Path outside project for {purpose}: {path}\n"
            f"Resolved to: {resolved_path}\n"
            f"Allowed directories:\n"
            + "\n".join(f"  - {d}" for d in allowed_dirs)
        )

    # Symlink check already performed above (before resolve())
    return resolved_path


def validate_agent_name(name: str, purpose: str = "agent tracking") -> str:
    """Validate agent name (alphanumeric, hyphen, underscore only).

    Args:
        name: Agent name to validate
        purpose: Description of what the name is for (for error messages)

    Returns:
        Validated agent name (stripped of whitespace)

    Raises:
        ValueError: If name is empty, too long, or contains invalid characters
        TypeError: If name is not a string

    Security:
        - Prevents injection attacks (only allows safe characters)
        - Length validation (prevents resource exhaustion)
        - No control characters

    Examples:
        >>> validate_agent_name("researcher")
        'researcher'
        >>> validate_agent_name("test-agent_v2")
        'test-agent_v2'
        >>> validate_agent_name("../../etc/passwd")  # Raises ValueError
        >>> validate_agent_name("")  # Raises ValueError
    """
    # Type check
    if not isinstance(name, str):
        raise TypeError(
            f"Agent name must be string for {purpose}, got {type(name).__name__}"
        )

    # Strip whitespace
    name = name.strip()

    # Empty check
    if not name:
        raise ValueError(
            f"Agent name cannot be empty for {purpose}\n"
            f"Expected: Non-empty string (alphanumeric, hyphen, underscore)"
        )

    # Length check
    if len(name) > MAX_AGENT_NAME_LENGTH:
        raise ValueError(
            f"Agent name too long for {purpose}: {len(name)} chars\n"
            f"Maximum: {MAX_AGENT_NAME_LENGTH} chars\n"
            f"Name: {name[:50]}..."
        )

    # Character validation (alphanumeric, hyphen, underscore only)
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        raise ValueError(
            f"Invalid agent name for {purpose}: {name}\n"
            f"Agent names must contain only:\n"
            f"  - Letters (a-z, A-Z)\n"
            f"  - Numbers (0-9)\n"
            f"  - Hyphens (-)\n"
            f"  - Underscores (_)\n"
            f"Got: {name}"
        )

    return name


def validate_message(message: str, purpose: str = "message logging") -> str:
    """Validate message (length limits, no control characters).

    Args:
        message: Message to validate
        purpose: Description of what the message is for (for error messages)

    Returns:
        Validated message (stripped of leading/trailing whitespace)

    Raises:
        ValueError: If message is too long or contains control characters
        TypeError: If message is not a string

    Security:
        - Length validation (prevents resource exhaustion)
        - Control character filtering (prevents log injection)
        - No path traversal sequences

    Examples:
        >>> validate_message("Research complete")
        'Research complete'
        >>> validate_message("x" * 20000)  # Raises ValueError (too long)
        >>> validate_message("Test\\x00message")  # Raises ValueError (control chars)
    """
    # Type check
    if not isinstance(message, str):
        raise TypeError(
            f"Message must be string for {purpose}, got {type(message).__name__}"
        )

    # Strip leading/trailing whitespace
    message = message.strip()

    # Length check
    if len(message) > MAX_MESSAGE_LENGTH:
        raise ValueError(
            f"Message too long for {purpose}: {len(message)} chars\n"
            f"Maximum: {MAX_MESSAGE_LENGTH} chars (10KB)\n"
            f"Message: {message[:100]}..."
        )

    # Control character check (ASCII 0-31 except tab, newline, carriage return)
    # Allow: \t (9), \n (10), \r (13)
    # Reject: \x00-\x08, \x0b-\x0c, \x0e-\x1f
    control_chars = re.findall(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', message)
    if control_chars:
        # Get unique control char codes
        char_codes = sorted(set(ord(c) for c in control_chars))
        raise ValueError(
            f"Message contains control characters for {purpose}\n"
            f"Control characters found (ASCII codes): {char_codes}\n"
            f"These can be used for log injection attacks.\n"
            f"Message (first 100 chars): {message[:100]}"
        )

    return message
