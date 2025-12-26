#!/usr/bin/env python3
"""
Unified Manifest Sync Hook - Dispatcher for PreCommit Manifest Validation

Consolidates PreCommit manifest validation hooks:
- validate_install_manifest.py (install manifest sync)
- validate_settings_hooks.py (settings template validation)

Hook: PreCommit (runs before git commit completes)

Environment Variables (opt-in/opt-out):
    VALIDATE_MANIFEST=true/false (default: true)
    VALIDATE_SETTINGS=true/false (default: true)
    AUTO_UPDATE_MANIFEST=true/false (default: true)

Exit codes:
    0: All validations passed (or were auto-updated)
    1: Validation failed (blocks commit)

Usage:
    # As PreCommit hook (automatic)
    python unified_manifest_sync.py

    # Check-only mode (no auto-update)
    AUTO_UPDATE_MANIFEST=false python unified_manifest_sync.py
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple


# ============================================================================
# Configuration
# ============================================================================

import os

# Check configuration from environment
VALIDATE_MANIFEST = os.environ.get("VALIDATE_MANIFEST", "true").lower() == "true"
VALIDATE_SETTINGS = os.environ.get("VALIDATE_SETTINGS", "true").lower() == "true"
AUTO_UPDATE_MANIFEST = os.environ.get("AUTO_UPDATE_MANIFEST", "true").lower() == "true"


# ============================================================================
# Utilities
# ============================================================================

def get_project_root() -> Path:
    """Find project root by looking for .git directory."""
    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return Path.cwd()


# ============================================================================
# Install Manifest Validation
# ============================================================================

def scan_source_files(plugin_dir: Path) -> Dict[str, List[str]]:
    """
    Scan source directories and return files by component.

    Args:
        plugin_dir: Path to plugin directory

    Returns:
        Dict mapping component name to list of file paths
    """
    components = {}

    # Define what to scan: (directory, pattern, component_name, recursive)
    scans = [
        ("hooks", "*.py", "hooks", False),
        ("lib", "*.py", "lib", False),
        ("agents", "*.md", "agents", False),
        ("commands", "*.md", "commands", False),  # Top level only
        ("scripts", "*.py", "scripts", False),
        ("config", "*.json", "config", False),
        ("templates", "*.json", "templates", False),
        ("templates", "*.template", "templates", False),
        ("skills", "*.md", "skills", True),  # Recursive
    ]

    for dir_name, pattern, component_name, recursive in scans:
        source_dir = plugin_dir / dir_name
        if not source_dir.exists():
            continue

        files = []
        glob_method = source_dir.rglob if recursive else source_dir.glob

        for f in glob_method(pattern):
            if not f.is_file():
                continue
            # Skip pycache, test files
            if "__pycache__" in str(f):
                continue
            if f.name.startswith("test_"):
                continue

            # Build manifest path
            relative_to_source = f.relative_to(source_dir)
            relative = f"plugins/autonomous-dev/{dir_name}/{relative_to_source}"
            files.append(relative)

        # Extend existing component files
        if component_name in components:
            components[component_name] = sorted(set(components[component_name] + files))
        else:
            components[component_name] = sorted(files)

    return components


def sync_manifest(manifest_path: Path, scanned: Dict[str, List[str]]) -> Tuple[bool, List[str], List[str]]:
    """
    Bidirectionally sync manifest with scanned files.

    Args:
        manifest_path: Path to install_manifest.json
        scanned: Scanned files by component

    Returns:
        Tuple of (was_updated, list of added files, list of removed files)
    """
    if not manifest_path.exists():
        return False, [], []

    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError:
        return False, [], []

    components_config = manifest.get("components", {})
    added_files = []
    removed_files = []
    was_updated = False

    for component_name, scanned_files in scanned.items():
        if component_name not in components_config:
            continue

        manifest_files = components_config[component_name].get("files", [])

        # Find added files (in scanned but not in manifest)
        for f in scanned_files:
            if f not in manifest_files:
                added_files.append(f)
                manifest_files.append(f)
                was_updated = True

        # Find removed files (in manifest but not in scanned)
        for f in list(manifest_files):
            if f not in scanned_files:
                removed_files.append(f)
                manifest_files.remove(f)
                was_updated = True

        # Update manifest
        components_config[component_name]["files"] = sorted(manifest_files)

    # Write updated manifest
    if was_updated and AUTO_UPDATE_MANIFEST:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    return was_updated, added_files, removed_files


def validate_install_manifest() -> Tuple[bool, str]:
    """
    Validate install manifest is in sync with source files.

    Returns:
        Tuple of (success, error_message)
    """
    if not VALIDATE_MANIFEST:
        return True, ""

    project_root = get_project_root()
    plugin_dir = project_root / "plugins" / "autonomous-dev"
    manifest_path = plugin_dir / "install_manifest.json"

    if not manifest_path.exists():
        return True, ""  # No manifest to validate

    # Scan source files
    scanned = scan_source_files(plugin_dir)

    # Sync manifest
    was_updated, added, removed = sync_manifest(manifest_path, scanned)

    if was_updated:
        if AUTO_UPDATE_MANIFEST:
            # Auto-updated successfully
            msg = f"Install manifest auto-updated:\n"
            if added:
                msg += f"  Added: {len(added)} files\n"
            if removed:
                msg += f"  Removed: {len(removed)} files\n"
            msg += "  (Changes staged automatically)\n"
            return True, msg
        else:
            # Check-only mode - report drift
            msg = f"Install manifest out of sync:\n"
            if added:
                msg += f"  Missing: {len(added)} files\n"
                for f in added[:5]:  # Show first 5
                    msg += f"    + {f}\n"
            if removed:
                msg += f"  Orphaned: {len(removed)} files\n"
                for f in removed[:5]:
                    msg += f"    - {f}\n"
            msg += "  Run with AUTO_UPDATE_MANIFEST=true to fix\n"
            return False, msg

    return True, ""


# ============================================================================
# Settings Template Validation
# ============================================================================

def extract_hook_files(settings: Dict) -> List[str]:
    """
    Extract hook file names from settings template.

    Args:
        settings: Settings template dictionary

    Returns:
        List of hook filenames
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
                # Extract hook filename from command
                match = re.search(r'hooks/([a-z_]+\.py)', command)
                if match:
                    hooks.append(match.group(1))

    return hooks


