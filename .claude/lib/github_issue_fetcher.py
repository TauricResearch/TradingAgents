#!/usr/bin/env python3
"""
GitHub Issue Fetcher - Fetch issue titles via gh CLI for batch processing.

Provides secure GitHub issue fetching functionality for /batch-implement --issues flag.
Uses gh CLI for GitHub operations with comprehensive security validation.

Security Features:
- CWE-20: Input validation (positive integers, max 100 issues)
- CWE-78: Command injection prevention (subprocess list args, shell=False)
- CWE-117: Log injection prevention (sanitize newlines, control characters)
- Audit logging for all gh CLI operations

Key Functions:
1. validate_issue_numbers() - Validate issue numbers before subprocess calls
2. fetch_issue_title() - Fetch single issue title via gh CLI
3. fetch_issue_titles() - Batch fetch multiple issue titles
4. format_feature_description() - Format issue as feature description

Workflow:
    1. Parse --issues argument: "72,73,74" → [72, 73, 74]
    2. Validate issue numbers (validate_issue_numbers)
    3. Fetch titles from GitHub (fetch_issue_titles)
    4. Format as features (format_feature_description)
    5. Create batch state with issue_numbers

Usage:
    from github_issue_fetcher import (
        validate_issue_numbers,
        fetch_issue_titles,
        format_feature_description,
    )

    # Parse issue numbers
    issue_numbers = [72, 73, 74]

    # Validate
    validate_issue_numbers(issue_numbers)

    # Fetch titles
    issue_titles = fetch_issue_titles(issue_numbers)
    # Returns: {72: "Add logging", 73: "Fix bug"}

    # Format as features
    features = [
        format_feature_description(num, title)
        for num, title in issue_titles.items()
    ]
    # Returns: ["Issue #72: Add logging", "Issue #73: Fix bug"]

Date: 2025-11-16
Issue: #77 (Add --issues flag to /batch-implement)
Agent: implementer
Phase: TDD Green (making tests pass)

See error-handling-patterns skill for exception hierarchy and error handling best practices.


Design Patterns:
    See library-design-patterns skill for standardized design patterns.
    See api-integration-patterns skill for standardized design patterns.
"""

import json
import subprocess
from pathlib import Path
from typing import List, Dict, Optional
from subprocess import TimeoutExpired

# Import security utilities for audit logging
import sys
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


# =============================================================================
# CONSTANTS
# =============================================================================


# Maximum issues per batch (prevent resource exhaustion)
MAX_ISSUES_PER_BATCH = 100

# Subprocess timeout (seconds)
GH_CLI_TIMEOUT = 10

# Title truncation length (prevent log bloat)
MAX_TITLE_LENGTH = 200


# =============================================================================
# INPUT VALIDATION (CWE-20)
# =============================================================================


def validate_issue_numbers(issue_numbers: List[int]) -> None:
    """Validate GitHub issue numbers.

    Security (CWE-20): Input Validation
    - Accept only positive integers (>0)
    - Reject zero, negative numbers
    - Enforce maximum limit (100 issues per batch)
    - Prevent resource exhaustion attacks

    Args:
        issue_numbers: List of GitHub issue numbers

    Raises:
        ValueError: If validation fails with helpful message

    Examples:
        >>> validate_issue_numbers([72, 73, 74])  # Valid
        >>> validate_issue_numbers([])  # Raises ValueError
        ValueError: Issue numbers list cannot be empty
        >>> validate_issue_numbers([-1])  # Raises ValueError
        ValueError: Invalid issue number: -1. Issue numbers must be positive integers.
        >>> validate_issue_numbers([0])  # Raises ValueError
        ValueError: Invalid issue number: 0. Issue numbers must be positive integers.
        >>> validate_issue_numbers(list(range(1, 102)))  # Raises ValueError
        ValueError: Too many issues: 101. Maximum allowed is 100 issues per batch.

    Security Notes:
        - This function MUST be called BEFORE any subprocess calls
        - Prevents command injection via invalid issue numbers
        - Prevents resource exhaustion via batch size limits
    """
    # Check for empty list
    if not issue_numbers:
        raise ValueError(
            "Issue numbers list cannot be empty. "
            "Provide at least one issue number."
        )

    # Check maximum batch size
    if len(issue_numbers) > MAX_ISSUES_PER_BATCH:
        raise ValueError(
            f"Too many issues: {len(issue_numbers)}. "
            f"Maximum allowed is {MAX_ISSUES_PER_BATCH} issues per batch. "
            f"Consider splitting into multiple batches."
        )

    # Validate each issue number
    for num in issue_numbers:
        if not isinstance(num, int) or num <= 0:
            raise ValueError(
                f"Invalid issue number: {num}. "
                f"Issue numbers must be positive integers (>0)."
            )

    # Audit log successful validation
    audit_log("github_issue_validation", "success", {
        "operation": "validate_issue_numbers",
        "count": len(issue_numbers),
        "issue_numbers": issue_numbers[:10],  # Log first 10 for audit trail
    })


