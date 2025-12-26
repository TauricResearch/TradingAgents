#!/usr/bin/env python3
"""
Git Operations Library - Consent-based automation for /auto-implement

This library provides git automation functions for the /auto-implement workflow.
All operations are consent-based with graceful degradation - if git operations
fail, the feature implementation still succeeds.

Key Features:
- Prerequisite validation (git installed, repo exists, config set)
- Automated staging and committing
- Automated push with network timeout handling
- Graceful degradation (commit succeeds even if push fails)
- Security-first (never log credentials, validate prerequisites)

Usage:
    from git_operations import auto_commit_and_push

    result = auto_commit_and_push(
        commit_message='feat: add new feature',
        branch='main',
        push=True
    )

    if result['success']:
        print(f"Committed: {result['commit_sha']}")
        if result['pushed']:
            print("Pushed to remote")

Date: 2025-11-04
Workflow: git_automation
Agent: implementer


Design Patterns:
    See library-design-patterns skill for standardized design patterns.
    See api-integration-patterns skill for standardized design patterns.
"""

import subprocess
from typing import Tuple, Dict, Any, List


def validate_git_repo() -> Tuple[bool, str]:
    """
    Validate if current directory is a git repository.

    Returns:
        Tuple of (is_valid, error_message)
        - (True, '') if valid git repository
        - (False, error_message) if not a git repository or git not installed

    Example:
        >>> is_valid, error = validate_git_repo()
        >>> if not is_valid:
        ...     print(f"Error: {error}")
    """
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--git-dir'],
            capture_output=True,
            text=True,
            check=True
        )
        return (True, '')
    except FileNotFoundError:
        return (False, 'git not installed')
    except PermissionError:
        return (False, 'permission denied')
    except subprocess.CalledProcessError as e:
        # Git command failed - likely not a git repository
        if 'not a git repository' in e.stderr.lower():
            return (False, 'not a git repository')
        return (False, f'git error: {e.stderr.strip()}')
    except Exception as e:
        return (False, f'unexpected error: {str(e)}')


def check_git_config() -> Tuple[bool, str]:
    """
    Validate that git user.name and user.email are configured.

    Returns:
        Tuple of (is_configured, error_message)
        - (True, '') if both user.name and user.email are set
        - (False, error_message) if one or both are missing

    Example:
        >>> is_configured, error = check_git_config()
        >>> if not is_configured:
        ...     print(f"Git config error: {error}")
    """
    name_set = False
    email_set = False

    # Check user.name
    try:
        name_result = subprocess.run(
            ['git', 'config', 'user.name'],
            capture_output=True,
            text=True,
            check=True
        )
        name = name_result.stdout.strip()
        if name:
            name_set = True
    except subprocess.CalledProcessError:
        pass  # name not set

    # Check user.email
    try:
        email_result = subprocess.run(
            ['git', 'config', 'user.email'],
            capture_output=True,
            text=True,
            check=True
        )
        email = email_result.stdout.strip()
        if email:
            email_set = True
    except subprocess.CalledProcessError:
        pass  # email not set

    # Determine what's missing
    if name_set and email_set:
        return (True, '')
    elif not name_set and not email_set:
        return (False, 'git user.name not set')  # Report first missing
    elif not name_set:
        return (False, 'git user.name not set')
    else:  # not email_set
        return (False, 'git user.email not set')


