#!/usr/bin/env python3
"""
Failure Classifier - Classify /auto-implement failures as transient vs permanent.

Classifies error messages to determine if a failed /auto-implement attempt should
be retried (transient errors like network issues) or marked as failed (permanent
errors like syntax errors).

Key Features:
1. Pattern-based classification (transient vs permanent)
2. Error message sanitization (CWE-117 log injection prevention)
3. Error context extraction for debugging
4. Case-insensitive pattern matching
5. Safe defaults (unknown errors → permanent, no retry)

Classification Strategy:
    TRANSIENT (retriable):
    - Network errors (ConnectionError, NetworkError)
    - Timeout errors (TimeoutError, timeout)
    - API rate limits (RateLimitError, 429, 503)
    - Temporary service failures (502, 504, TemporaryFailure)

    PERMANENT (non-retriable):
    - Syntax errors (SyntaxError, IndentationError)
    - Import errors (ImportError, ModuleNotFoundError)
    - Type errors (TypeError, AttributeError, NameError)
    - Value errors (ValueError, KeyError, IndexError)
    - Logic errors (AssertionError)

    UNKNOWN → PERMANENT (safe default, don't retry)

Usage:
    from failure_classifier import (
        classify_failure,
        is_transient_error,
        is_permanent_error,
        sanitize_error_message,
        extract_error_context,
        FailureType,
    )

    # Classify error
    error_msg = "ConnectionError: Failed to connect to API"
    failure_type = classify_failure(error_msg)
    if failure_type == FailureType.TRANSIENT:
        # Retry the operation
        pass

    # Check specific type
    if is_transient_error(error_msg):
        # Retry
        pass

    # Sanitize before logging
    safe_msg = sanitize_error_message(error_msg)
    log.error(safe_msg)

    # Extract rich context
    context = extract_error_context(error_msg, "Add user authentication")

Security:
- CWE-117: Log injection prevention via sanitization
- Max message length: 1000 chars (prevent resource exhaustion)
- Newline/carriage return removal
- Safe defaults (unknown → permanent)

Date: 2025-11-18
Issue: #89 (Automatic Failure Recovery for /batch-implement)
Agent: implementer
Phase: TDD Green (making tests pass)

See error-handling-patterns skill for exception hierarchy and error handling best practices.
"""

import re
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List


# =============================================================================
# Constants and Enums
# =============================================================================

class FailureType(Enum):
    """Classification of failure types."""
    TRANSIENT = "transient"  # Retriable (network, timeout, rate limit)
    PERMANENT = "permanent"  # Non-retriable (syntax, import, type errors)


# Transient error patterns (case-insensitive regex)
TRANSIENT_ERROR_PATTERNS: List[str] = [
    r"connectionerror",
    r"timeouterror",
    r"ratelimiterror",
    r"networkerror",
    r"httperror.*503",
    r"httperror.*502",
    r"httperror.*504",
    r"httperror.*429",
    r"temporaryfailure",
    r"service.*unavailable",
    r"bad.*gateway",
    r"gateway.*timeout",
    r"too.*many.*requests",
    r"connection.*refused",
    r"connection.*reset",
    r"operation.*timed.*out",
    r"timed.*out",
    r"network.*unreachable",
]

# Permanent error patterns (case-insensitive regex)
PERMANENT_ERROR_PATTERNS: List[str] = [
    r"syntaxerror",
    r"importerror",
    r"typeerror",
    r"nameerror",
    r"attributeerror",
    r"valueerror",
    r"indentationerror",
    r"keyerror",
    r"indexerror",
    r"assertionerror",
    r"modulenotfounderror",
    r"filenotfounderror",
    r"permissionerror",
    r"zerodivisionerror",
    r"notimplementederror",
    r"recursionerror",
]

# Maximum error message length (prevent resource exhaustion)
MAX_ERROR_MESSAGE_LENGTH = 1000


# =============================================================================
# Error Classification Functions
# =============================================================================

def is_transient_error(error_message: Optional[str]) -> bool:
    """
    Check if error message indicates a transient (retriable) error.

    Args:
        error_message: Error message to check

    Returns:
        True if error is transient, False otherwise
    """
    if not error_message:
        return False

    # Case-insensitive pattern matching
    error_lower = error_message.lower()

    for pattern in TRANSIENT_ERROR_PATTERNS:
        if re.search(pattern, error_lower):
            return True

    return False


def is_permanent_error(error_message: Optional[str]) -> bool:
    """
    Check if error message indicates a permanent (non-retriable) error.

    Args:
        error_message: Error message to check

    Returns:
        True if error is permanent, False otherwise
    """
    if not error_message:
        return False

    # Case-insensitive pattern matching
    error_lower = error_message.lower()

    for pattern in PERMANENT_ERROR_PATTERNS:
        if re.search(pattern, error_lower):
            return True

    return False


