#!/usr/bin/env python3
"""
Auto-bootstrap hook for autonomous-dev plugin.

This SessionStart hook automatically copies essential plugin commands to the
project's .claude/commands/ directory if they don't exist, solving the
"bootstrap paradox" where /setup can't be run because it doesn't exist yet.

Runs on SessionStart - checks if bootstrap is needed and runs it automatically.
"""

import os
import shutil
import sys
from pathlib import Path


def is_bootstrap_needed(project_dir: Path) -> bool:
    """Check if project needs bootstrapping."""
    commands_dir = project_dir / ".claude" / "commands"

    # Check if .claude directory exists
    if not commands_dir.exists():
        return True

    # Check if essential commands exist
    essential_commands = ["setup.md", "auto-implement.md"]
    for cmd in essential_commands:
        if not (commands_dir / cmd).exists():
            return True

    return False


def find_plugin_dir() -> Path:
    """Find the installed plugin directory."""
    home = Path.home()

    # Try to find in installed plugins
    plugin_path = home / ".claude" / "plugins" / "marketplaces" / "autonomous-dev" / "plugins" / "autonomous-dev"
    if plugin_path.exists():
        return plugin_path

    # Fallback: check if running from plugin directory itself
    current = Path(__file__).resolve()
    if "autonomous-dev" in str(current):
        # Navigate up to find plugin root
        for parent in current.parents:
            if (parent / ".claude-plugin" / "plugin.json").exists():
                return parent

    return None


def bootstrap_project(project_dir: Path, plugin_dir: Path) -> bool:
    """Bootstrap the project by copying essential plugin files."""

    # Ensure .claude directory exists
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)

    # Ensure commands directory exists
    commands_dir = claude_dir / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)

    # Copy all commands
    plugin_commands = plugin_dir / "commands"
    if not plugin_commands.exists():
        return False

    copied = []
    for cmd_file in plugin_commands.glob("*.md"):
        target = commands_dir / cmd_file.name
        shutil.copy2(cmd_file, target)
        copied.append(cmd_file.name)

    # Create a marker file to track bootstrap
    marker = claude_dir / ".autonomous-dev-bootstrapped"
    marker.write_text(f"Bootstrapped with plugin version: autonomous-dev\n")

    # Write to stderr so it appears in Claude Code output
    print(f"✅ Auto-bootstrapped autonomous-dev plugin", file=sys.stderr)
    print(f"   Copied {len(copied)} commands to .claude/commands/", file=sys.stderr)
    print(f"   Run /setup to complete configuration", file=sys.stderr)

    return True


def main():
    """Main hook entry point."""

    # Get project directory from environment or cwd
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))

    # Check if bootstrap is needed
    if not is_bootstrap_needed(project_dir):
        # Already bootstrapped, exit silently
        return 0

    # Find plugin directory
    plugin_dir = find_plugin_dir()
    if not plugin_dir:
        print("⚠️  Could not locate autonomous-dev plugin directory", file=sys.stderr)
        return 1

    # Bootstrap the project
    success = bootstrap_project(project_dir, plugin_dir)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
