#!/usr/bin/env python3
"""
Auto-Approval Consent - First-Run Consent Prompt for MCP Auto-Approval

This module provides interactive consent prompts for MCP auto-approval feature.
It implements opt-in consent design with:

1. First-run interactive prompt (similar to auto_git_workflow.py)
2. Non-interactive detection (CI/CD environments)
3. User state persistence (UserStateManager)
4. Environment variable override (MCP_AUTO_APPROVE)
5. Clear consent documentation and explanation

Usage:
    from auto_approval_consent import prompt_user_for_consent

    # On first run, prompt user
    if prompt_user_for_consent():
        print("User consented to auto-approval")
    else:
        print("User declined auto-approval")

Date: 2025-11-15
Issue: #73 (MCP Auto-Approval for Subagent Tool Calls)
Agent: implementer
Phase: TDD Green (making tests pass)

See error-handling-patterns skill for exception hierarchy and error handling best practices.


Design Patterns:
    See library-design-patterns skill for standardized design patterns.
    See state-management-patterns skill for standardized design patterns.
"""

import os
import sys
from pathlib import Path

# Import user state manager
try:
    from .user_state_manager import UserStateManager, DEFAULT_STATE_FILE
except ImportError:
    # Direct script execution - add lib dir to path
    lib_dir = Path(__file__).parent.resolve()
    sys.path.insert(0, str(lib_dir))
    from user_state_manager import UserStateManager, DEFAULT_STATE_FILE


# Consent preference key
CONSENT_PREFERENCE_KEY = "mcp_auto_approve_enabled"


def render_consent_prompt() -> str:
    """Render first-run consent prompt message.

    Returns:
        Formatted consent prompt string
    """
    return """
╔═══════════════════════════════════════════════════════════════════════════╗
║                   MCP AUTO-APPROVAL - FIRST RUN SETUP                     ║
╚═══════════════════════════════════════════════════════════════════════════╝

The MCP Auto-Approval feature enables automatic execution of certain MCP tool
calls without manual approval in BOTH main conversation and autonomous agents.

WHAT GETS AUTO-APPROVED:
  ✓ Safe read-only commands (pytest, git status, gh issue list, ls, cat, etc.)
  ✓ File operations within your project directory
  ✓ Commands in both main conversation and agent workflows

SECURITY CONTROLS:
  ✓ Whitelist-based command validation (known-safe commands only)
  ✓ Blacklist-based threat blocking (rm -rf, sudo, eval, etc.)
  ✓ Path traversal prevention (CWE-22)
  ✓ Command injection prevention (CWE-78)
  ✓ Comprehensive audit logging (logs/tool_auto_approve_audit.log)
  ✓ Circuit breaker (auto-disables after 10 denials)

YOU REMAIN IN CONTROL:
  • Disable anytime: Set MCP_AUTO_APPROVE=false in .env
  • Subagent-only mode: Set MCP_AUTO_APPROVE=subagent_only
  • Review audit logs: cat logs/tool_auto_approve_audit.log
  • Policy configuration: config/auto_approve_policy.json
  • Manual approval: Always shown for untrusted/blacklisted commands

PRIVACY:
  • No data sent to external services
  • All processing happens locally
  • Audit logs stay on your machine

Would you like to ENABLE MCP auto-approval? (yes/no)

(You can change this later via MCP_AUTO_APPROVE environment variable)
"""


def is_interactive_session() -> bool:
    """Check if running in interactive terminal session.

    Returns:
        True if interactive, False if non-interactive (CI/CD)
    """
    # Check if stdin is a TTY
    if not sys.stdin.isatty():
        return False

    # Check for common CI/CD environment variables
    ci_env_vars = ["CI", "GITHUB_ACTIONS", "GITLAB_CI", "CIRCLECI", "TRAVIS", "JENKINS_HOME"]
    for var in ci_env_vars:
        if os.getenv(var):
            return False

    return True


def parse_user_response(response: str) -> bool:
    """Parse user consent response.

    Args:
        response: User input string

    Returns:
        True for consent, False for decline
    """
    response = response.strip().lower()

    # Positive responses
    if response in ["yes", "y", "true", "1", "enable", "on"]:
        return True

    # Negative responses (default to no)
    return False


