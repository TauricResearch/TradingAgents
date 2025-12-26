#!/usr/bin/env python3
"""
Validate that slash commands document their --flags in the frontmatter.

This pre-commit hook ensures that commands with --flag options in their body
have those flags documented in the frontmatter (description and argument_hint
fields) for proper autocomplete display in Claude Code.

Exit codes:
- 0: All flags documented OR no flags found OR not applicable
- 1: Warning - undocumented flags found (non-blocking)
- Never exits 2 (this is non-critical validation)

Run this as part of pre-commit to catch missing flag documentation.

Author: implementer agent
Date: 2025-12-14
Issue: GitHub #133 - Add pre-commit hook for command frontmatter flag validation
Related: Issue #131 - Fixed frontmatter for /align, /batch-implement, /create-issue, /sync
"""

import re
import sys
from pathlib import Path
from typing import Optional


# False positive flags that should be ignored
_FALSE_POSITIVE_FLAGS = frozenset([
    "--help",
    "--version",
    "-h",
    "-v",
    "--flag",  # Generic example flag
    "--option",  # Generic example option
    "--example",  # Generic example
    "--your-flag",  # Documentation placeholder
    "--some-flag",  # Documentation placeholder
])


def get_false_positive_flags() -> frozenset:
    """
    Return set of flags that should be ignored (false positives).

    These are common flags used in documentation examples that don't
    need to be documented in frontmatter.

    Returns:
        Frozen set of flag strings to ignore
    """
    return _FALSE_POSITIVE_FLAGS


def extract_frontmatter(content: str) -> Optional[str]:
    """
    Extract YAML frontmatter from markdown content.

    Frontmatter is content between --- markers at the start of the file.

    Args:
        content: Full markdown file content

    Returns:
        Frontmatter string (without the --- markers), or None if not found
    """
    # Pattern: starts with ---, captures content (including empty) until next ---
    # Allow for empty frontmatter (just two --- lines)
    pattern = r'^---\s*\n(.*?)\n?---\s*\n'
    match = re.search(pattern, content, re.DOTALL | re.MULTILINE)

    if match:
        return match.group(1)
    return None


def remove_code_blocks(content: str) -> str:
    """
    Remove code blocks from markdown content.

    Removes both fenced code blocks (```...```) and inline code (`...`)
    to prevent false positive flag detection from code examples.

    Args:
        content: Markdown content

    Returns:
        Content with code blocks removed
    """
    # Remove fenced code blocks (``` blocks with optional language)
    # Use non-greedy matching to handle multiple blocks
    content = re.sub(r'```[^\n]*\n.*?```', '', content, flags=re.DOTALL)

    # Remove inline code (`code`)
    content = re.sub(r'`[^`]+`', '', content)

    return content


def extract_flags_from_body(content: str) -> list[str]:
    """
    Extract CLI flags (--flag-name) from markdown body.

    Removes code blocks first to avoid false positives from examples.
    Only extracts double-dash flags (--flag), not single-dash (-f).

    Args:
        content: Markdown body content (after frontmatter)

    Returns:
        List of unique flags found (e.g., ["--verbose", "--output"])
    """
    if not content:
        return []

    # Remove code blocks to avoid false positives
    clean_content = remove_code_blocks(content)

    # Pattern: --word(-word)* with word boundary
    # Matches: --verbose, --dry-run, --no-verify
    pattern = r'--\w+(?:-\w+)*\b'

    matches = re.findall(pattern, clean_content)

    # Deduplicate and return as list
    return list(set(matches))


def check_flags_in_frontmatter(flags: list[str], frontmatter: str) -> list[str]:
    """
    Check which flags are missing from frontmatter.

    Checks both description and argument_hint fields.
    Filters out false positive flags (--help, --version, etc.).

    Args:
        flags: List of flags found in body
        frontmatter: YAML frontmatter content

    Returns:
        List of flags that are missing from frontmatter
    """
    if not flags or not frontmatter:
        return []

    false_positives = get_false_positive_flags()
    missing = []

    for flag in flags:
        # Skip false positives
        if flag in false_positives:
            continue

        # Check if flag appears anywhere in frontmatter
        # (description or argument_hint fields)
        if flag not in frontmatter:
            missing.append(flag)

    return sorted(missing)