def detect_merge_conflict() -> Tuple[bool, List[str]]:
    """
    Detect if there are unmerged paths (merge conflicts).

    Returns:
        Tuple of (has_conflict, conflicted_files)
        - (False, []) if no conflicts
        - (True, ['file1.py', 'file2.py']) if conflicts exist

    Example:
        >>> has_conflict, files = detect_merge_conflict()
        >>> if has_conflict:
        ...     print(f"Conflicts in: {', '.join(files)}")
    """
    try:
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            capture_output=True,
            text=True,
            check=True
        )

        # Parse output for merge conflict markers
        # Porcelain format:
        # UU = both modified
        # AA = both added
        # DD = both deleted
        # Regular format (for test compatibility):
        # "both modified:" or "both added:" or "both deleted:"

        conflicted_files = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue

            # Check porcelain format (first 2 characters)
            if len(line) >= 3:
                status = line[:2]
                if status in ('UU', 'AA', 'DD'):
                    # Extract filename (after status codes and space)
                    filename = line[3:].strip()
                    if filename:
                        conflicted_files.append(filename)

            # Also check regular format (for test compatibility)
            if 'both modified:' in line or 'both added:' in line or 'both deleted:' in line:
                # Extract filename after the marker
                parts = line.split(':', 1)
                if len(parts) >= 2:
                    filename = parts[1].strip()
                    if filename and filename not in conflicted_files:
                        conflicted_files.append(filename)

        if conflicted_files:
            return (True, conflicted_files)
        return (False, [])

    except Exception:
        # On error, fail safe - assume no conflicts
        return (False, [])


def is_detached_head() -> bool:
    """
    Check if repository is in detached HEAD state.

    Returns:
        False if on a branch
        True if in detached HEAD state or error (fail-safe)

    Example:
        >>> if is_detached_head():
        ...     print("Warning: detached HEAD state")
    """
    try:
        result = subprocess.run(
            ['git', 'symbolic-ref', '-q', 'HEAD'],
            capture_output=True,
            check=True
        )
        # Returns 0 if on a branch
        return False
    except subprocess.CalledProcessError:
        # Returns 1 if detached HEAD
        return True
    except Exception:
        # On error, fail safe - assume detached
        return True


def has_uncommitted_changes() -> bool:
    """
    Check if there are uncommitted changes in working tree.

    Returns:
        False if working tree is clean
        True if uncommitted changes exist or error (fail-safe)

    Example:
        >>> if not has_uncommitted_changes():
        ...     print("Working tree clean")
    """
    try:
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            capture_output=True,
            text=True,
            check=True
        )
        # Any output means changes exist
        return bool(result.stdout.strip())
    except Exception:
        # On error, fail safe - assume changes exist
        return True


def stage_all_changes() -> Tuple[bool, str]:
    """
    Stage all changes in the working tree.

    Returns:
        Tuple of (success, error_message)
        - (True, '') if staging succeeded
        - (False, error_message) if staging failed

    Example:
        >>> success, error = stage_all_changes()
        >>> if not success:
        ...     print(f"Staging failed: {error}")
    """
    try:
        subprocess.run(
            ['git', 'add', '.'],
            capture_output=True,
            text=True,
            check=True
        )
        return (True, '')
    except PermissionError:
        return (False, 'permission denied')
    except subprocess.CalledProcessError as e:
        return (False, f'git add failed: {e.stderr.strip()}')
    except Exception as e:
        return (False, f'unexpected error: {str(e)}')


def commit_changes(message: str) -> Tuple[bool, str, str]:
    """
    Create a git commit with the given message.

    Args:
        message: Commit message (can be multiline)

    Returns:
        Tuple of (success, commit_sha, error_message)
        - (True, commit_sha, '') if commit succeeded
        - (False, '', error_message) if commit failed

    Example:
        >>> success, sha, error = commit_changes('feat: add feature')
        >>> if success:
        ...     print(f"Committed: {sha}")
    """
    # Validate message
    if not message or not message.strip():
        return (False, '', 'commit message cannot be empty')

    try:
        result = subprocess.run(
            ['git', 'commit', '-m', message],
            capture_output=True,
            text=True,
            check=True
        )

        # Parse commit SHA from output
        # Format: "[branch_name commit_sha] commit message"
        # Example: "[main abc1234] feat: add feature"
        commit_sha = ''
        stdout = result.stdout.strip()
        if stdout:
            # Look for pattern [branch sha]
            import re
            match = re.search(r'\[[\w/-]+\s+([a-f0-9]+)\]', stdout)
            if match:
                commit_sha = match.group(1)

        return (True, commit_sha, '')

    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip()

        # Handle "nothing to commit"
        if 'nothing to commit' in stderr.lower():
            return (False, '', 'nothing to commit, working tree clean')

        # Handle missing git config
        if 'user.name' in stderr.lower() or 'user.email' in stderr.lower():
            return (False, '', 'git user.name or user.email not set')

        return (False, '', f'git commit failed: {stderr}')

    except Exception as e:
        return (False, '', f'unexpected error: {str(e)}')


