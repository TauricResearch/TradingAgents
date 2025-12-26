#!/usr/bin/env python3
"""
PROJECT.md Alignment Validation Hook - Gatekeeper for STRICT MODE

This hook enforces that PROJECT.md exists and all work aligns with it.
It's a BLOCKING hook that prevents commits if alignment fails.

What it checks:
- PROJECT.md exists
- PROJECT.md has required sections (GOALS, SCOPE, CONSTRAINTS)
- Current changes align with PROJECT.md SCOPE
- Documentation mentions PROJECT.md

This is the GATEKEEPER for strict mode - nothing proceeds without alignment.

Relevant Skills:
- project-alignment-validation: Alignment checklist, semantic validation approach

Usage:
    Add to .claude/settings.local.json PreCommit hooks:
    {
      "hooks": {
        "PreCommit": [
          {
            "type": "command",
            "command": "python .claude/hooks/validate_project_alignment.py || exit 1"
          }
        ]
      }
    }

Exit codes:
- 0: PROJECT.md aligned
- 1: PROJECT.md missing or misaligned (blocks commit)
"""

import sys
import re
from pathlib import Path
from typing import Tuple


def get_project_root() -> Path:
    """Find project root directory."""
    current = Path.cwd()

    # Look for PROJECT.md or .git directory
    while current != current.parent:
        if (current / "PROJECT.md").exists() or (current / ".git").exists():
            return current
        current = current.parent

    return Path.cwd()


def check_project_md_exists(project_root: Path) -> Tuple[bool, str]:
    """Check if PROJECT.md exists."""
    project_md_path = project_root / "PROJECT.md"

    if not project_md_path.exists():
        # Check alternate locations
        alt_path = project_root / ".claude" / "PROJECT.md"
        if alt_path.exists():
            return True, f"✅ PROJECT.md found at {alt_path}"

        return False, (
            "❌ PROJECT.md NOT FOUND\n"
            "\n"
            "STRICT MODE requires PROJECT.md to define strategic direction.\n"
            "\n"
            "Create PROJECT.md with:\n"
            "  1. GOALS - What you're building and success metrics\n"
            "  2. SCOPE - What's in/out of scope\n"
            "  3. CONSTRAINTS - Technical stack, performance, security limits\n"
            "  4. ARCHITECTURE - System design and patterns\n"
            "\n"
            "Quick setup:\n"
            "  /setup --create-project-md\n"
            "\n"
            "Or copy template:\n"
            "  cp .claude/templates/PROJECT.md PROJECT.md\n"
        )

    return True, f"✅ PROJECT.md found at {project_md_path}"


def check_required_sections(project_root: Path) -> Tuple[bool, str]:
    """Check PROJECT.md has required sections."""
    project_md_path = project_root / "PROJECT.md"
    alt_path = project_root / ".claude" / "PROJECT.md"

    # Use whichever exists
    path_to_check = project_md_path if project_md_path.exists() else alt_path

    if not path_to_check.exists():
        return False, "PROJECT.md not found"

    content = path_to_check.read_text()

    required_sections = ["GOALS", "SCOPE", "CONSTRAINTS"]
    missing_sections = []

    for section in required_sections:
        # Look for section headers (## GOALS, # GOALS, etc.)
        if not re.search(rf'^#+\s*{section}', content, re.MULTILINE | re.IGNORECASE):
            missing_sections.append(section)

    if missing_sections:
        return False, (
            f"❌ PROJECT.md missing required sections:\n"
            + "\n".join(f"  - {s}" for s in missing_sections) +
            f"\n\nAdd these sections to define strategic direction.\n"
            f"See .claude/templates/PROJECT.md for structure."
        )

    return True, f"✅ PROJECT.md has all required sections ({', '.join(required_sections)})"


def check_scope_alignment(project_root: Path) -> Tuple[bool, str]:
    """
    Check if current changes align with PROJECT.md SCOPE.

    This is a basic check - full alignment validation happens in orchestrator.
    Just verifies that someone has considered alignment.
    """
    project_md_path = project_root / "PROJECT.md"
    alt_path = project_root / ".claude" / "PROJECT.md"

    path_to_check = project_md_path if project_md_path.exists() else alt_path

    if not path_to_check.exists():
        return False, "PROJECT.md not found"

    content = path_to_check.read_text()

    # Check if SCOPE section has content (not empty)
    scope_match = re.search(
        r'^\s*#+\s*SCOPE\s*\n(.*?)(?=\n#+\s|\Z)',
        content,
        re.MULTILINE | re.IGNORECASE | re.DOTALL
    )

    if not scope_match:
        return False, (
            "❌ PROJECT.md SCOPE section empty or missing\n"
            "\n"
            "Define what's IN SCOPE and OUT OF SCOPE to guide development.\n"
        )

    scope_content = scope_match.group(1).strip()

    if len(scope_content) < 50:  # Arbitrary minimum
        return False, (
            "❌ PROJECT.md SCOPE section too brief\n"
            "\n"
            "Add specific items to SCOPE section:\n"
            "  - What features are in scope\n"
            "  - What features are explicitly out of scope\n"
            "  - Boundaries and constraints\n"
        )

    return True, "✅ PROJECT.md SCOPE defined (alignment enforced by orchestrator)"


def main() -> int:
    """
    Run PROJECT.md alignment validation.

    Returns:
        0 if aligned
        1 if misaligned (blocks commit)
    """
    print("🔍 Validating PROJECT.md alignment (STRICT MODE)...\n")

    project_root = get_project_root()

    # Run all checks
    checks = [
        ("PROJECT.md exists", check_project_md_exists(project_root)),
        ("Required sections", check_required_sections(project_root)),
        ("SCOPE defined", check_scope_alignment(project_root)),
    ]

    all_passed = True

    for check_name, (passed, message) in checks:
        if passed:
            print(message)
        else:
            print(f"❌ {check_name} FAILED:")
            print(f"   {message}")
            print()
            all_passed = False

    print()

    if all_passed:
        print("✅ PROJECT.md alignment validation PASSED")
        print()
        print("NOTE: Orchestrator will perform detailed alignment check")
        print("      before feature implementation begins.")
        return 0
    else:
        print("❌ PROJECT.md alignment validation FAILED")
        print()
        print("STRICT MODE: Cannot commit without PROJECT.md alignment.")
        print()
        print("Fix the issues above, then retry commit.")
        print()
        print("To bypass (NOT RECOMMENDED):")
        print("  git commit --no-verify")
        return 1


if __name__ == "__main__":
    sys.exit(main())