def validate_command_file(filepath: Path) -> list[str]:
    """
    Validate a command file for undocumented flags.

    Checks if all --flags used in the body are documented in the
    frontmatter (description or argument_hint fields).

    Args:
        filepath: Path to the command .md file

    Returns:
        List of warning messages (empty if all valid)
    """
    warnings = []

    try:
        content = filepath.read_text(encoding='utf-8')
    except Exception as e:
        return [f"Could not read file: {e}"]

    # Extract frontmatter
    frontmatter = extract_frontmatter(content)

    if frontmatter is None:
        # Check if file has flags that need documentation
        body_flags = extract_flags_from_body(content)
        real_flags = [f for f in body_flags if f not in get_false_positive_flags()]
        if real_flags:
            return [f"No frontmatter found but file contains flags: {', '.join(real_flags)}"]
        return []

    # Get body content (everything after frontmatter)
    # Find the end of frontmatter and get the rest
    frontmatter_end = re.search(r'^---\s*\n.*?\n---\s*\n', content, re.DOTALL | re.MULTILINE)
    if frontmatter_end:
        body = content[frontmatter_end.end():]
    else:
        body = content

    # Extract flags from body
    flags = extract_flags_from_body(body)

    if not flags:
        return []  # No flags to validate

    # Check which flags are missing from frontmatter
    missing = check_flags_in_frontmatter(flags, frontmatter)

    if missing:
        warnings.append(f"Undocumented flags: {', '.join(missing)}")

    return warnings


def main():
    """
    Main entry point for the pre-commit hook.

    Scans all command files in plugins/autonomous-dev/commands/
    and reports any undocumented flags.

    Exit codes:
    - 0: All valid or not applicable
    - 1: Warnings found (non-blocking)
    """
    # Find commands directory relative to this script or cwd
    # Script is at: plugins/autonomous-dev/hooks/validate_command_frontmatter_flags.py
    # Commands are at: plugins/autonomous-dev/commands/

    # Try relative to script first
    script_dir = Path(__file__).parent
    plugin_dir = script_dir.parent
    commands_dir = plugin_dir / "commands"

    # If not found, try relative to cwd (for testing)
    if not commands_dir.exists():
        cwd = Path.cwd()
        commands_dir = cwd / "plugins" / "autonomous-dev" / "commands"

    if not commands_dir.exists():
        # Not applicable (not in a project with commands)
        print("ℹ️  Commands directory not found, skipping validation")
        sys.exit(0)

    print("=" * 70)
    print("COMMAND FRONTMATTER FLAG VALIDATION")
    print("=" * 70)
    print()

    command_files = sorted(commands_dir.glob("*.md"))

    if not command_files:
        print("ℹ️  No command files found")
        sys.exit(0)

    valid = []
    with_warnings = []

    for filepath in command_files:
        warnings = validate_command_file(filepath)

        if not warnings:
            valid.append(filepath.name)
            print(f"✅ {filepath.name}")
        else:
            with_warnings.append((filepath.name, warnings))
            print(f"⚠️  {filepath.name}")
            for warning in warnings:
                print(f"   {warning}")

    print()
    print("=" * 70)
    print(f"RESULTS: {len(valid)} valid, {len(with_warnings)} with warnings")
    print("=" * 70)

    if with_warnings:
        print()
        print("COMMANDS WITH UNDOCUMENTED FLAGS:")
        print()
        for name, warnings in with_warnings:
            print(f"  ⚠️  {name}")
            for warning in warnings:
                print(f"     {warning}")
            print()

        print("TO FIX:")
        print()
        print("  Add missing flags to the frontmatter description or argument_hint.")
        print()
        print("  Example:")
        print('    description: "Command with --flag1 and --flag2 options"')
        print('    argument_hint: "--flag1 [--flag2]"')
        print()
        print("  See Issue #131 for examples of properly documented frontmatter.")
        print()

        # Exit 1 = warning (non-blocking)
        sys.exit(1)
    else:
        print()
        print("✅ ALL COMMANDS HAVE PROPERLY DOCUMENTED FLAGS!")
        print()
        sys.exit(0)


if __name__ == "__main__":
    main()
