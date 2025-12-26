#!/usr/bin/env python3
"""
GitHub Issue Closer - Auto-close issues after /auto-implement workflow.

Provides functionality to automatically close GitHub issues after successful
autonomous feature implementation. Uses gh CLI for GitHub operations with
comprehensive security validation.

Security Features:
- CWE-20: Input validation (positive integers, max 999999)
- CWE-78: Command injection prevention (subprocess list args, shell=False)
- CWE-117: Log injection prevention (sanitize newlines, control characters)
- Audit logging for all gh CLI operations

Key Functions:
1. extract_issue_number() - Extract issue number from command args
2. validate_issue_state() - Check if issue exists and is open
3. generate_close_summary() - Format markdown summary for closing
4. close_github_issue() - Close issue via gh CLI
5. prompt_user_consent() - Interactive consent prompt

Workflow:
    1. Extract issue number from command args (patterns: "issue #8", "#8", "Issue 8")
    2. Prompt user for consent (interactive)
    3. Validate issue exists and is open (validate_issue_state)
    4. Generate close summary (generate_close_summary)
    5. Close issue with summary (close_github_issue)
    6. Graceful degradation on any failure (non-blocking)

Usage:
    from github_issue_closer import (
        extract_issue_number,
        validate_issue_state,
        generate_close_summary,
        close_github_issue,
        prompt_user_consent,
    )

    # Extract issue number
    issue_num = extract_issue_number("implement issue #8")
    # Returns: 8

    # Prompt for consent
    if not prompt_user_consent(issue_num):
        return  # User declined

    # Validate issue state
    validate_issue_state(issue_num)  # Raises if not open

    # Generate summary
    metadata = {
        'pr_url': 'https://github.com/user/repo/pull/42',
        'commit_hash': 'abc123',
        'files_changed': ['file1.py', 'file2.py'],
        'agents_passed': ['researcher', 'planner', 'test-master',
                          'implementer', 'reviewer', 'security-auditor', 'doc-master'],
    }
    summary = generate_close_summary(issue_num, metadata)

    # Close issue
    close_github_issue(issue_num, summary)

Date: 2025-11-18
Issue: #91 (Auto-close GitHub issues after /auto-implement)
Agent: implementer
Phase: TDD Green (making tests pass)

Design Patterns:
    See library-design-patterns skill for standardized design patterns.
    See api-integration-patterns skill for standardized design patterns.
See error-handling-patterns skill for exception hierarchy and error handling best practices.
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from subprocess import CalledProcessError, TimeoutExpired

# Import security utilities for audit logging
sys.path.insert(0, str(Path(__file__).parent))
from security_utils import audit_log


# =============================================================================
# EXCEPTIONS
# =============================================================================


class GitHubAPIError(Exception):
    """Base exception for GitHub API errors."""
    pass


class IssueNotFoundError(GitHubAPIError):
    """Exception raised when GitHub issue is not found."""
    pass


class IssueAlreadyClosedError(GitHubAPIError):
    """Exception raised when GitHub issue is already closed."""
    pass


# =============================================================================
# CONSTANTS
# =============================================================================


# Maximum issue number (prevent resource exhaustion)
MAX_ISSUE_NUMBER = 999999

# Subprocess timeout (seconds)
GH_CLI_TIMEOUT = 10


# =============================================================================
# CORE FUNCTIONS
# =============================================================================


def extract_issue_number(feature_request: str) -> Optional[int]:
    """
    Extract issue number from feature request command args.

    Recognizes patterns:
    - "issue #8", "#8", "Issue 8" (standard)
    - "GH-42" (GitHub shorthand)
    - "closes #8", "fixes #8", "resolves #8" (conventional commits)
    - Case-insensitive
    - Uses first occurrence if multiple mentions

    Args:
        feature_request: Command args from /auto-implement

    Returns:
        Issue number as integer, or None if no issue number found

    Examples:
        >>> extract_issue_number("implement issue #8")
        8
        >>> extract_issue_number("implement #8 feature")
        8
        >>> extract_issue_number("Issue 8 implementation")
        8
        >>> extract_issue_number("GH-42 implementation")
        42
        >>> extract_issue_number("fixes #123 - login bug")
        123
        >>> extract_issue_number("implement new feature")
        None
    """
    if not feature_request:
        return None

    # Patterns ordered by specificity (most specific first)
    # Case-insensitive, captures first occurrence
    patterns = [
        r'(?:closes?|fix(?:es)?|resolves?)\s*#(\d+)',  # "closes #8", "fixes #8", "resolves #8"
        r'GH-(\d+)',                                     # "GH-42" (GitHub shorthand)
        r'issue\s*#(\d+)',                              # "issue #8"
        r'#(\d+)',                                       # "#8" (standalone)
        r'issue\s+(\d+)',                               # "Issue 8" (no hash)
    ]

    for pattern in patterns:
        match = re.search(pattern, feature_request, re.IGNORECASE)
        if match:
            return int(match.group(1))

    return None


def validate_issue_state(issue_number: int) -> bool:
    """
    Validate issue exists and is open via gh CLI.

    Args:
        issue_number: GitHub issue number

    Returns:
        True if issue exists and is open

    Raises:
        ValueError: If issue number is invalid (CWE-20)
        IssueNotFoundError: If issue doesn't exist
        IssueAlreadyClosedError: If issue is already closed
        GitHubAPIError: If gh CLI fails (timeout, network)

    Security:
        - CWE-20: Validates issue number is positive integer (1-999999)
        - CWE-78: Uses subprocess list args (never shell=True)
        - Audit logging: Logs all gh CLI operations

    Examples:
        >>> validate_issue_state(8)
        True
        >>> validate_issue_state(-1)
        ValueError: Issue number must be positive
        >>> validate_issue_state(999)
        IssueNotFoundError: Issue #999 not found
    """
    # CWE-20: Input validation - positive integers only
    if not isinstance(issue_number, int) or issue_number <= 0:
        raise ValueError(f"Issue number must be positive integer (got: {issue_number})")

    if issue_number > MAX_ISSUE_NUMBER:
        raise ValueError(f"Issue number too large (max: {MAX_ISSUE_NUMBER})")

    # CWE-78: Command injection prevention - list args, shell=False
    cmd = ['gh', 'issue', 'view', str(issue_number), '--json', 'state,title,number']

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=GH_CLI_TIMEOUT,
            check=True,
        )

        # Parse JSON response
        data = json.loads(result.stdout)

        # Check state
        if data['state'] == 'closed':
            audit_log(
                event_type='validate_issue_state',
                status='already_closed',
                context={
                    'issue_number': issue_number,
                    'title': data.get('title', ''),
                },
            )
            raise IssueAlreadyClosedError(f"Issue #{issue_number} is already closed")

        # Success
        audit_log(
            event_type='validate_issue_state',
            status='success',
            context={
                'issue_number': issue_number,
                'state': data['state'],
                'title': data.get('title', ''),
            },
        )
        return True

    except TimeoutExpired as e:
        audit_log(
            event_type='validate_issue_state',
            status='timeout',
            context={
                'issue_number': issue_number,
                'timeout': GH_CLI_TIMEOUT,
            },
        )
        raise GitHubAPIError(f"Timeout validating issue #{issue_number}") from e

    except CalledProcessError as e:
        # Check if issue not found
        if 'not found' in e.stderr.lower():
            audit_log(
                event_type='validate_issue_state',
                status='not_found',
                context={
                    'issue_number': issue_number,
                    'stderr': e.stderr,
                },
            )
            raise IssueNotFoundError(f"Issue #{issue_number} not found") from e

        # Other gh CLI errors
        audit_log(
            event_type='validate_issue_state',
            status='failed',
            context={
                'issue_number': issue_number,
                'stderr': e.stderr,
            },
        )
        raise GitHubAPIError(f"Failed to validate issue #{issue_number}: {e.stderr}") from e


def sanitize_output(text: str) -> str:
    """
    Sanitize text for log/comment output.

    Security: CWE-117 - Log injection prevention
    Removes control characters and replaces newlines with spaces.

    Args:
        text: Text to sanitize

    Returns:
        Sanitized text with control chars removed

    Examples:
        >>> sanitize_output("file\\nwith\\nnewlines.py")
        'file with newlines.py'
        >>> sanitize_output("file\\x00control.py")
        'filecontrol.py'
    """
    # Remove control characters (CWE-117)
    sanitized = ''.join(char if ord(char) >= 32 or char == '\n' else '' for char in text)

    # Replace single newlines with spaces (preserve paragraph structure)
    sanitized = re.sub(r'(?<!\n)\n(?!\n)', ' ', sanitized)

    return sanitized


def generate_close_summary(issue_number: int, workflow_metadata: Dict[str, Any]) -> str:
    """
    Generate markdown summary for closing issue.

    Args:
        issue_number: GitHub issue number
        workflow_metadata: Workflow metadata from auto_git_workflow hook
            Expected keys:
            - pr_url (optional): Pull request URL
            - commit_hash: Git commit hash
            - files_changed: List of changed file paths
            - agents_passed (optional): List of agent names

    Returns:
        Markdown-formatted summary string

    Security:
        - CWE-117: Sanitizes file names and metadata (remove control chars)

    Examples:
        >>> metadata = {
        ...     'pr_url': 'https://github.com/user/repo/pull/42',
        ...     'commit_hash': 'abc123',
        ...     'files_changed': ['file1.py', 'file2.py'],
        ...     'agents_passed': ['researcher', 'planner', 'test-master',
        ...                       'implementer', 'reviewer', 'security-auditor', 'doc-master'],
        ... }
        >>> summary = generate_close_summary(8, metadata)
        >>> 'Completed via /auto-implement' in summary
        True
        >>> 'All 7 agents passed' in summary
        True
    """
    # Extract metadata
    pr_url = workflow_metadata.get('pr_url')
    commit_hash = workflow_metadata.get('commit_hash', 'N/A')
    files_changed = workflow_metadata.get('files_changed', [])
    agents_passed = workflow_metadata.get('agents_passed', [])

    # Sanitize commit hash (CWE-117)
    commit_hash = sanitize_output(commit_hash)

    # Build summary sections (using single newlines to prevent log injection - CWE-117)
    summary_lines = [
        f"## Issue #{issue_number} Completed via /auto-implement",
        "### Workflow Status",
    ]

    # Agent status
    if agents_passed:
        summary_lines.append(f"All {len(agents_passed)} agents passed:")
        for agent in agents_passed:
            summary_lines.append(f"- {agent}")
    else:
        summary_lines.append("Workflow completed successfully")

    # PR section (if available)
    if pr_url:
        summary_lines.append("### Pull Request")
        summary_lines.append(f"- {pr_url}")

    # Commit section
    summary_lines.append("### Commit")
    summary_lines.append(f"- {commit_hash}")

    # Files changed section
    if files_changed:
        summary_lines.append("### Files Changed")
        summary_lines.append(f"{len(files_changed)} files changed:")

        # Show first 10 files, truncate rest
        display_files = files_changed[:10]
        for file_path in display_files:
            # Sanitize file path (CWE-117)
            safe_path = sanitize_output(str(file_path))
            summary_lines.append(f"- {safe_path}")

        # Truncation message
        if len(files_changed) > 10:
            remaining = len(files_changed) - 10
            summary_lines.append(f"... {remaining} more")

    # Footer
    summary_lines.append("---")
    summary_lines.append("Generated by autonomous-dev /auto-implement workflow")

    return "\n".join(summary_lines)


def close_github_issue(issue_number: int, comment: str) -> bool:
    """
    Close GitHub issue via gh CLI with comment.

    Args:
        issue_number: GitHub issue number
        comment: Close comment (markdown formatted)

    Returns:
        True if issue closed successfully

    Raises:
        ValueError: If issue number is invalid (CWE-20)
        IssueNotFoundError: If issue doesn't exist
        GitHubAPIError: If gh CLI fails (timeout, network)

    Security:
        - CWE-20: Validates issue number is positive integer
        - CWE-78: Uses subprocess list args (never shell=True)
        - Audit logging: Logs all gh CLI operations

    Examples:
        >>> close_github_issue(8, "Completed via /auto-implement")
        True
        >>> close_github_issue(-1, "test")
        ValueError: Issue number must be positive
    """
    # CWE-20: Input validation - positive integers only
    if not isinstance(issue_number, int) or issue_number <= 0:
        raise ValueError(f"Issue number must be positive integer (got: {issue_number})")

    if issue_number > MAX_ISSUE_NUMBER:
        raise ValueError(f"Issue number too large (max: {MAX_ISSUE_NUMBER})")

    # CWE-78: Command injection prevention - list args, shell=False
    cmd = ['gh', 'issue', 'close', str(issue_number), '--comment', comment]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=GH_CLI_TIMEOUT,
            check=True,
        )

        # Success
        log_audit_event({
            'action': 'close_github_issue',
            'issue_number': issue_number,
            'status': 'success',
            'timestamp': None,  # Will be added by audit_log
        })

        return True

    except TimeoutExpired as e:
        audit_log(
            event_type='close_github_issue',
            status='timeout',
            context={
                'issue_number': issue_number,
                'timeout': GH_CLI_TIMEOUT,
            },
        )
        raise GitHubAPIError(f"Timeout closing issue #{issue_number}") from e

    except CalledProcessError as e:
        # Check if issue not found
        if 'not found' in e.stderr.lower():
            audit_log(
                event_type='close_github_issue',
                status='not_found',
                context={
                    'issue_number': issue_number,
                    'stderr': e.stderr,
                },
            )
            raise IssueNotFoundError(f"Issue #{issue_number} not found") from e

        # Check if already closed (idempotent)
        if 'already closed' in e.stderr.lower():
            audit_log(
                event_type='close_github_issue',
                status='already_closed',
                context={
                    'issue_number': issue_number,
                    'stderr': e.stderr,
                },
            )
            return True  # Idempotent - already closed is success

        # Other gh CLI errors
        audit_log(
            event_type='close_github_issue',
            status='failed',
            context={
                'issue_number': issue_number,
                'stderr': e.stderr,
            },
        )
        raise GitHubAPIError(f"Failed to close issue #{issue_number}: {e.stderr}") from e


def log_audit_event(event: Dict[str, Any]) -> None:
    """
    Log audit event for issue closing operations.

    Wrapper around security_utils.audit_log() for consistent formatting.

    Args:
        event: Event dictionary with keys:
            - action: Operation name (e.g., 'close_github_issue')
            - issue_number: GitHub issue number
            - status: 'success', 'failed', 'timeout', etc.
            - timestamp: Optional timestamp (auto-added if None)

    Security:
        - Audit logging requirement for all gh CLI operations

    Examples:
        >>> log_audit_event({
        ...     'action': 'close_github_issue',
        ...     'issue_number': 8,
        ...     'status': 'success',
        ... })
    """
    audit_log(
        event_type=event.get('action', 'github_issue_operation'),
        status=event.get('status', 'unknown'),
        context={
            'issue_number': event.get('issue_number'),
            'action': event.get('action'),
        },
    )


def prompt_user_consent(issue_number: int, title: str = "") -> bool:
    """
    Prompt user for consent to close issue.

    Checks environment variable and user preferences first, then prompts
    if needed. Implements first-run consent pattern (same as AUTO_GIT_ENABLED).

    Priority order:
    1. AUTO_CLOSE_ISSUES environment variable (if set)
    2. Saved user preference (if previously answered)
    3. Interactive first-run prompt (ask once, remember forever)

    Args:
        issue_number: GitHub issue number
        title: Issue title (optional, for display)

    Returns:
        True if user consents (env var, saved pref, or interactive yes), False otherwise

    Environment Variables:
        AUTO_CLOSE_ISSUES: Set to 'true' to auto-close, 'false' to never close

    Examples:
        >>> # Environment variable set
        >>> os.environ['AUTO_CLOSE_ISSUES'] = 'true'
        >>> prompt_user_consent(8)
        True  # No prompt, uses env var

        >>> # First run (no saved preference)
        >>> prompt_user_consent(8, "Add authentication")
        Auto-close GitHub issues when features complete? [yes/no]: yes
        ✓ Preference saved. You won't be asked again.
        True

        >>> # Subsequent runs (preference saved)
        >>> prompt_user_consent(42)
        True  # No prompt, uses saved preference
    """
    import os
    import sys
    from pathlib import Path

    # Import UserStateManager
    try:
        from .user_state_manager import UserStateManager, DEFAULT_STATE_FILE
    except ImportError:
        # Direct script execution
        lib_dir = Path(__file__).parent.resolve()
        sys.path.insert(0, str(lib_dir))
        from user_state_manager import UserStateManager, DEFAULT_STATE_FILE

    # STEP 1: Check environment variable (highest priority)
    env_value = os.environ.get('AUTO_CLOSE_ISSUES', '').strip().lower()
    if env_value in ('true', 'yes', '1'):
        return True
    elif env_value in ('false', 'no', '0'):
        return False

    # STEP 2: Check saved user preference
    try:
        manager = UserStateManager(DEFAULT_STATE_FILE)
        saved_preference = manager.get_preference('auto_close_issues')

        if saved_preference is not None:
            # User has answered before, use saved preference
            return bool(saved_preference)

    except Exception:
        # If user state manager fails, fall back to interactive prompt
        pass

    # STEP 3: First-run interactive prompt
    print("\n" + "="*60)
    print("GitHub Issue Auto-Close Configuration")
    print("="*60)
    print("\nWhen features complete successfully, automatically close the")
    print("associated GitHub issue?")
    print("\nBenefits:")
    print("  • Fully automated workflow (no manual cleanup)")
    print("  • Unattended batch processing (/batch-implement)")
    print("  • Issue closed with workflow metadata")
    print("\nRequirements:")
    print("  • gh CLI installed and authenticated")
    print("  • Include issue number in request (e.g., 'issue #72')")
    print("\nYou can override later with AUTO_CLOSE_ISSUES environment variable.")
    print("="*60 + "\n")

    # Retry loop for invalid input
    while True:
        try:
            response = input("Auto-close GitHub issues when features complete? [yes/no]: ").strip().lower()

            if response in ('yes', 'y'):
                # Save preference
                try:
                    manager = UserStateManager(DEFAULT_STATE_FILE)
                    manager.set_preference('auto_close_issues', True)
                    manager.save()
                    print("✓ Preference saved. You won't be asked again.\n")
                except Exception as e:
                    print(f"⚠️  Could not save preference: {e}")
                    print("   You'll be prompted again next time.\n")

                return True

            elif response in ('no', 'n'):
                # Save preference
                try:
                    manager = UserStateManager(DEFAULT_STATE_FILE)
                    manager.set_preference('auto_close_issues', False)
                    manager.save()
                    print("✓ Preference saved. You won't be asked again.\n")
                    print("   To enable later, set: export AUTO_CLOSE_ISSUES=true\n")
                except Exception as e:
                    print(f"⚠️  Could not save preference: {e}")
                    print("   You'll be prompted again next time.\n")

                return False

            else:
                print("Invalid input. Please enter 'yes' or 'no'.")

        except EOFError:
            # Handle EOF gracefully (e.g., piped input)
            print("\nEOF encountered - defaulting to 'no'.")
            return False
        except KeyboardInterrupt:
            # Re-raise KeyboardInterrupt - let user cancel completely
            print("\nCancelled by user.")
            raise