# =============================================================================
# SINGLE ISSUE FETCHING (CWE-78)
# =============================================================================


def fetch_issue_title(issue_number: int) -> Optional[str]:
    """Fetch single GitHub issue title via gh CLI.

    Security (CWE-78): Command Injection Prevention
    - Use subprocess.run() with LIST arguments (not string)
    - shell=False (CRITICAL security requirement)
    - 10-second timeout to prevent hung processes
    - Audit log all gh CLI operations

    Args:
        issue_number: GitHub issue number

    Returns:
        Issue title if exists, None if not found (404)

    Raises:
        FileNotFoundError: If gh CLI is not installed
        TimeoutExpired: If gh CLI hangs (>10 seconds)
        OSError: If network or system errors occur

    Examples:
        >>> fetch_issue_title(72)  # Existing issue
        'Add logging feature'
        >>> fetch_issue_title(9999)  # Non-existent issue
        None
        >>> fetch_issue_title(72)  # gh CLI not installed
        FileNotFoundError: gh CLI not found. Install from: https://cli.github.com

    Security Notes:
        - CRITICAL: Uses subprocess.run() with list args (prevents command injection)
        - CRITICAL: shell=False prevents shell metacharacter attacks
        - Validates subprocess command construction in tests
        - All operations are audit logged
    """
    try:
        # SECURITY CRITICAL: Use list arguments, shell=False
        # This prevents command injection via issue_number
        result = subprocess.run(
            ['gh', 'issue', 'view', str(issue_number), '--json', 'title'],
            capture_output=True,
            text=True,
            timeout=GH_CLI_TIMEOUT,
            shell=False,  # CRITICAL: Never use shell=True
        )

        # Check return code
        if result.returncode != 0:
            # Check for common errors
            stderr_lower = result.stderr.lower()

            # Issue not found (404)
            if 'no pull requests or issues found' in stderr_lower or 'not found' in stderr_lower:
                audit_log(f"Issue #{issue_number} not found (404)", "not_found", {
                    "operation": "fetch_issue_title",
                    "issue_number": issue_number,
                    "error": "Issue not found (404)",
                })
                return None

            # Authentication error
            if 'authentication' in stderr_lower or 'unauthorized' in stderr_lower:
                audit_log("github_issue_fetch", "error", {
                    "operation": "fetch_issue_title",
                    "issue_number": issue_number,
                    "error": "Authentication required",
                })
                # Graceful degradation - return None instead of raising
                return None

            # Rate limit
            if 'rate limit' in stderr_lower:
                audit_log("github_issue_fetch", "error", {
                    "operation": "fetch_issue_title",
                    "issue_number": issue_number,
                    "error": "API rate limit exceeded",
                })
                # Graceful degradation - return None instead of raising
                return None

            # Other errors - graceful degradation
            audit_log("github_issue_fetch", "error", {
                "operation": "fetch_issue_title",
                "issue_number": issue_number,
                "error": result.stderr[:200],  # Log first 200 chars
            })
            return None

        # Parse JSON response
        try:
            data = json.loads(result.stdout)
            title = data.get('title', '')

            # Audit log success
            audit_log(f"Successfully fetched issue #{issue_number}", "success", {
                "operation": "fetch_issue_title",
                "issue_number": issue_number,
                "title_length": len(title),
            })

            return title

        except json.JSONDecodeError as e:
            # Graceful degradation on JSON parse error
            audit_log("github_issue_fetch", "error", {
                "operation": "fetch_issue_title",
                "issue_number": issue_number,
                "error": f"JSON parse error: {e}",
            })
            return None

    except FileNotFoundError:
        # gh CLI not installed
        audit_log("github_issue_fetch", "error", {
            "operation": "fetch_issue_title",
            "issue_number": issue_number,
            "error": "gh CLI not found",
        })
        raise FileNotFoundError(
            "gh CLI not found. Install from: https://cli.github.com\n"
            "After installing, authenticate with: gh auth login"
        )

    except TimeoutExpired:
        # gh CLI timeout
        audit_log("github_issue_fetch", "error", {
            "operation": "fetch_issue_title",
            "issue_number": issue_number,
            "error": f"Timeout after {GH_CLI_TIMEOUT} seconds",
        })
        raise

    except OSError as e:
        # Network or system error
        audit_log("github_issue_fetch", "error", {
            "operation": "fetch_issue_title",
            "issue_number": issue_number,
            "error": str(e),
        })
        raise


# =============================================================================
# BATCH ISSUE FETCHING
# =============================================================================