def record_consent(consent: bool, state_file: Path = DEFAULT_STATE_FILE) -> None:
    """Record user consent in user state.

    Args:
        consent: User consent decision (True = enabled, False = disabled)
        state_file: Path to user state file
    """
    manager = UserStateManager(state_file)

    # Set preference
    manager.set_preference(CONSENT_PREFERENCE_KEY, consent)

    # Mark first run complete
    manager.record_first_run_complete()

    # Save state
    manager.save()


def prompt_user_for_consent(state_file: Path = DEFAULT_STATE_FILE) -> bool:
    """Prompt user for MCP auto-approval consent on first run.

    This function:
    1. Checks if running in interactive session
    2. Displays consent prompt
    3. Parses user response
    4. Records consent in user state
    5. Returns consent decision

    Args:
        state_file: Path to user state file

    Returns:
        True if user consented, False otherwise
    """
    # Check if interactive session
    if not is_interactive_session():
        # Non-interactive - default to disabled (opt-in design)
        record_consent(False, state_file)
        return False

    # Display consent prompt
    print(render_consent_prompt())

    # Get user response
    try:
        response = input("Enter your choice: ").strip()
    except (EOFError, KeyboardInterrupt):
        # User cancelled - default to no
        print("\n\nCancelled. MCP auto-approval will be DISABLED.")
        record_consent(False, state_file)
        return False

    # Parse response
    consent = parse_user_response(response)

    # Record consent
    record_consent(consent, state_file)

    # Display confirmation
    if consent:
        print("\n✓ MCP auto-approval ENABLED")
        print("  You can disable anytime with: MCP_AUTO_APPROVE=false")
        print("  Audit logs: logs/tool_auto_approve_audit.log")
    else:
        print("\n✓ MCP auto-approval DISABLED")
        print("  You can enable anytime with: MCP_AUTO_APPROVE=true")

    print()

    return consent


def get_auto_approval_mode(state_file: Path = DEFAULT_STATE_FILE) -> str:
    """Get MCP auto-approval mode from environment or user state.

    Modes:
    - "everywhere": Auto-approve in both main conversation and subagents
    - "subagent_only": Auto-approve only in subagent context (legacy behavior)
    - "disabled": Auto-approval disabled

    Priority:
    1. MCP_AUTO_APPROVE environment variable (override)
    2. User state preference (persisted choice)
    3. Default to "disabled" (opt-in design)

    Args:
        state_file: Path to user state file

    Returns:
        Mode string: "everywhere", "subagent_only", or "disabled"
    """
    # Check environment variable override
    env_var = os.getenv("MCP_AUTO_APPROVE", "").strip().lower()
    if env_var in ["true", "1", "yes", "on", "enable", "everywhere"]:
        return "everywhere"
    elif env_var == "subagent_only":
        return "subagent_only"
    elif env_var in ["false", "0", "no", "off", "disable", "disabled"]:
        return "disabled"

    # Check user state preference
    manager = UserStateManager(state_file)

    # If first run, prompt user
    if manager.is_first_run():
        consent = prompt_user_for_consent(state_file)
        # User consent translates to "everywhere" mode (new default)
        return "everywhere" if consent else "disabled"

    # Get saved preference
    consent = manager.get_preference(CONSENT_PREFERENCE_KEY, default=False)

    # Legacy behavior: consent = True → "everywhere" mode
    return "everywhere" if consent else "disabled"


def check_user_consent(state_file: Path = DEFAULT_STATE_FILE) -> bool:
    """Check if user has consented to MCP auto-approval.

    This is a convenience wrapper around get_auto_approval_mode() for
    backwards compatibility.

    Priority:
    1. MCP_AUTO_APPROVE environment variable (override)
    2. User state preference (persisted choice)
    3. Default to False (opt-in design)

    Args:
        state_file: Path to user state file

    Returns:
        True if auto-approval enabled (any mode), False if disabled
    """
    mode = get_auto_approval_mode(state_file)
    return mode in ["everywhere", "subagent_only"]


# Main entry point for testing
if __name__ == "__main__":
    consent = check_user_consent()
    print(f"MCP auto-approval consent: {consent}")