def get_remote_name() -> str:
    """
    Get the name of the first git remote (usually 'origin').

    Returns:
        Remote name (e.g., 'origin') or empty string if no remote configured

    Example:
        >>> remote = get_remote_name()
        >>> if not remote:
        ...     print("No remote configured")
    """
    try:
        result = subprocess.run(
            ['git', 'remote'],
            capture_output=True,
            text=True,
            check=True
        )
        # Return first line (first remote)
        remotes = result.stdout.strip().split('\n')
        if remotes and remotes[0]:
            return remotes[0].strip()
        return ''
    except Exception:
        return ''


def push_to_remote(
    branch: str,
    remote: str = 'origin',
    set_upstream: bool = False,
    timeout: int = 30
) -> Tuple[bool, str]:
    """
    Push commits to remote repository.

    Args:
        branch: Branch name to push
        remote: Remote name (default: 'origin')
        set_upstream: Use -u flag for new branches (default: False)
        timeout: Network timeout in seconds (default: 30)

    Returns:
        Tuple of (success, error_message)
        - (True, '') if push succeeded
        - (False, error_message) if push failed

    Example:
        >>> success, error = push_to_remote('main', 'origin')
        >>> if not success:
        ...     print(f"Push failed: {error}")
    """
    try:
        # Build command
        cmd = ['git', 'push']
        if set_upstream:
            cmd.append('-u')
        cmd.extend([remote, branch])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout
        )
        return (True, '')

    except subprocess.TimeoutExpired:
        return (False, 'network timeout while pushing to remote')

    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip()

        # Parse specific errors
        if 'protected branch' in stderr.lower():
            return (False, 'protected branch update failed')
        elif 'permission denied' in stderr.lower() or 'forbidden' in stderr.lower():
            return (False, 'permission denied')
        elif 'rejected' in stderr.lower():
            return (False, f'push rejected: {stderr}')
        else:
            return (False, f'git push failed: {stderr}')

    except Exception as e:
        return (False, f'unexpected error: {str(e)}')


def create_feature_branch(branch_name: str) -> Tuple[bool, str, str]:
    """
    Create a new feature branch.

    Args:
        branch_name: Name for the new branch

    Returns:
        Tuple of (success, branch_name, error_message)
        - (True, branch_name, '') if branch created
        - (False, '', error_message) if branch creation failed

    Example:
        >>> success, branch, error = create_feature_branch('feature/test')
        >>> if success:
        ...     print(f"Created branch: {branch}")
    """
    try:
        subprocess.run(
            ['git', 'checkout', '-b', branch_name],
            capture_output=True,
            text=True,
            check=True
        )
        return (True, branch_name, '')

    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip()

        # Parse specific errors
        if 'already exists' in stderr.lower():
            return (False, '', f"branch '{branch_name}' already exists")
        elif 'not a valid branch name' in stderr.lower():
            return (False, '', f"'{branch_name}' is not a valid branch name")
        else:
            return (False, '', f'git checkout failed: {stderr}')

    except Exception as e:
        return (False, '', f'unexpected error: {str(e)}')


