#!/usr/bin/env python3
"""
Validate All Hooks Documented - Pre-commit Hook

Ensures every hook in hooks/ directory is documented in docs/HOOKS.md.
Blocks commits if new hooks are added without documentation.

Usage:
    python3 validate_hooks_documented.py

Exit Codes:
    0 - All hooks documented
    1 - Some hooks missing from docs
"""

import re
import sys
from pathlib import Path


def get_project_root() -> Path:
    """Find project root by looking for .git directory."""
    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return Path.cwd()


def get_documented_hooks(hooks_md: Path) -> set[str]:
    """Extract hook names documented in HOOKS.md.

    Returns:
        Set of hook names (without .py extension)
    """
    if not hooks_md.exists():
        return set()

    content = hooks_md.read_text()
    # Match "### hook_name.py" or "### hook_name"
    pattern = r'^###\s+([a-z_]+)(?:\.py)?'
    matches = re.findall(pattern, content, re.MULTILINE)
    return set(matches)


def get_source_hooks(hooks_dir: Path) -> set[str]:
    """Get all hook names from source directory.

    Returns:
        Set of hook names (without .py extension)
    """
    if not hooks_dir.exists():
        return set()

    hooks = set()
    for f in hooks_dir.glob("*.py"):
        if f.name.startswith("test_") or f.name == "__init__.py":
            continue
        hooks.add(f.stem)
    return hooks


def validate_hooks_documented() -> tuple[bool, list[str]]:
    """Validate all hooks are documented in HOOKS.md.

    Returns:
        Tuple of (success, list of undocumented hooks)
    """
    project_root = get_project_root()
    plugin_dir = project_root / "plugins" / "autonomous-dev"
    hooks_dir = plugin_dir / "hooks"
    hooks_md = project_root / "docs" / "HOOKS.md"

    if not hooks_md.exists():
        return True, []  # No docs file, skip validation

    source_hooks = get_source_hooks(hooks_dir)
    documented_hooks = get_documented_hooks(hooks_md)

    # Find undocumented hooks
    undocumented = source_hooks - documented_hooks

    return len(undocumented) == 0, sorted(undocumented)


def main() -> int:
    """Main entry point."""
    success, undocumented = validate_hooks_documented()

    if success:
        print("✅ All hooks documented in HOOKS.md")
        return 0
    else:
        print("❌ Undocumented hooks detected!")
        print("")
        print(f"Missing from docs/HOOKS.md ({len(undocumented)}):")
        for hook in undocumented:
            print(f"  - {hook}.py")
        print("")
        print("Fix: Add documentation for each hook to docs/HOOKS.md")
        print("Format:")
        print("  ### hook_name.py")
        print("  **Purpose**: What it does")
        print("  **Lifecycle**: PreCommit/SubagentStop/etc")
        return 1


if __name__ == "__main__":
    sys.exit(main())
