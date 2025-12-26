#!/usr/bin/env python3
"""
Context-Triggered Skill Injection - Issue #154

Auto-injects relevant skills based on conversation context patterns,
not just agent frontmatter declarations.

Key Features:
- Pattern-based detection (fast regex, not LLM)
- Max 5 skills per context to prevent bloat
- <100ms latency requirement
- Graceful degradation (missing skills don't block)
- Reuses existing skill_loader.py infrastructure

Pattern Categories:
- security: auth, token, password, JWT, encryption
- api: REST, endpoint, API, HTTP
- database: SQL, migration, schema, ORM
- git: commit, push, branch, merge, PR
- testing: test, unittest, pytest, TDD
- python: Python, type hints, docstring, PEP

Usage:
    from context_skill_injector import get_context_skill_injection

    # Get formatted skill content for a prompt
    skill_content = get_context_skill_injection("implement secure API endpoint")

    # Or use individual functions
    patterns = detect_context_patterns("implement JWT auth")
    skills = select_skills_for_context("implement JWT auth")
"""

import re
import sys
from typing import Dict, List, Optional, Set

# ============================================================================
# Configuration
# ============================================================================

# Maximum skills to inject per context (prevents context bloat)
MAX_CONTEXT_SKILLS = 5

# Pattern definitions - each maps to a set of relevant skills
# Uses word boundaries (\b) to prevent partial matches
CONTEXT_PATTERNS = {
    "security": [
        r"\b(auth|authenticat\w*|authoriz\w*)\b",  # Matches authenticate, authentication, authorize, etc.
        r"\b(token|jwt|oauth|api.?key)\b",
        r"\b(password|secret|credential|encrypt)\b",
        r"\b(secure|security|vulnerability|exploit)\b",
        r"\b(login|logout|session|cookie)\b",
    ],
    "api": [
        r"\b(api|rest|endpoint|http)\b",
        r"\b(request|response|route|handler)\b",
        r"\b(get|post|put|delete|patch)\s+(request|endpoint|method)\b",
        r"\b(webhook|callback|async.?api)\b",
    ],
    "database": [
        r"\b(database|db|sql|query)\b",
        r"\b(migration|schema|table|column)\b",
        r"\b(orm|sqlalchemy|django.?orm|prisma)\b",
        r"\b(insert|update|delete|select)\s+(into|from|where)?\b",
        r"\b(postgresql|mysql|sqlite|mongodb)\b",
    ],
    "git": [
        r"\b(git|commit|push|pull|merge)\b",
        r"\b(branch|checkout|rebase|cherry.?pick)\b",
        r"\b(pull.?request|pr|merge.?request)\b",
        r"\b(stash|reset|revert|diff)\b",
    ],
    "testing": [
        r"\b(test|tests|testing|unittest)\b",
        r"\b(pytest|jest|mocha|jasmine)\b",
        r"\b(tdd|test.?driven|coverage)\b",
        r"\b(mock|stub|fixture|assert)\b",
        r"\b(integration.?test|unit.?test|e2e)\b",
    ],
    "python": [
        r"\b(python|py|python3)\b",
        r"\b(type.?hint|typing|annotations)\b",
        r"\b(docstring|pep|pep8|pep.?484)\b",
        r"\b(class|def|async.?def|decorator)\b",
        r"\b(import|from\s+\w+\s+import)\b",
    ],
}

# Maps pattern categories to skill names
# Skills must exist in plugins/autonomous-dev/skills/{skill-name}/SKILL.md
PATTERN_SKILL_MAP: Dict[str, List[str]] = {
    "security": ["security-patterns"],
    "api": ["api-design", "api-integration-patterns"],
    "database": ["database-design"],
    "git": ["git-workflow"],
    "testing": ["testing-guide"],
    "python": ["python-standards"],
}

# Priority order for skill selection when limit exceeded
PATTERN_PRIORITY = [
    "security",  # Security always first
    "testing",   # Tests are fundamental
    "api",       # API patterns common
    "database",  # Data layer
    "python",    # Language specifics
    "git",       # Operations
]


# ============================================================================
# Pattern Detection
# ============================================================================

