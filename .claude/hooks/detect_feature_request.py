#!/usr/bin/env python3
"""
Feature Request Detection Hook - Auto-Orchestration Engine

This hook runs on UserPromptSubmit to detect when the user is requesting
a feature implementation via natural language ("vibe coding").

When detected, it automatically invokes the orchestrator agent which:
1. Checks PROJECT.md alignment FIRST
2. Blocks work if feature not in SCOPE
3. Triggers full agent pipeline if aligned

Relevant Skills:
- project-alignment-validation: Semantic validation approach for request understanding

Usage:
    Add to .claude/settings.local.json:
    {
      "hooks": {
        "UserPromptSubmit": [
          {
            "type": "command",
            "command": "python .claude/hooks/detect_feature_request.py"
          }
        ]
      }
    }

Exit codes:
- 0: Feature request detected (orchestrator should be invoked)
- 1: Not a feature request (proceed normally)
"""

import sys
import re


def is_feature_request(user_input: str) -> bool:
    """
    Detect if user input is requesting feature implementation.

    Triggers on keywords like:
    - "implement X"
    - "add X"
    - "create X"
    - "build X"
    - "develop X"
    - "write X"
    - "make X"

    Returns:
        True if feature request detected, False otherwise
    """
    # Convert to lowercase for matching
    text = user_input.lower()

    # Feature request patterns
    patterns = [
        # Direct implementation requests
        r'\b(implement|add|create|build|develop|write|make)\s+',

        # "I want/need to..."
        r'\b(i\s+want|i\s+need|i\'d\s+like)\s+to\s+(implement|add|create|build)',

        # "Can you implement/add..."
        r'\b(can\s+you|could\s+you|please)\s+(implement|add|create|build|write|make)',

        # "Let's implement/add..."
        r'\b(let\'s|lets)\s+(implement|add|create|build|write|make)',

        # Feature-specific keywords
        r'\b(new\s+feature|feature\s+request)',
        r'\b(authentication|authorization|user\s+management)',
        r'\b(api\s+endpoint|rest\s+api|graphql)',
        r'\b(database|model|schema)',
        r'\b(ui\s+component|frontend|backend)',
    ]

    # Check if any pattern matches
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True

    # Exclude questions and queries (these shouldn't trigger)
    exclusion_patterns = [
        r'^\s*(what|why|how|when|where|who|explain|describe|tell\s+me)',
        r'^\s*(show|display|list|find|search)',
        r'\?$',  # Ends with question mark
    ]

    for pattern in exclusion_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return False

    return False


def get_orchestrator_message(user_input: str) -> str:
    """
    Generate message to display when feature request is detected.

    Returns:
        Formatted message reminding Claude to invoke /auto-implement
    """
    return f"""
🎯 **STRICT MODE: Feature Request Detected**

**User Request**: {user_input[:100]}{'...' if len(user_input) > 100 else ''}

**ACTION REQUIRED**: You MUST run /auto-implement command now:
  /auto-implement "{user_input[:80]}{'...' if len(user_input) > 80 else ''}"

**Why**: Strict mode requires orchestrator to validate PROJECT.md alignment
before any implementation work begins. This ensures:
- ✅ Feature aligns with PROJECT.md (GOALS, SCOPE, CONSTRAINTS)
- ✅ Full agent pipeline executes (researcher → planner → test-master → implementer → reviewer → security-auditor → doc-master)
- ✅ SDLC best practices enforced automatically
- ✅ Background validation via PreCommit hooks

**DO NOT respond conversationally** - Run the command above to trigger the autonomous workflow.
"""


def should_invoke_orchestrator() -> bool:
    """
    Determine if orchestrator should be invoked based on user input.

    Reads from stdin (user's message) and applies feature detection.

    Returns:
        True if orchestrator should be invoked
    """
    # Read user input from stdin
    user_input = sys.stdin.read().strip()

    # Skip if empty
    if not user_input:
        return False

    # Check if this is a feature request
    if is_feature_request(user_input):
        # Print orchestrator message to stderr (visible to user)
        print(get_orchestrator_message(user_input), file=sys.stderr)
        return True

    return False


def main() -> int:
    """
    Main entry point for feature detection hook.

    Returns:
        0 if orchestrator should be invoked
        1 if not a feature request
    """
    try:
        if should_invoke_orchestrator():
            # Feature request detected - orchestrator should handle
            return 0
        else:
            # Not a feature request - proceed normally
            return 1
    except Exception as e:
        # On error, don't block - proceed normally
        print(f"Warning: Feature detection error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
