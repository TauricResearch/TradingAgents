#!/usr/bin/env python3
"""
Acceptance Criteria Parser - Extract and format acceptance criteria from GitHub issues.

Fetches GitHub issue bodies via gh CLI, parses acceptance criteria sections,
and formats criteria for UAT test generation with Gherkin-style scenarios.

Key Features:
1. Fetch issue body via gh CLI (subprocess with security)
2. Parse categorized acceptance criteria (### headers)
3. Format criteria as Gherkin-style test scenarios
4. Handle malformed/missing criteria gracefully
5. Security: subprocess list args (no shell=True), input validation

Usage:
    from acceptance_criteria_parser import (
        fetch_issue_body,
        parse_acceptance_criteria,
        format_for_uat
    )

    # Full pipeline
    issue_body = fetch_issue_body(161)
    criteria = parse_acceptance_criteria(issue_body)
    uat_scenarios = format_for_uat(criteria)

Date: 2025-12-25
Issue: #161 (Enhanced test-master for 3-tier coverage)
Agent: implementer
Phase: TDD Green (making tests pass)
"""

import re
import subprocess
from typing import Dict, List


def fetch_issue_body(issue_number: int) -> str:
    """Fetch GitHub issue body via gh CLI.

    Args:
        issue_number: GitHub issue number

    Returns:
        Issue body as string

    Raises:
        ValueError: If issue not found (404)
        RuntimeError: If gh CLI not installed or network error

    Security:
        - Uses subprocess.run with list args (no shell=True)
        - Validates issue_number is positive integer
        - No credential exposure

    Example:
        >>> body = fetch_issue_body(161)
        >>> "Acceptance Criteria" in body
        True
    """
    # Validate issue number
    if not isinstance(issue_number, int) or issue_number <= 0:
        raise ValueError(f"Invalid issue number: {issue_number}")

    # Build gh CLI command
    cmd = [
        "gh", "issue", "view", str(issue_number),
        "--json", "body",
        "--jq", ".body"
    ]

    try:
        # Execute gh CLI (security: list args, no shell=True)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False  # Handle return codes manually
        )

        # Check for errors
        if result.returncode != 0:
            stderr_lower = result.stderr.lower()
            # Check network errors first (more specific than generic "could not resolve")
            if "could not resolve host" in stderr_lower or "network" in stderr_lower:
                raise RuntimeError(f"Network error fetching issue #{issue_number}: {result.stderr}")
            elif "could not resolve" in stderr_lower or "not found" in stderr_lower:
                raise ValueError(f"Issue #{issue_number} not found")
            else:
                raise RuntimeError(f"gh CLI error: {result.stderr}")

        return result.stdout

    except FileNotFoundError:
        raise RuntimeError(
            "gh CLI not installed. Install with: brew install gh (macOS) or see https://cli.github.com/"
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Timeout fetching issue #{issue_number}")


def parse_acceptance_criteria(issue_body: str) -> Dict[str, List[str]]:
    """Parse acceptance criteria from GitHub issue body.

    Extracts criteria from "## Acceptance Criteria" section, supporting both
    categorized (### headers) and uncategorized (- [ ] items) formats.

    Args:
        issue_body: GitHub issue body text

    Returns:
        Dict mapping category name to list of criteria strings.
        Empty dict if no acceptance criteria found.

    Examples:
        Categorized:
        >>> body = '''
        ... ## Acceptance Criteria
        ... ### Fresh Install
        ... - [ ] Feature works
        ... - [ ] Tests pass
        ... '''
        >>> criteria = parse_acceptance_criteria(body)
        >>> criteria["Fresh Install"]
        ['Feature works', 'Tests pass']

        Uncategorized:
        >>> body = '''
        ... ## Acceptance Criteria
        ... - [ ] Feature works
        ... - [ ] Tests pass
        ... '''
        >>> criteria = parse_acceptance_criteria(body)
        >>> criteria["General"]
        ['Feature works', 'Tests pass']
    """
    # Find "## Acceptance Criteria" section
    # Pattern matches ## but not ### to avoid stopping at category headers
    ac_pattern = r"## Acceptance Criteria\s*\n(.*?)(?=\n## [^#]|\Z)"
    match = re.search(ac_pattern, issue_body, re.DOTALL | re.IGNORECASE)

    if not match:
        return {}

    ac_section = match.group(1)

    # Check for categorized criteria (### headers)
    category_pattern = r"###\s+([^\n]+)\s*\n(.*?)(?=\n###|\Z)"
    category_matches = list(re.finditer(category_pattern, ac_section, re.DOTALL))

    if category_matches:
        # Categorized format
        result = {}
        for category_match in category_matches:
            category = category_match.group(1).strip()
            criteria_text = category_match.group(2)
            criteria = _extract_criteria_items(criteria_text)
            if criteria:  # Only add categories with criteria
                result[category] = criteria
        return result
    else:
        # Uncategorized format - all items go to "General"
        criteria = _extract_criteria_items(ac_section)
        if criteria:
            return {"General": criteria}
        else:
            return {}


def _extract_criteria_items(text: str) -> List[str]:
    """Extract individual criteria items from text.

    Handles both checkbox format (- [ ]) and plain bullet format (-).
    Strips checkbox markers and cleans whitespace.

    Args:
        text: Text containing criteria items

    Returns:
        List of cleaned criteria strings
    """
    # Pattern for criteria items: - [ ] or - [x] or just -
    item_pattern = r"^[\s]*-\s*(?:\[[ x]\]\s*)?(.+)$"
    criteria = []

    for line in text.split('\n'):
        match = re.match(item_pattern, line.strip())
        if match:
            criterion = match.group(1).strip()
            # Skip empty criteria or noise
            if criterion and not criterion.startswith('(') and criterion.lower() != 'no criteria defined':
                criteria.append(criterion)

    return criteria


def format_for_uat(criteria: Dict[str, List[str]]) -> List[Dict[str, str]]:
    """Format acceptance criteria as UAT test scenarios.

    Converts each criterion into a Gherkin-style test scenario with:
    - category: Original category name
    - criterion: Original criterion text
    - scenario_name: Valid pytest function name (test_*)

    Args:
        criteria: Dict mapping category to list of criteria

    Returns:
        List of scenario dicts, one per criterion

    Example:
        >>> criteria = {"Fresh Install": ["Feature works correctly"]}
        >>> scenarios = format_for_uat(criteria)
        >>> scenarios[0]["scenario_name"]
        'test_fresh_install_feature_works_correctly'
        >>> scenarios[0]["category"]
        'Fresh Install'
    """
    scenarios = []

    for category, criteria_list in criteria.items():
        for criterion in criteria_list:
            # Generate pytest-compatible scenario name
            scenario_name = _generate_scenario_name(category, criterion)

            scenarios.append({
                "category": category,
                "criterion": criterion,
                "scenario_name": scenario_name
            })

    return scenarios


def _generate_scenario_name(category: str, criterion: str) -> str:
    """Generate valid pytest scenario name from category and criterion.

    Converts to snake_case, removes special characters, prepends "test_".

    Args:
        category: Category name (e.g., "Fresh Install")
        criterion: Criterion text (e.g., "Feature works correctly")

    Returns:
        Valid pytest function name (e.g., "test_fresh_install_feature_works_correctly")
    """
    # Combine category and criterion
    combined = f"{category} {criterion}"

    # Convert to lowercase
    name = combined.lower()

    # Replace spaces and special chars with underscores
    name = re.sub(r'[^a-z0-9_]+', '_', name)

    # Remove leading/trailing underscores
    name = name.strip('_')

    # Collapse multiple underscores
    name = re.sub(r'_+', '_', name)

    # Truncate to reasonable length (pytest allows long names, but 100 chars is practical)
    if len(name) > 97:  # 97 + "test_" = 101
        name = name[:97]

    # Prepend "test_"
    return f"test_{name}"