def detect_context_patterns(user_prompt: Optional[str]) -> Set[str]:
    """
    Detect context patterns in user prompt.

    Scans the prompt for predefined regex patterns to identify
    relevant skill categories (security, api, database, etc.).

    Args:
        user_prompt: User's prompt text

    Returns:
        Set of pattern category names detected (e.g., {"security", "api"})

    Example:
        >>> detect_context_patterns("implement JWT authentication")
        {'security'}
        >>> detect_context_patterns("create REST API endpoint")
        {'api'}
    """
    if not user_prompt:
        return set()

    text = user_prompt.lower()
    detected = set()

    for category, patterns in CONTEXT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                detected.add(category)
                break  # One match per category is enough

    return detected


# ============================================================================
# Skill Selection
# ============================================================================

def select_skills_for_context(
    user_prompt: Optional[str],
    max_skills: int = MAX_CONTEXT_SKILLS,
) -> List[str]:
    """
    Select relevant skills based on context patterns in prompt.

    Detects patterns in the prompt, maps them to skills, and returns
    a prioritized list limited to max_skills to prevent context bloat.

    Args:
        user_prompt: User's prompt text
        max_skills: Maximum number of skills to return (default: 5)

    Returns:
        List of skill names to inject, ordered by priority

    Example:
        >>> select_skills_for_context("implement secure API")
        ['security-patterns', 'api-design', 'api-integration-patterns']
    """
    if not user_prompt:
        return []

    # Detect patterns
    patterns = detect_context_patterns(user_prompt)

    if not patterns:
        return []

    # Collect skills from detected patterns, respecting priority
    skills = []
    seen = set()

    for category in PATTERN_PRIORITY:
        if category in patterns:
            category_skills = PATTERN_SKILL_MAP.get(category, [])
            for skill in category_skills:
                if skill not in seen:
                    skills.append(skill)
                    seen.add(skill)
                    if len(skills) >= max_skills:
                        return skills

    return skills


# ============================================================================
# Integration with skill_loader
# ============================================================================

def get_context_skill_injection(
    user_prompt: Optional[str],
    max_skills: int = MAX_CONTEXT_SKILLS,
) -> str:
    """
    Get formatted skill content for context-based injection.

    Main entry point that combines pattern detection, skill selection,
    and skill loading into a single call. Returns formatted skill
    content ready to inject into context.

    Args:
        user_prompt: User's prompt text
        max_skills: Maximum number of skills to inject

    Returns:
        Formatted skill content string (XML-tagged) or empty string

    Example:
        >>> content = get_context_skill_injection("implement JWT auth")
        >>> print(content[:50])
        <skills>
        <skill name="security-patterns">...
    """
    if not user_prompt:
        return ""

    # Select skills based on context
    skills = select_skills_for_context(user_prompt, max_skills)

    if not skills:
        return ""

    # Try to load and format skills using skill_loader
    try:
        from skill_loader import load_skill_content, format_skills_for_prompt
    except ImportError:
        # skill_loader not available - graceful degradation
        return ""

    # Load skill content
    skill_contents = {}
    for skill_name in skills:
        content = load_skill_content(skill_name)
        if content:
            skill_contents[skill_name] = content

    if not skill_contents:
        return ""

    # Format for prompt injection
    return format_skills_for_prompt(skill_contents)


# ============================================================================
# Utility Functions
# ============================================================================

def get_pattern_categories() -> List[str]:
    """
    Get list of available pattern categories.

    Returns:
        List of pattern category names
    """
    return list(CONTEXT_PATTERNS.keys())


def get_skills_for_pattern(pattern: str) -> List[str]:
    """
    Get skills mapped to a specific pattern category.

    Args:
        pattern: Pattern category name (e.g., "security")

    Returns:
        List of skill names for that pattern
    """
    return PATTERN_SKILL_MAP.get(pattern, [])


# ============================================================================
# CLI Entry Point
# ============================================================================

def main():
    """CLI entry point for testing."""

    if len(sys.argv) < 2:
        print("Usage: python context_skill_injector.py <prompt>")
        print("Example: python context_skill_injector.py 'implement JWT auth'")
        sys.exit(1)

    prompt = " ".join(sys.argv[1:])

    print(f"Prompt: {prompt}")
    print()

    patterns = detect_context_patterns(prompt)
    print(f"Detected patterns: {patterns}")

    skills = select_skills_for_context(prompt)
    print(f"Selected skills: {skills}")

    content = get_context_skill_injection(prompt)
    if content:
        print(f"\nSkill content length: {len(content)} chars")
        print(f"First 200 chars:\n{content[:200]}...")
    else:
        print("\nNo skill content loaded")


if __name__ == "__main__":
    main()
