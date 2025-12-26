#!/usr/bin/env python3
"""
Unified Post Tool Hook - Dispatcher for PostToolUse Lifecycle

Consolidates PostToolUse hooks:
- post_tool_use_error_capture.py (tool error logging)

Hook: PostToolUse (runs after any tool execution)

Environment Variables (opt-in/opt-out):
    CAPTURE_TOOL_ERRORS=true/false (default: true)

Exit codes:
    0: Always (non-blocking hook for informational logging)

Usage:
    # As PostToolUse hook (automatic)
    echo '{"tool_name": "Bash", "tool_result": {"exit_code": 1}}' | python unified_post_tool.py

    # Manual run
    echo '{"tool_name": "Bash", "tool_result": {"exit_code": 0}}' | python unified_post_tool.py
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, Optional


# ============================================================================
# Dynamic Library Discovery
# ============================================================================

def find_lib_dir() -> Optional[Path]:
    """
    Find the lib directory dynamically.

    Searches:
    1. Relative to this file: ../lib
    2. In project root: plugins/autonomous-dev/lib
    3. In global install: ~/.autonomous-dev/lib

    Returns:
        Path to lib directory or None if not found
    """
    candidates = [
        Path(__file__).parent.parent / "lib",  # Relative to hooks/
        Path.cwd() / "plugins" / "autonomous-dev" / "lib",  # Project root
        Path.home() / ".autonomous-dev" / "lib",  # Global install
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


# Add lib to path
LIB_DIR = find_lib_dir()
if LIB_DIR:
    sys.path.insert(0, str(LIB_DIR))

# Optional imports with graceful fallback
try:
    from error_analyzer import write_error_to_registry
    HAS_ERROR_ANALYZER = True
except ImportError:
    HAS_ERROR_ANALYZER = False


# ============================================================================
# Configuration
# ============================================================================

# Check configuration from environment
CAPTURE_TOOL_ERRORS = os.environ.get("CAPTURE_TOOL_ERRORS", "true").lower() == "true"

# Error patterns to detect in stderr
ERROR_PATTERNS = [
    r"error:",
    r"Error:",
    r"ERROR:",
    r"failed",
    r"Failed",
    r"FAILED",
    r"exception",
    r"Exception",
    r"EXCEPTION",
    r"traceback",
    r"Traceback",
]


# ============================================================================
# Tool Error Capture
# ============================================================================

def is_tool_failure(tool_result: Dict) -> bool:
    """
    Determine if a tool result represents a failure.

    Args:
        tool_result: Tool result dictionary

    Returns:
        True if failure detected, False otherwise

    Example:
        >>> is_tool_failure({"exit_code": 1})
        True
        >>> is_tool_failure({"exit_code": 0})
        False
        >>> is_tool_failure({"stderr": "Error: file not found"})
        True
    """
    # Check exit code
    exit_code = tool_result.get("exit_code")
    if exit_code is not None and exit_code != 0:
        return True

    # Check stderr for error patterns
    stderr = tool_result.get("stderr", "")
    if stderr:
        for pattern in ERROR_PATTERNS:
            if re.search(pattern, stderr, re.IGNORECASE):
                return True

    # Check for error field in result
    if tool_result.get("error"):
        return True

    return False


def extract_error_message(tool_result: Dict) -> str:
    """
    Extract error message from tool result.

    Args:
        tool_result: Tool result dictionary

    Returns:
        Error message string (truncated to 1000 chars max)

    Example:
        >>> extract_error_message({"error": "File not found"})
        'File not found'
        >>> extract_error_message({"stderr": "Error: " + "x" * 2000})[:10]
        'Error: xxx'
    """
    # Priority: error field > stderr > stdout truncated
    if tool_result.get("error"):
        return str(tool_result["error"])

    stderr = tool_result.get("stderr", "")
    if stderr:
        return stderr[:1000]  # Cap at 1000 chars

    stdout = tool_result.get("stdout", "")
    if stdout:
        return stdout[:500]  # Less for stdout

    return "Unknown error (no details in tool result)"


def capture_error(tool_name: str, tool_input: Dict, tool_result: Dict) -> bool:
    """
    Capture error to registry.

    Args:
        tool_name: Name of the tool that failed
        tool_input: Tool input parameters
        tool_result: Tool result with error

    Returns:
        True if captured successfully, False otherwise
    """
    if not CAPTURE_TOOL_ERRORS or not HAS_ERROR_ANALYZER:
        return False

    try:
        error_message = extract_error_message(tool_result)
        exit_code = tool_result.get("exit_code")

        # Build context (sanitized)
        context = {
            "tool_input_keys": list(tool_input.keys()) if tool_input else [],
        }

        # Add command for Bash (sanitized - no secrets)
        if tool_name == "Bash" and "command" in tool_input:
            cmd = str(tool_input["command"])
            # Only capture first 100 chars of command
            context["command_preview"] = cmd[:100] + "..." if len(cmd) > 100 else cmd

        return write_error_to_registry(
            tool_name=tool_name,
            exit_code=exit_code,
            error_message=error_message,
            context=context,
        )
    except Exception:
        # Graceful degradation
        return False


# ============================================================================
# Main Hook Entry Point
# ============================================================================

def main() -> int:
    """
    Main hook entry point.

    Reads stdin for hook input, captures errors if detected.

    Returns:
        Always 0 (non-blocking hook)
    """
    # Read input from stdin
    try:
        input_data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        # Invalid input - allow tool to proceed
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse"
            }
        }
        print(json.dumps(output))
        return 0

    # Extract tool info
    tool_name = input_data.get("tool_name", "unknown")
    tool_input = input_data.get("tool_input", {})
    tool_result = input_data.get("tool_result", {})

    # Check if this is a failure
    if is_tool_failure(tool_result):
        # Non-blocking capture - failures here don't interrupt workflow
        try:
            capture_error(tool_name, tool_input, tool_result)
        except Exception:
            pass  # Graceful degradation

    # Always allow tool to proceed (PostToolUse is informational)
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse"
        }
    }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
