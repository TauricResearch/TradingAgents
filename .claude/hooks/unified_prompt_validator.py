#!/usr/bin/env python3
"""
Unified Prompt Validator Hook - Dispatcher for UserPromptSubmit Checks

Consolidates UserPromptSubmit hooks:
- detect_feature_request.py (workflow bypass detection - BLOCKING)
- quality_workflow_nudge (implementation intent - NON-BLOCKING)

Hook: UserPromptSubmit (runs when user submits a prompt)

Environment Variables (opt-in/opt-out):
    ENFORCE_WORKFLOW=true/false (default: true) - Controls bypass blocking
    QUALITY_NUDGE_ENABLED=true/false (default: true) - Controls quality reminders

Exit codes:
    0: Pass - No issues detected OR nudge shown (non-blocking)
    2: Block - Workflow bypass detected

Usage:
    # As UserPromptSubmit hook (automatic)
    echo '{"userPrompt": "gh issue create"}' | python unified_prompt_validator.py

    # Test quality nudge
    echo '{"userPrompt": "implement auth feature"}' | python unified_prompt_validator.py

    # Disable nudges
    echo '{"userPrompt": "implement auth"}' | QUALITY_NUDGE_ENABLED=false python unified_prompt_validator.py
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


# ============================================================================
# Configuration
# ============================================================================

# Check configuration from environment
ENFORCE_WORKFLOW = os.environ.get("ENFORCE_WORKFLOW", "true").lower() == "true"
QUALITY_NUDGE_ENABLED = os.environ.get("QUALITY_NUDGE_ENABLED", "true").lower() == "true"


# ============================================================================
# Workflow Bypass Detection
# ============================================================================

def is_bypass_attempt(user_input: str) -> bool:
    """
    Detect if user input is attempting to bypass proper workflow.

    Triggers on patterns that try to skip /create-issue pipeline:
    - "gh issue create" (direct gh CLI usage)
    - "skip /create-issue" / "bypass /create-issue" (explicit bypass)

    Does NOT trigger on:
    - "/create-issue" command itself (that's the CORRECT workflow)
    - Feature requests like "implement X" (moved to persuasion, not enforcement)

    Args:
        user_input: User prompt text

    Returns:
        True if bypass attempt detected, False otherwise

    Example:
        >>> is_bypass_attempt("gh issue create --title 'bug'")
        True
        >>> is_bypass_attempt("/create-issue Add JWT auth")
        False
        >>> is_bypass_attempt("skip /create-issue and implement it")
        True
    """
    # Convert to lowercase for matching
    text = user_input.lower()

    # Explicit bypass language (skip/bypass) - check FIRST
    # "skip /create-issue" or "bypass /create-issue" are ALWAYS bypass attempts
    if re.search(r'\b(skip|bypass)\s+/?(create-issue|auto-implement)', text, re.IGNORECASE):
        return True

    # Check for legitimate /create-issue command (without skip/bypass)
    # This is the CORRECT workflow and should not be blocked
    if re.search(r'/create[\s-]issue', text, re.IGNORECASE):
        return False

    # Direct gh CLI usage to create issues (bypasses research, validation)
    if re.search(r'\bgh\s+issue\s+create\b', text, re.IGNORECASE):
        return True

    return False


def get_bypass_message(user_input: str) -> str:
    """
    Generate blocking message when bypass attempt is detected.

    Args:
        user_input: User prompt that triggered bypass detection

    Returns:
        Formatted message explaining why bypass is blocked and correct workflow
    """
    preview = user_input[:100] + '...' if len(user_input) > 100 else user_input

    return f"""
WORKFLOW BYPASS BLOCKED

Detected Pattern: {preview}

You MUST use the correct workflow:
  /create-issue "description"

Why This Is Blocked:
- Direct issue creation bypasses duplicate detection
- Skips research integration (cached for /auto-implement)
- No PROJECT.md alignment validation

Correct Workflow:
1. Run: /create-issue "feature description"
2. Command validates + researches + creates issue
3. Then use: /auto-implement #<issue-number>

Set ENFORCE_WORKFLOW=false in .env to disable this check.
"""


def check_workflow_bypass(user_input: str) -> Dict[str, any]:
    """
    Check for workflow bypass attempts.

    Args:
        user_input: User prompt text

    Returns:
        Dict with 'passed' (bool) and 'message' (str)
    """
    if not ENFORCE_WORKFLOW:
        return {'passed': True, 'message': ''}

    if is_bypass_attempt(user_input):
        return {
            'passed': False,
            'message': get_bypass_message(user_input),
        }

    return {'passed': True, 'message': ''}


# ============================================================================
# Quality Workflow Nudge Detection (Issue #153)
# ============================================================================

# Implementation intent patterns - detect phrases indicating new code creation
IMPLEMENTATION_PATTERNS = [
    # Direct implementation verbs with feature/component targets
    # Uses (?:\w+\s+)* to match zero or more words before target (e.g., "JWT authentication feature")
    r'\b(implement|create|add|build|write|develop)\s+(?:a\s+)?(?:new\s+)?'
    r'(?:\w+\s+)*(feature|function|class|method|module|component|api|endpoint|'
    r'service|handler|controller|model|interface|code|authentication|system|'
    r'logic|workflow|validation|integration)',
    # Feature addition patterns (direct like "add support" or with description)
    r'\b(add|implement)\s+(?:.*\s+)?(support|functionality|capability)\b',
    # System modification patterns
    r'\b(modify|update|change|refactor)\s+.*\s+to\s+(add|support|implement)\b',
]

# Quality nudge message template
QUALITY_NUDGE_MESSAGE = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 Quality Workflow Reminder
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

It looks like you're about to implement a feature.

Before implementing directly, consider the quality workflow:

1. Check PROJECT.md alignment
   Does this feature serve project GOALS and respect CONSTRAINTS?

2. Search codebase for existing patterns
   Use Grep/Glob to find similar implementations first.

3. Consider /auto-implement (recommended)
   Research → Plan → TDD → Implement → Review → Security → Docs

Why /auto-implement works better (production data):
  - Bug rate: 23% (direct) vs 4% (pipeline)
  - Security issues: 12% (direct) vs 0.3% (pipeline)
  - Test coverage: 43% (direct) vs 94% (pipeline)

This is a reminder, not a requirement. Proceed if you prefer direct implementation.

To disable: Set QUALITY_NUDGE_ENABLED=false in .env
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


def is_implementation_intent(user_input: str) -> bool:
    """
    Check if user input indicates implementation intent.

    Uses regex patterns to detect phrases like:
    - "implement X feature"
    - "add Y function"
    - "create Z class"
    - "build new component"

    Does NOT trigger for:
    - Questions ("How do I implement...?")
    - Documentation updates
    - Bug fixes
    - Reading/searching operations
    - Already using /auto-implement or /create-issue

    Args:
        user_input: User prompt text

    Returns:
        True if implementation intent detected, False otherwise

    Example:
        >>> is_implementation_intent("implement JWT authentication feature")
        True
        >>> is_implementation_intent("How do I implement this?")
        False
        >>> is_implementation_intent("/auto-implement #123")
        False
    """
    if not user_input or not user_input.strip():
        return False

    text = user_input.lower().strip()

    # Skip if already using quality commands
    if re.search(r'/auto-implement|/create-issue', text, re.IGNORECASE):
        return False

    # Skip questions (end with ?)
    if text.rstrip().endswith('?'):
        return False

    # Check implementation patterns
    for pattern in IMPLEMENTATION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True

    return False


def detect_implementation_intent(user_input: str) -> Dict[str, any]:
    """
    Detect implementation intent and provide quality workflow nudge.

    This is a NON-BLOCKING check. It never prevents the prompt from
    being processed. Instead, it provides a helpful reminder about
    quality workflows.

    Args:
        user_input: User prompt text

    Returns:
        Dict with 'nudge' (bool) and 'message' (str)
    """
    if not QUALITY_NUDGE_ENABLED:
        return {'nudge': False, 'message': ''}

    if is_implementation_intent(user_input):
        return {
            'nudge': True,
            'message': QUALITY_NUDGE_MESSAGE,
        }

    return {'nudge': False, 'message': ''}


# ============================================================================
# Main Hook Entry Point
# ============================================================================

def main() -> int:
    """
    Main hook entry point.

    Reads stdin for hook input, dispatches checks, outputs result.
    Handles both blocking checks (workflow bypass) and non-blocking
    nudges (quality workflow reminders).

    Returns:
        0 if all checks pass or nudge detected (non-blocking)
        2 if workflow bypass detected (blocking)
    """
    # Read input from stdin
    try:
        input_data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        # Invalid input - allow to proceed
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit"
            }
        }
        print(json.dumps(output))
        return 0

    # Extract user prompt
    user_prompt = input_data.get('userPrompt', '')

    # Check for workflow bypass (BLOCKING)
    workflow_check = check_workflow_bypass(user_prompt)

    if not workflow_check['passed']:
        # Block: Print error message to stderr and return error code
        print(workflow_check['message'], file=sys.stderr)
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "error": workflow_check['message']
            }
        }
        print(json.dumps(output))
        return 2

    # Check for implementation intent (NON-BLOCKING)
    intent_check = detect_implementation_intent(user_prompt)

    if intent_check['nudge']:
        # Nudge: Print reminder to stderr but still allow (exit 0)
        print(intent_check['message'], file=sys.stderr)
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "nudge": intent_check['message']
            }
        }
        print(json.dumps(output))
        return 0

    # Pass: All checks succeeded, no nudges
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit"
        }
    }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