def validate_settings_hooks() -> Tuple[bool, str]:
    """
    Validate all hooks in settings template exist.

    Returns:
        Tuple of (success, error_message)
    """
    if not VALIDATE_SETTINGS:
        return True, ""

    project_root = get_project_root()
    plugin_dir = project_root / "plugins" / "autonomous-dev"

    # Load settings template
    template_path = plugin_dir / "config" / "global_settings_template.json"
    if not template_path.exists():
        return True, ""

    try:
        settings = json.loads(template_path.read_text())
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in settings template: {e}"

    # Extract referenced hooks
    referenced_hooks = extract_hook_files(settings)
    if not referenced_hooks:
        return True, ""

    # Check each hook exists
    hooks_dir = plugin_dir / "hooks"
    missing = []

    for hook_file in referenced_hooks:
        hook_path = hooks_dir / hook_file
        if not hook_path.exists():
            missing.append(hook_file)

    if missing:
        msg = f"Settings template references missing hooks:\n"
        for h in missing:
            msg += f"  - {h}\n"
        return False, msg

    return True, ""


# ============================================================================
# Main Hook Entry Point
# ============================================================================

def main() -> int:
    """
    Main hook entry point.

    Runs all validations and reports results.

    Returns:
        0 if all validations passed, 1 if any failed
    """
    all_passed = True
    messages = []

    # Validate install manifest
    manifest_passed, manifest_msg = validate_install_manifest()
    if not manifest_passed:
        all_passed = False
        messages.append(f"[FAIL] Install Manifest:\n{manifest_msg}")
    elif manifest_msg:
        messages.append(f"[INFO] Install Manifest:\n{manifest_msg}")

    # Validate settings hooks
    settings_passed, settings_msg = validate_settings_hooks()
    if not settings_passed:
        all_passed = False
        messages.append(f"[FAIL] Settings Hooks:\n{settings_msg}")

    # Output results
    if messages:
        for msg in messages:
            print(msg, file=sys.stderr if not all_passed else sys.stdout)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
