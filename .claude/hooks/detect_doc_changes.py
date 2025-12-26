#!/usr/bin/env python3
"""
Strict Documentation Update Enforcement Hook

Detects when code changes require documentation updates and BLOCKS commits
if required docs aren't updated.

This is a PRE-COMMIT hook that prevents README.md and other docs from drifting
out of sync with code changes.

Usage:
    # As pre-commit hook (automatic)
    python detect_doc_changes.py

    # Manual check
    python detect_doc_changes.py --check

Exit codes:
    0: All required docs updated (or no doc updates needed)
    1: Missing doc updates - commit BLOCKED
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple
import fnmatch
import re


def get_plugin_root() -> Path:
    """Get the plugin root directory."""
    # This script is in plugins/autonomous-dev/hooks/
    return Path(__file__).parent.parent


def get_repo_root() -> Path:
    """Get the repository root directory."""
    return get_plugin_root().parent.parent


def load_registry() -> Dict:
    """Load the doc change registry configuration."""
    plugin_root = get_plugin_root()
    registry_path = plugin_root / "config" / "doc_change_registry.json"

    if not registry_path.exists():
        print(f"⚠️  Warning: Registry not found at {registry_path}")
        return {"mappings": [], "exclusions": []}

    with open(registry_path) as f:
        return json.load(f)


def get_staged_files() -> List[str]:
    """Get list of files staged for commit."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            check=True
        )
        return [f.strip() for f in result.stdout.split("\n") if f.strip()]
    except subprocess.CalledProcessError:
        print("❌ Error: Could not get staged files (are you in a git repository?)")
        sys.exit(1)


def is_excluded(file_path: str, exclusions: List[str]) -> bool:
    """Check if file matches any exclusion pattern."""
    for pattern in exclusions:
        if fnmatch.fnmatch(file_path, pattern):
            return True
    return False


def match_pattern(file_path: str, pattern: str) -> bool:
    """Check if file matches a pattern (supports wildcards and directory patterns)."""
    # Convert pattern to regex-friendly format
    # commands/*.md → commands/[^/]+\.md$
    # skills/*/ → skills/[^/]+/

    regex_pattern = pattern.replace("**", ".*")
    regex_pattern = regex_pattern.replace("*", "[^/]+")
    regex_pattern = regex_pattern.replace("?", "[^/]")

    # Ensure pattern matches from appropriate position
    if not regex_pattern.startswith("^"):
        regex_pattern = ".*" + regex_pattern
    if not regex_pattern.endswith("$"):
        regex_pattern = regex_pattern + ".*"

    return bool(re.match(regex_pattern, file_path))


def find_required_docs(
    staged_files: List[str],
    registry: Dict
) -> Dict[str, Set[str]]:
    """
    Find which docs are required to be updated based on staged code changes.

    Returns:
        Dict mapping code file → set of required doc files
    """
    exclusions = registry.get("exclusions", [])
    mappings = registry.get("mappings", [])
    required_docs_map = {}

    for file_path in staged_files:
        # Skip excluded files
        if is_excluded(file_path, exclusions):
            continue

        # Check each mapping rule
        for mapping in mappings:
            pattern = mapping["code_pattern"]

            if match_pattern(file_path, pattern):
                required_docs = set(mapping["required_docs"])

                if file_path not in required_docs_map:
                    required_docs_map[file_path] = {
                        "docs": required_docs,
                        "description": mapping["description"],
                        "suggestion": mapping["suggestion"]
                    }
                else:
                    # Merge with existing requirements
                    required_docs_map[file_path]["docs"].update(required_docs)

    return required_docs_map


def check_doc_updates(
    required_docs_map: Dict[str, Set[str]],
    staged_files: Set[str]
) -> Tuple[bool, List[Dict]]:
    """
    Check if all required docs are staged for commit.

    Returns:
        (all_docs_updated, violations)
        - all_docs_updated: True if all required docs are staged
        - violations: List of dicts with code_file, missing_docs, description, suggestion
    """
    violations = []

    for code_file, requirements in required_docs_map.items():
        required_docs = requirements["docs"]
        missing_docs = required_docs - staged_files

        if missing_docs:
            violations.append({
                "code_file": code_file,
                "missing_docs": sorted(list(missing_docs)),
                "description": requirements["description"],
                "suggestion": requirements["suggestion"]
            })

    return (len(violations) == 0, violations)


def print_violations(violations: List[Dict]):
    """Print helpful error message for documentation violations."""
    print("\n" + "=" * 80)
    print("❌ COMMIT BLOCKED: Required documentation updates missing!")
    print("=" * 80)
    print()
    print("You changed code that requires documentation updates.")
    print("The following documentation files must be updated:\n")

    for i, violation in enumerate(violations, 1):
        print(f"{i}. Code Change: {violation['code_file']}")
        print(f"   Why: {violation['description']}")
        print(f"   Missing Docs:")
        for doc in violation['missing_docs']:
            print(f"     - {doc}")
        print(f"   Suggestion: {violation['suggestion']}")
        print()

    print("=" * 80)
    print("How to fix:")
    print("=" * 80)
    print()
    print("1. Update the required documentation files listed above")
    print("2. Stage the updated docs:")
    print("   git add <doc-files>")
    print("3. Retry your commit:")
    print("   git commit")
    print()
    print("Validation:")
    print("  Run: python plugins/autonomous-dev/hooks/validate_docs_consistency.py")
    print("  to verify all docs are consistent")
    print()
    print("=" * 80)


def main():
    """Main entry point for doc change detection hook."""
    # Load registry
    registry = load_registry()

    if not registry.get("mappings"):
        # No mappings configured - allow commit
        sys.exit(0)

    # Get staged files
    staged_files = get_staged_files()

    if not staged_files:
        # No files staged - nothing to check
        sys.exit(0)

    staged_set = set(staged_files)

    # Find required docs based on code changes
    required_docs_map = find_required_docs(staged_files, registry)

    if not required_docs_map:
        # No code changes that require doc updates
        sys.exit(0)

    # Check if all required docs are updated
    all_updated, violations = check_doc_updates(required_docs_map, staged_set)

    if all_updated:
        print("✅ All required documentation updates included in commit")
        sys.exit(0)
    else:
        print_violations(violations)
        sys.exit(1)


if __name__ == "__main__":
    main()
