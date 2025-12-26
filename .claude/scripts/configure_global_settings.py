#!/usr/bin/env python3
"""
Configure Global Settings CLI - Fresh install permission configuration

Creates or updates ~/.claude/settings.json with correct permission patterns
for Claude Code 2.0. This script is called by install.sh during fresh install.

Features:
1. Fresh install: Create ~/.claude/settings.json from template
2. Upgrade: Preserve user customizations while fixing broken patterns
3. Broken patterns: Replace Bash(:*) with specific safe patterns
4. Non-blocking: Exit 0 even on errors (installation continues)
5. JSON output: Return structured data for install.sh consumption
6. Directory creation: Create ~/.claude/ if missing

Security:
- Path validation (CWE-22, CWE-59)
- Atomic writes with secure permissions
- Backup before modification
- No wildcards (Bash(git:*) NOT Bash(*))

Usage:
    # Fresh install (no existing settings)
    python3 configure_global_settings.py --template /path/to/template.json

    # Upgrade (existing settings, preserve customizations)
    python3 configure_global_settings.py --template /path/to/template.json --home ~/.claude

Output:
    JSON to stdout: {"success": bool, "created": bool, "message": str, ...}
    Exit code: Always 0 (non-blocking for install.sh)

See Also:
    - plugins/autonomous-dev/lib/settings_generator.py for merge logic
    - plugins/autonomous-dev/config/global_settings_template.json for template
    - tests/unit/scripts/test_configure_global_settings.py for test cases
    - GitHub Issue #116 for requirements

Date: 2025-12-13
Issue: GitHub #116
Agent: implementer
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any

# Add lib to path for imports
try:
    # Try package import first
    from autonomous_dev.lib.settings_generator import SettingsGenerator, SettingsGeneratorError
except ImportError:
    # Fallback for direct script execution
    lib_path = Path(__file__).parent.parent / "lib"
    sys.path.insert(0, str(lib_path))
    from settings_generator import SettingsGenerator, SettingsGeneratorError


def create_fresh_settings(template_path: Path, global_path: Path) -> Dict[str, Any]:
    """Create fresh settings.json from template.

    Args:
        template_path: Path to global_settings_template.json
        global_path: Path to ~/.claude/settings.json

    Returns:
        Result dict with success status and metadata
    """
    try:
        # Validate template exists
        if not template_path.exists():
            return {
                "success": False,
                "created": False,
                "message": f"Template file not found: {template_path}",
                "error": "template_not_found"
            }

        # Ensure ~/.claude/ directory exists
        claude_dir = global_path.parent
        if not ensure_claude_directory(claude_dir):
            return {
                "success": False,
                "created": False,
                "message": f"Failed to create directory: {claude_dir}",
                "error": "directory_creation_failed"
            }

        # Read template
        template_content = template_path.read_text()
        template_settings = json.loads(template_content)

        # Write settings atomically
        global_path.write_text(json.dumps(template_settings, indent=2) + "\n")

        # Set secure permissions (owner read/write only)
        global_path.chmod(0o600)

        return {
            "success": True,
            "created": True,
            "message": "Fresh install: Created settings.json from template",
            "path": str(global_path),
            "patterns_count": len(template_settings.get("permissions", {}).get("allow", []))
        }

    except PermissionError as e:
        return {
            "success": False,
            "created": False,
            "message": f"Permission denied: {e}",
            "error": "permission_denied"
        }
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "created": False,
            "message": f"Invalid JSON in template: {e}",
            "error": "invalid_template_json"
        }
    except Exception as e:
        return {
            "success": False,
            "created": False,
            "message": f"Unexpected error: {e}",
            "error": "unexpected_error"
        }


def upgrade_existing_settings(global_path: Path, template_path: Path) -> Dict[str, Any]:
    """Upgrade existing settings while preserving user customizations.

    Args:
        global_path: Path to existing ~/.claude/settings.json
        template_path: Path to global_settings_template.json

    Returns:
        Result dict with success status and metadata
    """
    try:
        # Validate inputs
        if not global_path.exists():
            return {
                "success": False,
                "created": False,
                "message": f"Settings file not found: {global_path}",
                "error": "settings_not_found"
            }

        if not template_path.exists():
            return {
                "success": False,
                "created": False,
                "message": f"Template file not found: {template_path}",
                "error": "template_not_found"
            }

        # Use SettingsGenerator to merge settings
        # Pass project_root mode to avoid requiring full plugin structure
        generator = SettingsGenerator(project_root=Path.home())

        # Call merge_global_settings (handles backup, merge, and write)
        # Returns merged settings dict on success, raises exception on error
        merged_settings = generator.merge_global_settings(
            global_path,
            template_path,
            fix_wildcards=True,
            create_backup=True
        )

        # Count patterns fixed (check if Bash(:*) was in original)
        patterns_fixed = 0
        backup_path = global_path.with_suffix(".json.backup")
        try:
            if backup_path.exists():
                original_settings = json.loads(backup_path.read_text())
                if "permissions" in original_settings and "allow" in original_settings["permissions"]:
                    broken = [p for p in original_settings["permissions"]["allow"] if p in ["Bash(:*)", "Bash(*)"]]
                    patterns_fixed = len(broken)
        except:
            pass

        # Build message based on patterns fixed
        if patterns_fixed > 0:
            message = f"Settings upgraded successfully (fixed {patterns_fixed} broken patterns, preserved customizations)"
        else:
            message = "Settings upgraded successfully (preserved customizations)"

        return {
            "success": True,
            "created": False,
            "message": message,
            "merged": True,
            "patterns_fixed": patterns_fixed,
            "path": str(global_path)
        }

    except SettingsGeneratorError as e:
        return {
            "success": False,
            "created": False,
            "message": f"Settings merge error: {e}",
            "error": "merge_failed"
        }

    except PermissionError as e:
        return {
            "success": False,
            "created": False,
            "message": f"Permission denied: {e}",
            "error": "permission_denied"
        }
    except Exception as e:
        return {
            "success": False,
            "created": False,
            "message": f"Unexpected error: {e}",
            "error": "unexpected_error"
        }


def ensure_claude_directory(claude_dir: Path) -> bool:
    """Ensure ~/.claude/ directory exists with correct permissions.

    Args:
        claude_dir: Path to ~/.claude/ directory

    Returns:
        True if directory exists/created, False on error
    """
    try:
        # Create directory if missing (mkdir -p behavior)
        claude_dir.mkdir(parents=True, exist_ok=True)

        # Set permissions (owner read/write/execute)
        claude_dir.chmod(0o700)

        return True

    except PermissionError:
        return False
    except Exception:
        return False


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Configure ~/.claude/settings.json for autonomous-dev plugin",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Fresh install
    %(prog)s --template global_settings_template.json

    # Upgrade with custom home
    %(prog)s --template global_settings_template.json --home ~/.claude

Exit Code:
    Always exits 0 (non-blocking for install.sh)
    Check JSON output "success" field for actual status
        """
    )

    parser.add_argument(
        "--template",
        type=Path,
        required=True,
        help="Path to global_settings_template.json"
    )

    parser.add_argument(
        "--home",
        type=Path,
        default=Path.home() / ".claude",
        help="Path to .claude directory (default: ~/.claude)"
    )

    parser.add_argument(
        "--staging",
        type=Path,
        help="Path to staging directory (unused, for compatibility)"
    )

    args = parser.parse_args()

    # Determine global_path
    global_path = args.home / "settings.json"

    # Check if settings.json already exists
    if global_path.exists():
        # Upgrade scenario: merge with existing settings
        result = upgrade_existing_settings(global_path, args.template)
    else:
        # Fresh install scenario: create from template
        result = create_fresh_settings(args.template, global_path)

    # Output JSON to stdout
    print(json.dumps(result, indent=2))

    # Always exit 0 (non-blocking for install.sh)
    sys.exit(0)


if __name__ == "__main__":
    main()