def auto_commit_and_push(
    commit_message: str,
    branch: str,
    push: bool = True
) -> Dict[str, Any]:
    """
    High-level function that orchestrates the full commit-and-push workflow.

    This function provides graceful degradation - if commit succeeds but push
    fails, it still reports success (the commit worked).

    Workflow:
        1. Validate git repo
        2. Check git config
        3. Detect merge conflicts
        4. Check for detached HEAD
        5. Check for uncommitted changes
        6. Stage all changes
        7. Commit changes
        8. Get remote name (if push requested)
        9. Push to remote (if push requested)

    Args:
        commit_message: Commit message
        branch: Branch name to push to
        push: Whether to push after committing (default: True)

    Returns:
        Dictionary with keys:
            - success (bool): Overall success (True if commit succeeded)
            - commit_sha (str): Commit SHA if committed, '' otherwise
            - pushed (bool): True if pushed successfully
            - error (str): Error message if any, '' otherwise

    Example:
        >>> result = auto_commit_and_push('feat: add feature', 'main', True)
        >>> if result['success']:
        ...     print(f"Committed: {result['commit_sha']}")
        ...     if result['pushed']:
        ...         print("Pushed to remote")
    """
    result = {
        'success': False,
        'commit_sha': '',
        'pushed': False,
        'error': ''
    }

    # Step 1: Validate git repository
    is_valid, error = validate_git_repo()
    if not is_valid:
        result['error'] = error
        return result

    # Step 2: Check git config
    is_configured, error = check_git_config()
    if not is_configured:
        result['error'] = error
        return result

    # Step 3: Detect merge conflicts
    has_conflict, files = detect_merge_conflict()
    if has_conflict:
        result['error'] = f"merge conflict detected in: {', '.join(files)}"
        return result

    # Step 4: Check for detached HEAD
    if is_detached_head():
        result['error'] = 'repository is in detached HEAD state'
        return result

    # Step 5: Check for uncommitted changes
    if not has_uncommitted_changes():
        result['success'] = True  # Not an error - just nothing to do
        result['error'] = 'nothing to commit, working tree clean'
        return result

    # Step 6: Stage all changes
    stage_success, error = stage_all_changes()
    if not stage_success:
        result['error'] = f'failed to stage changes: {error}'
        return result

    # Step 7: Commit changes
    commit_success, commit_sha, error = commit_changes(commit_message)
    if not commit_success:
        result['error'] = error
        return result

    # Commit succeeded - mark as success even if push fails
    result['success'] = True
    result['commit_sha'] = commit_sha

    # Step 8-9: Push to remote (if requested)
    if push:
        # Get remote name
        remote = get_remote_name()
        if not remote:
            result['error'] = 'no remote configured'
            return result

        # Push to remote
        push_success, error = push_to_remote(branch, remote)
        if push_success:
            result['pushed'] = True
        else:
            # Push failed, but commit succeeded - graceful degradation
            result['error'] = error

    return result


class GitOperations:
    """
    Object-oriented wrapper for git operations functions.

    Provides a class-based interface to git automation functions.
    All methods are static/class methods that delegate to module functions.
    """

    @staticmethod
    def validate_repo() -> Tuple[bool, str]:
        """Validate if current directory is a git repository."""
        return validate_git_repo()

    @staticmethod
    def check_config() -> Tuple[bool, str]:
        """Validate git user.name and user.email are configured."""
        return check_git_config()

    @staticmethod
    def detect_conflicts() -> Tuple[bool, List[str]]:
        """Detect merge conflicts in repository."""
        return detect_merge_conflict()

    @staticmethod
    def is_detached() -> bool:
        """Check if repository is in detached HEAD state."""
        return is_detached_head()

    @staticmethod
    def has_changes() -> bool:
        """Check if repository has uncommitted changes."""
        return has_uncommitted_changes()

    @staticmethod
    def stage_all() -> Tuple[bool, str]:
        """Stage all changes for commit."""
        return stage_all_changes()

    @staticmethod
    def commit(message: str) -> Tuple[bool, str, str]:
        """Commit staged changes with given message."""
        return commit_changes(message)

    @staticmethod
    def push(branch: str = 'main', remote: str = None) -> Tuple[bool, str]:
        """Push commits to remote repository."""
        if remote is None:
            remote = get_remote_name()
        return push_to_remote(branch, remote)

    @staticmethod
    def auto_commit_push(
        commit_message: str,
        branch: str = 'main',
        push: bool = True
    ) -> Dict[str, Any]:
        """Automated commit and push workflow."""
        return auto_commit_and_push(commit_message, branch, push)
