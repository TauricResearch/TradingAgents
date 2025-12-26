#!/usr/bin/env python3
"""
Auto-sync hook for plugin development.

Automatically syncs local plugin changes to installed location before commits.
This prevents the "two-location hell" where developers edit one location but
Claude Code reads from another.

Exit codes:
  0: Allow commit, no message (sync successful or not needed)
  1: Allow commit, show warning (sync recommended)
  2: Block commit, show error (sync failed, must fix)
"""

import json
import subprocess
import sys
from pathlib import Path


def is_plugin_development_mode():
    """Check if we're developing the autonomous-dev plugin itself."""
    # Check if we're in the plugins/autonomous-dev directory structure
    cwd = Path.cwd()

    # Look for plugin.json in .claude-plugin/ subdirectory
    plugin_json = cwd / "plugins" / "autonomous-dev" / ".claude-plugin" / "plugin.json"

    return plugin_json.exists()


def is_plugin_installed():
    """Check if the plugin is installed in Claude Code."""
    home = Path.home()
    installed_plugins_file = home / ".claude" / "plugins" / "installed_plugins.json"

    if not installed_plugins_file.exists():
        return False

    try:
        with open(installed_plugins_file) as f:
            config = json.load(f)

        # Look for autonomous-dev plugin
        for plugin_key in config.get("plugins", {}).keys():
            if plugin_key.startswith("autonomous-dev@"):
                return True
    except (json.JSONDecodeError, PermissionError, FileNotFoundError):
        return False

    return False


def get_modified_plugin_files():
    """Get list of modified files in plugins/autonomous-dev/."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--", "plugins/autonomous-dev/"],
            capture_output=True,
            text=True,
            check=True
        )

        files = [f for f in result.stdout.strip().split('\n') if f]

        # Filter to files that matter (not tests, not docs/dev)
        relevant_files = []
        for f in files:
            if any(x in f for x in ["agents/", "commands/", "hooks/", "lib/"]):
                relevant_files.append(f)

        return relevant_files
    except subprocess.CalledProcessError:
        return []


def auto_sync():
    """Automatically sync changes to installed plugin."""
    sync_script = Path("plugins/autonomous-dev/hooks/sync_to_installed.py")

    if not sync_script.exists():
        return False, "Sync script not found"

    try:
        result = subprocess.run(
            ["python3", str(sync_script)],
            capture_output=True,
            text=True,
            check=True,
            timeout=10
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, f"Sync failed: {e.stderr}"
    except subprocess.TimeoutExpired:
        return False, "Sync timed out"
    except Exception as e:
        return False, f"Sync error: {str(e)}"


def main():
    """Main hook logic."""

    # Only run for plugin development
    if not is_plugin_development_mode():
        sys.exit(0)  # Not plugin dev, allow commit

    # Check if plugin is installed
    if not is_plugin_installed():
        # Plugin not installed, no need to sync
        sys.exit(0)

    # Check if we're modifying plugin files
    modified_files = get_modified_plugin_files()

    if not modified_files:
        # No plugin files modified, allow commit
        sys.exit(0)

    # Relevant plugin files modified and plugin installed - auto-sync
    print("🔄 Auto-syncing plugin changes to installed location...", file=sys.stderr)
    print(f"   Modified files: {len(modified_files)}", file=sys.stderr)
    print("", file=sys.stderr)

    success, message = auto_sync()

    if success:
        print("✅ Plugin changes synced to installed location", file=sys.stderr)
        print("⚠️  RESTART REQUIRED: Quit and restart Claude Code to see changes", file=sys.stderr)
        print("", file=sys.stderr)
        sys.exit(0)  # Allow commit
    else:
        print("❌ Auto-sync failed!", file=sys.stderr)
        print(file=sys.stderr)
        print(message, file=sys.stderr)
        print(file=sys.stderr)
        print("Options:", file=sys.stderr)
        print("  1. Run manually: python plugins/autonomous-dev/hooks/sync_to_installed.py", file=sys.stderr)
        print("  2. Skip sync: git commit --no-verify", file=sys.stderr)
        sys.exit(2)  # Block commit


if __name__ == "__main__":
    main()
