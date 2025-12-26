#!/usr/bin/env python3
"""
Validate Settings Template Hooks - Pre-commit Hook

Ensures hooks referenced in global_settings_template.json actually exist
in the hooks directory. Prevents "hook not found" errors after install.

Usage:
    python3 validate_settings_hooks.py

Exit Codes:
    0 - All referenced hooks exist
    1 - Some hooks are missing
"""

import json
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


def extract_hook_files(settings: dict) -> list[str]:
    """Extract hook file names from settings template.

    Returns:
        List of hook filenames (e.g., ['pre_tool_use.py', 'auto_git_workflow.py'])
    """
    hooks = []

    hooks_config = settings.get("hooks", {})
    for lifecycle, matchers in hooks_config.items():
        if not isinstance(matchers, list):
            continue
        for matcher in matchers:
            if not isinstance(matcher, dict):
                continue
            for hook in matcher.get("hooks", []):
                if not isinstance(hook, dict):
                    continue
                command = hook.get("command", "")
                # Extract hook filename from command like:
                # "python3 ~/.claude/hooks/pre_tool_use.py"
                # "MCP_AUTO_APPROVE=true python3 ~/.claude/hooks/pre_tool_use.py"
                match = re.search(r'hooks/([a-z_]+\.py)', command)
                if match:
                    hooks.append(match.group(1))

    return hooks


def validate_settings_hooks() -> tuple[bool, list[str]]:
    """Validate all hooks in settings template exist AND are in install manifest.

    IMPORTANT: Hooks must be both:
    1. Present in source (plugins/autonomous-dev/hooks/)
    2. Listed in install_manifest.json (so they get installed to ~/.claude/hooks/)

    Returns:
        Tuple of (success, list of error messages)
    """
    project_root = get_project_root()
    plugin_dir = project_root / "plugins" / "autonomous-dev"

    # Load settings template
    template_path = plugin_dir / "config" / "global_settings_template.json"
    if not template_path.exists():
        return True, []  # No template, nothing to validate

    try:
        settings = json.loads(template_path.read_text())
    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON in settings template: {e}"]

    # Load install manifest
    manifest_path = plugin_dir / "config" / "install_manifest.json"
    manifest_hooks = set()
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
            manifest_hooks = {
                Path(p).name
                for p in manifest.get("components", {}).get("hooks", {}).get("files", [])
            }
        except json.JSONDecodeError:
            pass  # Will be caught by other validation

    # Extract referenced hooks
    referenced_hooks = extract_hook_files(settings)
    if not referenced_hooks:
        return True, []  # No hooks referenced

    # Check each hook exists in source AND manifest
    hooks_dir = plugin_dir / "hooks"
    errors = []

    for hook_file in referenced_hooks:
        hook_path = hooks_dir / hook_file

        # Check 1: Exists in source
        if not hook_path.exists():
            errors.append(f"{hook_file}: Missing from source directory")
            continue

        # Check 2: Listed in manifest (so it gets installed)
        if hook_file not in manifest_hooks:
            errors.append(
                f"{hook_file}: Exists in source but NOT in install_manifest.json! "
                f"This hook won't be installed to ~/.claude/hooks/"
            )

    return len(errors) == 0, errors


def main() -> int:
    """Main entry point."""
    success, missing = validate_settings_hooks()

    if success:
        print("✅ All settings template hooks exist")
        return 0
    else:
        print("❌ Settings template references missing hooks!")
        print("")
        print("Missing hooks:")
        for hook in sorted(missing):
            print(f"  - {hook}")
        print("")
        print("Fix: Either create the hook or update global_settings_template.json")
        return 1


if __name__ == "__main__":
    sys.exit(main())
