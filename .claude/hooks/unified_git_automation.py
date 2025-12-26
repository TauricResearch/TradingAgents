#!/usr/bin/env python3
"""
Unified Git Automation Hook - Dispatcher for SubagentStop Git Operations

Consolidates SubagentStop git automation hooks:
- auto_git_workflow.py (commit, push, PR creation)

Hook: SubagentStop (runs when doc-master completes)
Matcher: doc-master (last agent in parallel validation phase)

Environment Variables (opt-in/opt-out):
    AUTO_GIT_ENABLED=true/false (default: false)
    AUTO_GIT_PUSH=true/false (default: false)
    AUTO_GIT_PR=true/false (default: false)
    SESSION_FILE=path (default: latest in docs/sessions/)

Environment Variables (provided by Claude Code):
    CLAUDE_AGENT_NAME - Name of the subagent that completed
    CLAUDE_AGENT_STATUS - Status: "success" or "error"

Exit codes:
    0: Always (non-blocking hook - failures are logged but don't block)

Usage:
    # As SubagentStop hook (automatic)
    CLAUDE_AGENT_NAME=doc-master AUTO_GIT_ENABLED=true python unified_git_automation.py
"""

import json
import os
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
    from security_utils import validate_path, audit_log
    HAS_SECURITY_UTILS = True
except ImportError:
    HAS_SECURITY_UTILS = False
    def audit_log(event_type: str, status: str, context: Dict) -> None:
        pass

try:
    from auto_implement_git_integration import execute_step8_git_operations
    HAS_GIT_INTEGRATION = True
except ImportError:
    HAS_GIT_INTEGRATION = False


# ============================================================================
# Configuration
# ============================================================================

def parse_bool(value: str) -> bool:
    """Parse boolean from various formats (case-insensitive)."""
    return value.lower() in ('true', 'yes', '1')


# Check configuration from environment
AUTO_GIT_ENABLED = parse_bool(os.environ.get('AUTO_GIT_ENABLED', 'false'))
AUTO_GIT_PUSH = parse_bool(os.environ.get('AUTO_GIT_PUSH', 'false')) if AUTO_GIT_ENABLED else False
AUTO_GIT_PR = parse_bool(os.environ.get('AUTO_GIT_PR', 'false')) if AUTO_GIT_ENABLED else False


# ============================================================================
# Git Workflow Trigger
# ============================================================================

def should_trigger_git_workflow(agent_name: Optional[str]) -> bool:
    """
    Check if git workflow should trigger based on agent name.

    Only triggers for doc-master (last agent in parallel validation phase).

    Args:
        agent_name: Name of agent that just completed

    Returns:
        True if workflow should trigger, False otherwise
    """
    if not agent_name:
        return False

    # Trigger for doc-master (last agent in parallel validation phase)
    return agent_name == 'doc-master'


def check_git_workflow_consent() -> Dict[str, bool]:
    """
    Check user consent for git operations via environment variables.

    Returns:
        Dict with consent flags:
        {
            'git_enabled': bool,      # Master switch
            'push_enabled': bool,     # Push consent
            'pr_enabled': bool,       # PR consent
            'all_enabled': bool       # All three enabled
        }
    """
    all_enabled = AUTO_GIT_ENABLED and AUTO_GIT_PUSH and AUTO_GIT_PR

    return {
        'git_enabled': AUTO_GIT_ENABLED,
        'push_enabled': AUTO_GIT_PUSH,
        'pr_enabled': AUTO_GIT_PR,
        'all_enabled': all_enabled,
    }


def get_session_file_path() -> Optional[Path]:
    """
    Get path to session file for workflow metadata.

    Checks SESSION_FILE environment variable first, otherwise finds latest
    session file in docs/sessions/ directory.

    Returns:
        Path to session file or None if not found/invalid
    """
    session_file_env = os.environ.get('SESSION_FILE')

    if session_file_env:
        # Use explicit session file (validate security if available)
        session_path = Path(session_file_env).resolve()

        if HAS_SECURITY_UTILS:
            try:
                validated_path = validate_path(
                    session_path,
                    purpose='session file reading',
                    allow_missing=True,
                )
                return validated_path
            except ValueError as e:
                audit_log(
                    event_type='session_file_path_validation',
                    status='rejected',
                    context={'session_file': str(session_path), 'error': str(e)},
                )
                return None
        else:
            return session_path if session_path.exists() else None

    # Find latest session file
    session_dir = Path("docs/sessions")
    if not session_dir.exists():
        return None

    session_files = list(session_dir.glob("*-pipeline.json"))
    if not session_files:
        return None

    return sorted(session_files)[-1]


def execute_git_workflow(session_file: Path, consent: Dict[str, bool]) -> bool:
    """
    Execute git workflow operations.

    Args:
        session_file: Path to session file with workflow metadata
        consent: Consent flags for git operations

    Returns:
        True if executed successfully, False otherwise
    """
    if not HAS_GIT_INTEGRATION:
        return False

    try:
        # Execute git operations via library
        result = execute_step8_git_operations(
            session_file=session_file,
            git_enabled=consent['git_enabled'],
            push_enabled=consent['push_enabled'],
            pr_enabled=consent['pr_enabled'],
        )
        return result.get('success', False)
    except Exception as e:
        if HAS_SECURITY_UTILS:
            audit_log(
                event_type='git_workflow_execution',
                status='error',
                context={'error': str(e)},
            )
        return False


# ============================================================================
# Main Hook Entry Point
# ============================================================================

def main() -> int:
    """
    Main hook entry point.

    Reads agent info from environment, executes git workflow if appropriate.

    Returns:
        Always 0 (non-blocking hook - failures logged but don't block)
    """
    # Get agent info from environment
    agent_name = os.environ.get("CLAUDE_AGENT_NAME")
    agent_status = os.environ.get("CLAUDE_AGENT_STATUS", "success")

    # Check if workflow should trigger
    if not should_trigger_git_workflow(agent_name):
        # Not the right agent - skip
        output = {
            "hookSpecificOutput": {
                "hookEventName": "SubagentStop"
            }
        }
        print(json.dumps(output))
        return 0

    # Only trigger on success
    if agent_status != "success":
        output = {
            "hookSpecificOutput": {
                "hookEventName": "SubagentStop"
            }
        }
        print(json.dumps(output))
        return 0

    # Check consent
    consent = check_git_workflow_consent()
    if not consent['git_enabled']:
        # Git automation disabled
        output = {
            "hookSpecificOutput": {
                "hookEventName": "SubagentStop"
            }
        }
        print(json.dumps(output))
        return 0

    # Get session file
    session_file = get_session_file_path()
    if not session_file:
        # No session file - can't execute workflow
        output = {
            "hookSpecificOutput": {
                "hookEventName": "SubagentStop"
            }
        }
        print(json.dumps(output))
        return 0

    # Execute git workflow (non-blocking - errors logged but don't fail hook)
    try:
        execute_git_workflow(session_file, consent)
    except Exception:
        # Graceful degradation
        pass

    # Always succeed (non-blocking hook)
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SubagentStop"
        }
    }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
