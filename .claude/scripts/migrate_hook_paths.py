#!/usr/bin/env python3
"""
Migration script for Issue #113: Make PreToolUse hook path dynamic.

Detects hardcoded absolute paths in settings.json and replaces them with
portable ~/.claude/hooks/pre_tool_use.py path.

Usage:
    python migrate_hook_paths.py
    python migrate_hook_paths.py --settings-path ~/.claude/settings.json
    python migrate_hook_paths.py --dry-run
    python migrate_hook_paths.py --verbose
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional


def detect_hardcoded_paths(settings: Dict[str, Any]) -> list:
    """
    Detect hardcoded absolute paths in settings.

    Args:
        settings: Settings dictionary to check

    Returns:
        List of detected hardcoded path patterns
    """
    hardcoded_patterns = []

    if "hooks" not in settings:
        return hardcoded_patterns

    for hook_type, hook_configs in settings["hooks"].items():
        if not isinstance(hook_configs, list):
            continue

        for hook_config in hook_configs:
            if not isinstance(hook_config, dict):
                continue

            hooks = hook_config.get("hooks", [])
            if not isinstance(hooks, list):
                continue

            for hook in hooks:
                if not isinstance(hook, dict):
                    continue

                command = hook.get("command", "")

                # Detect various hardcoded path patterns
                # Match any absolute path ending in autonomous-dev/plugins/autonomous-dev/hooks/pre_tool_use.py
                patterns = [
                    r'/Users/[^/\s]+/.*?autonomous-dev/plugins/autonomous-dev/hooks/pre_tool_use\.py',
                    r'/home/[^/\s]+/.*?autonomous-dev/plugins/autonomous-dev/hooks/pre_tool_use\.py',
                    r'/opt/.*?autonomous-dev/plugins/autonomous-dev/hooks/pre_tool_use\.py',
                    r'[A-Za-z]:[/\\].*?autonomous-dev[/\\]plugins[/\\]autonomous-dev[/\\]hooks[/\\]pre_tool_use\.py',
                ]

                for pattern in patterns:
                    if re.search(pattern, command):
                        hardcoded_patterns.append({
                            "hook_type": hook_type,
                            "command": command,
                            "pattern": pattern
                        })

    return hardcoded_patterns


def migrate_settings_file(settings_path: Path, dry_run: bool = False, verbose: bool = False) -> Dict[str, Any]:
    """
    Migrate settings.json to use portable hook paths.

    Args:
        settings_path: Path to settings.json file
        dry_run: If True, don't modify files (just report)
        verbose: If True, output detailed information

    Returns:
        Dictionary with migration results:
        - migrated: bool (True if changes were made)
        - changes: int (number of paths migrated)
        - summary: str (human-readable summary)
        - backup_path: str or None (path to backup file)
    """
    result = {
        "migrated": False,
        "changes": 0,
        "summary": "",
        "backup_path": None
    }

    # Check if file exists
    if not settings_path.exists():
        result["summary"] = f"Settings file not found: {settings_path}"
        if verbose:
            print(f"❌ {result['summary']}")
        return result

    # Read settings
    try:
        settings = json.loads(settings_path.read_text())
    except json.JSONDecodeError as e:
        result["summary"] = f"Invalid JSON in settings file: {e}"
        if verbose:
            print(f"❌ {result['summary']}")
        return result
    except Exception as e:
        result["summary"] = f"Error reading settings file: {e}"
        if verbose:
            print(f"❌ {result['summary']}")
        return result

    # Detect hardcoded paths
    hardcoded = detect_hardcoded_paths(settings)

    if not hardcoded:
        result["summary"] = "All hook paths are already portable"
        if verbose:
            print(f"✅ {result['summary']}")
        return result

    if verbose:
        print(f"🔍 Found {len(hardcoded)} hardcoded path(s) to migrate")

    # Create backup before modifying (unless dry-run)
    if not dry_run:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = settings_path.parent / f"{settings_path.name}.backup.{timestamp}"
        shutil.copy2(settings_path, backup_path)
        result["backup_path"] = str(backup_path)
        if verbose:
            print(f"💾 Created backup: {backup_path}")

    # Migrate paths
    changes = 0
    portable_path = "~/.claude/hooks/pre_tool_use.py"

    if "hooks" in settings:
        for hook_type, hook_configs in settings["hooks"].items():
            if not isinstance(hook_configs, list):
                continue

            for hook_config in hook_configs:
                if not isinstance(hook_config, dict):
                    continue

                hooks = hook_config.get("hooks", [])
                if not isinstance(hooks, list):
                    continue

                for hook in hooks:
                    if not isinstance(hook, dict):
                        continue

                    command = hook.get("command", "")

                    # Replace hardcoded paths with portable path
                    patterns = [
                        r'/Users/[^/\s]+/.*?autonomous-dev/plugins/autonomous-dev/hooks/pre_tool_use\.py',
                        r'/home/[^/\s]+/.*?autonomous-dev/plugins/autonomous-dev/hooks/pre_tool_use\.py',
                        r'/opt/.*?autonomous-dev/plugins/autonomous-dev/hooks/pre_tool_use\.py',
                        r'[A-Za-z]:[/\\].*?autonomous-dev[/\\]plugins[/\\]autonomous-dev[/\\]hooks[/\\]pre_tool_use\.py',
                    ]

                    new_command = command
                    for pattern in patterns:
                        if re.search(pattern, new_command):
                            new_command = re.sub(pattern, portable_path, new_command)
                            changes += 1
                            if verbose:
                                print(f"🔄 Migrating {hook_type} hook")
                                print(f"   Old: {command}")
                                print(f"   New: {new_command}")

                    if new_command != command:
                        hook["command"] = new_command

    # Write migrated settings (unless dry-run)
    if changes > 0 and not dry_run:
        settings_path.write_text(json.dumps(settings, indent=2))
        result["migrated"] = True
        result["changes"] = changes
        result["summary"] = f"Successfully migrated {changes} hardcoded path(s)"
        if verbose:
            print(f"✅ {result['summary']}")
    elif changes > 0 and dry_run:
        result["migrated"] = False
        result["changes"] = changes
        result["summary"] = f"Dry-run: Would migrate {changes} hardcoded path(s)"
        if verbose:
            print(f"ℹ️  {result['summary']}")
    else:
        result["summary"] = "No changes needed"
        if verbose:
            print(f"✅ {result['summary']}")

    return result


def rollback_migration(settings_path: Path, backup_path: Path) -> bool:
    """
    Rollback migration by restoring from backup.

    Args:
        settings_path: Path to settings.json file
        backup_path: Path to backup file

    Returns:
        True if rollback successful, False otherwise
    """
    try:
        if not backup_path.exists():
            print(f"❌ Backup file not found: {backup_path}")
            return False

        shutil.copy2(backup_path, settings_path)
        print(f"✅ Restored settings from backup: {backup_path}")
        return True
    except Exception as e:
        print(f"❌ Rollback failed: {e}")
        return False


def migrate_hook_paths(settings_path: Optional[Path] = None, dry_run: bool = False, verbose: bool = False) -> Dict[str, Any]:
    """
    Main migration function.

    Args:
        settings_path: Path to settings.json (defaults to ~/.claude/settings.json)
        dry_run: If True, don't modify files
        verbose: If True, output detailed information

    Returns:
        Dictionary with migration results
    """
    if settings_path is None:
        settings_path = Path.home() / ".claude" / "settings.json"
    elif isinstance(settings_path, str):
        settings_path = Path(settings_path).expanduser()

    return migrate_settings_file(settings_path, dry_run=dry_run, verbose=verbose)


def main():
    """Command-line interface."""
    parser = argparse.ArgumentParser(
        description="Migrate PreToolUse hook paths from hardcoded to portable (Issue #113)"
    )
    parser.add_argument(
        "--settings-path",
        type=str,
        default=None,
        help="Path to settings.json (default: ~/.claude/settings.json)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without modifying files"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Output detailed information"
    )
    parser.add_argument(
        "--rollback",
        type=str,
        help="Rollback migration from backup file"
    )

    args = parser.parse_args()

    if args.rollback:
        # Rollback mode
        settings_path = Path(args.settings_path).expanduser() if args.settings_path else Path.home() / ".claude" / "settings.json"
        backup_path = Path(args.rollback).expanduser()
        success = rollback_migration(settings_path, backup_path)
        sys.exit(0 if success else 1)
    else:
        # Migration mode
        result = migrate_hook_paths(
            settings_path=args.settings_path,
            dry_run=args.dry_run,
            verbose=args.verbose
        )

        # Print summary (unless verbose already printed it)
        if not args.verbose:
            icon = "✅" if result["migrated"] or result["changes"] == 0 else "ℹ️"
            print(f"{icon} {result['summary']}")
            if result.get("backup_path"):
                print(f"💾 Backup: {result['backup_path']}")

        sys.exit(0)


if __name__ == "__main__":
    main()
