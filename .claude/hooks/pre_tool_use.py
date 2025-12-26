#!/usr/bin/env python3
"""
PreToolUse Hook - Simple Standalone Script for Claude Code

Reads tool call from stdin, validates it, outputs decision to stdout.

Input (stdin):
{
  "tool_name": "Bash",
  "tool_input": {"command": "pytest tests/"}
}

Output (stdout):
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",  # or "deny"
    "permissionDecisionReason": "reason"
  }
}

Exit code: 0 (always - let Claude Code process the decision)
"""

import json
import sys
import os
from pathlib import Path

# Add lib directory to path
LIB_DIR = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB_DIR))

# Load .env file if available
def load_env():
    """Load .env file from project root if it exists."""
    env_file = Path(os.getcwd()) / ".env"
    if env_file.exists():
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key not in os.environ:
                            os.environ[key] = value
        except Exception:
            pass  # Silently skip

load_env()

def main():
    """Main entry point."""
    try:
        # Read input from stdin
        input_data = json.load(sys.stdin)

        # Extract tool info
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})

        # Get agent name from environment
        agent_name = os.getenv("CLAUDE_AGENT_NAME", "").strip() or None

        # Import and run validation
        try:
            from auto_approval_engine import should_auto_approve

            approved, reason = should_auto_approve(tool_name, tool_input, agent_name)

            # Determine three-state decision:
            # 1. approved=True → "allow" (auto-approve)
            # 2. blacklisted/security_risk → "deny" (block entirely)
            # 3. not whitelisted → "ask" (fall back to user)
            if approved:
                permission_decision = "allow"
            elif "blacklist" in reason.lower() or "injection" in reason.lower() or "security" in reason.lower() or "circuit breaker" in reason.lower():
                permission_decision = "deny"
            else:
                # Not whitelisted but not dangerous - ask user
                permission_decision = "ask"

        except Exception as e:
            # Graceful degradation - ask user on error (don't block)
            permission_decision = "ask"
            reason = f"Auto-approval error: {e}"

        # Output decision
        decision = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": permission_decision,
                "permissionDecisionReason": reason
            }
        }

        print(json.dumps(decision))

    except Exception as e:
        # Error - ask user (don't block on hook errors)
        decision = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": f"Hook error: {e}"
            }
        }
        print(json.dumps(decision))

    # Always exit 0 - let Claude Code process the decision
    sys.exit(0)

if __name__ == "__main__":
    main()