def classify_failure(error_message: Optional[str]) -> FailureType:
    """
    Classify error message as transient or permanent.

    Classification Rules:
    1. Check transient patterns first (network, timeout, rate limit)
    2. Check permanent patterns (syntax, import, type errors)
    3. Default to PERMANENT for safety (don't retry unknown errors)

    Args:
        error_message: Error message to classify

    Returns:
        FailureType.TRANSIENT or FailureType.PERMANENT

    Examples:
        >>> classify_failure("ConnectionError: Failed to connect")
        FailureType.TRANSIENT

        >>> classify_failure("SyntaxError: invalid syntax")
        FailureType.PERMANENT

        >>> classify_failure("WeirdUnknownError: something happened")
        FailureType.PERMANENT  # Safe default
    """
    # Handle None/empty
    if not error_message:
        return FailureType.PERMANENT  # Safe default

    # Check transient patterns
    if is_transient_error(error_message):
        return FailureType.TRANSIENT

    # Check permanent patterns
    if is_permanent_error(error_message):
        return FailureType.PERMANENT

    # Unknown errors default to permanent (safe default - don't retry)
    return FailureType.PERMANENT


# =============================================================================
# Error Message Sanitization
# =============================================================================

def sanitize_error_message(error_message: Optional[str]) -> str:
    """
    Sanitize error message for safe logging (CWE-117 prevention).

    Security Measures:
    1. Remove newlines (prevent log injection)
    2. Remove carriage returns (prevent log injection)
    3. Truncate to MAX_ERROR_MESSAGE_LENGTH (prevent resource exhaustion)

    Args:
        error_message: Raw error message

    Returns:
        Sanitized error message safe for logging

    Examples:
        >>> sanitize_error_message("Error\\nFAKE LOG: Admin access")
        "Error FAKE LOG: Admin access"

        >>> sanitize_error_message("Error: " + "X" * 10000)
        "Error: XXX...[truncated]"
    """
    if not error_message:
        return ""

    # Remove newlines and carriage returns (CWE-117 log injection)
    sanitized = error_message.replace("\n", " ").replace("\r", " ")

    # Truncate long messages (prevent resource exhaustion)
    if len(sanitized) > MAX_ERROR_MESSAGE_LENGTH:
        sanitized = sanitized[:MAX_ERROR_MESSAGE_LENGTH - 14] + "...[truncated]"

    return sanitized


def sanitize_feature_name(feature_name: str) -> str:
    """
    Sanitize feature name for safe storage and logging.

    Security Measures:
    1. Remove newlines (prevent log injection - CWE-117)
    2. Remove carriage returns (prevent log injection - CWE-117)
    3. Remove path traversal sequences (prevent CWE-22)
    4. Truncate to reasonable length (prevent resource exhaustion)

    Args:
        feature_name: Raw feature name

    Returns:
        Sanitized feature name safe for storage and logging

    Examples:
        >>> sanitize_feature_name("Add auth\\nFAKE LOG: Admin access")
        "Add auth FAKE LOG: Admin access"

        >>> sanitize_feature_name("../../etc/passwd")
        "etc/passwd [sanitized]"

        >>> sanitize_feature_name("Normal feature")
        "Normal feature"
    """
    if not feature_name:
        return ""

    # Remove newlines and carriage returns (CWE-117 log injection)
    sanitized = feature_name.replace("\n", " ").replace("\r", " ")

    # Remove path traversal sequences (CWE-22)
    if ".." in sanitized:
        # Remove ../ and ..\ sequences
        sanitized = sanitized.replace("../", "").replace("..\\", "")
        # Add marker that this was sanitized
        if "sanitized" not in sanitized.lower():
            sanitized += " [sanitized]"

    # Truncate long names (prevent resource exhaustion)
    MAX_FEATURE_NAME_LENGTH = 200
    if len(sanitized) > MAX_FEATURE_NAME_LENGTH:
        sanitized = sanitized[:MAX_FEATURE_NAME_LENGTH - 14] + "...[truncated]"

    return sanitized


# =============================================================================
# Error Context Extraction
# =============================================================================

def extract_error_context(
    error_message: Optional[str],
    feature_name: str,
) -> Dict[str, Any]:
    """
    Extract rich error context for debugging and logging.

    Context includes:
    - error_type: Type of error (e.g., "SyntaxError")
    - error_message: Sanitized error message
    - feature_name: Feature being processed
    - timestamp: When error occurred
    - failure_type: Classification (transient/permanent)

    Args:
        error_message: Raw error message
        feature_name: Name of feature being processed

    Returns:
        Dictionary with error context containing:
        - error_type (str): Error class name
        - error_message (str): Sanitized message
        - feature_name (str): Feature being processed
        - timestamp (str): ISO 8601 timestamp
        - failure_type (str): "transient" or "permanent"

    Examples:
        >>> context = extract_error_context(
        ...     "SyntaxError: invalid syntax",
        ...     "Add user authentication"
        ... )
        >>> context["error_type"]
        "SyntaxError"
        >>> context["failure_type"]
        "permanent"
    """
    # Sanitize error message
    sanitized_message = sanitize_error_message(error_message)

    # Extract error type (first word before colon)
    error_type = "Unknown"
    if error_message and ":" in error_message:
        error_type = error_message.split(":")[0].strip()
    elif error_message:
        # Try to extract error type from class name
        match = re.match(r"(\w+Error)", error_message)
        if match:
            error_type = match.group(1)

    # Classify failure
    failure_type = classify_failure(error_message)

    # Build context
    context = {
        "error_type": error_type,
        "error_message": sanitized_message,
        "feature_name": feature_name,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "failure_type": failure_type.value,
    }

    return context


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    "FailureType",
    "classify_failure",
    "is_transient_error",
    "is_permanent_error",
    "sanitize_error_message",
    "extract_error_context",
    "TRANSIENT_ERROR_PATTERNS",
    "PERMANENT_ERROR_PATTERNS",
]