def fetch_issue_titles(issue_numbers: List[int]) -> Dict[int, str]:
    """Batch fetch multiple GitHub issue titles.

    Features:
    - Call fetch_issue_title() for each issue
    - Graceful degradation: skip missing issues (return None)
    - Audit log batch operations
    - Raise ValueError if ALL issues missing

    Args:
        issue_numbers: List of GitHub issue numbers

    Returns:
        Dict mapping issue_number → title (only successful fetches)

    Raises:
        ValueError: If ALL issues are missing or failed to fetch
        FileNotFoundError: If gh CLI is not installed
        TimeoutExpired: If gh CLI hangs

    Examples:
        >>> fetch_issue_titles([72, 73, 74])
        {72: 'Add logging', 73: 'Fix bug', 74: 'Update docs'}
        >>> fetch_issue_titles([72, 9999, 74])  # 9999 doesn't exist
        {72: 'Add logging', 74: 'Update docs'}
        >>> fetch_issue_titles([9998, 9999])  # All missing
        ValueError: No issues found. All issue numbers are invalid or don't exist: [9998, 9999]

    Security Notes:
        - Input validation should be done BEFORE calling this function
        - All gh CLI operations are audit logged
        - Graceful degradation on missing issues
    """
    # Audit log batch start
    audit_log("github_issue_fetch_batch start", "info", {
        "operation": "fetch_issue_titles",
        "count": len(issue_numbers),
        "issue_numbers": issue_numbers[:10],  # Log first 10
    })

    results = {}
    missing_issues = []

    # Fetch each issue
    for num in issue_numbers:
        title = fetch_issue_title(num)

        if title is not None:
            results[num] = title
            # Log successful fetch in batch context
            audit_log(f"Batch: fetched issue #{num}", "info", {
                "operation": "fetch_issue_titles_item",
                "issue_number": num,
            })
        else:
            missing_issues.append(num)

    # Check if ALL issues failed
    if not results:
        audit_log("github_issue_fetch_batch", "error", {
            "operation": "fetch_issue_titles",
            "error": "All issues failed to fetch",
            "missing_issues": missing_issues,
        })
        raise ValueError(
            f"No issues found. All issue numbers are invalid or don't exist: {missing_issues}\n"
            f"Please verify the issue numbers and try again."
        )

    # Log warnings for missing issues
    if missing_issues:
        audit_log("github_issue_fetch_batch", "warning", {
            "operation": "fetch_issue_titles",
            "successful": len(results),
            "missing": len(missing_issues),
            "missing_issues": missing_issues,
        })

    # Audit log batch completion
    audit_log("github_issue_fetch_batch complete", "info", {
        "operation": "fetch_issue_titles",
        "successful": len(results),
        "total": len(issue_numbers),
    })

    return results


# =============================================================================
# OUTPUT FORMATTING (CWE-117)
# =============================================================================


def format_feature_description(issue_number: int, title: str) -> str:
    """Format issue as feature description.

    Security (CWE-117): Log Injection Prevention
    - Sanitize newlines (\n, \r)
    - Remove control characters (\t, \x00, \x1b)
    - Truncate long titles (>200 chars → "...")
    - Handle empty/whitespace-only titles

    Args:
        issue_number: GitHub issue number
        title: Issue title (may contain malicious characters)

    Returns:
        Formatted feature description: "Issue #72: Add logging feature"

    Examples:
        >>> format_feature_description(72, "Add logging feature")
        'Issue #72: Add logging feature'
        >>> format_feature_description(72, "Title\\nINJECTED\\nLOG")
        'Issue #72: Title INJECTED LOG'
        >>> format_feature_description(72, "")
        'Issue #72: (no title)'
        >>> format_feature_description(72, "A" * 500)
        'Issue #72: AAAA...AAA...'

    Security Notes:
        - CRITICAL: Sanitizes newlines to prevent log injection (CWE-117)
        - Removes control characters (\t, \x00, \x1b, etc.)
        - Truncates long titles to prevent log bloat
        - All malicious characters are replaced or removed
    """
    # Strip whitespace
    title = title.strip()

    # Handle empty titles
    if not title:
        return f"Issue #{issue_number}: (no title)"

    # SECURITY: Remove newlines (CWE-117 prevention)
    # Replace \n and \r with spaces
    title = title.replace('\n', ' ').replace('\r', ' ')

    # SECURITY: Remove control characters
    # Keep only printable characters (ASCII 32-126) and space
    sanitized = []
    for char in title:
        char_code = ord(char)
        if char_code >= 32 and char_code <= 126:
            sanitized.append(char)
        elif char == ' ':
            sanitized.append(char)
        # Skip all other control characters (\t, \x00, \x1b, etc.)

    title = ''.join(sanitized)

    # Collapse multiple spaces
    title = ' '.join(title.split())

    # Handle whitespace-only after sanitization
    if not title:
        return f"Issue #{issue_number}: (no title)"

    # SECURITY: Truncate long titles (prevent log bloat)
    if len(title) > MAX_TITLE_LENGTH:
        title = title[:MAX_TITLE_LENGTH] + "..."

    return f"Issue #{issue_number}: {title}"
