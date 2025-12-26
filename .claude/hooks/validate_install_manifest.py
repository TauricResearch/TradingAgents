#!/usr/bin/env python3
"""
Validate and Auto-Update Install Manifest - Pre-commit Hook

Ensures install_manifest.json is BIDIRECTIONALLY SYNCED with source directories.
AUTOMATICALLY UPDATES the manifest when files are added OR removed.

Scans:
- hooks/*.py → manifest components.hooks.files
- lib/*.py → manifest components.lib.files
- agents/*.md → manifest components.agents.files
- commands/*.md → manifest components.commands.files (excludes archive/)
- scripts/*.py → manifest components.scripts.files
- config/*.json → manifest components.config.files
- templates/*.json, *.template → manifest components.templates.files

Usage:
    python3 validate_install_manifest.py [--check-only]

Flags:
    --check-only  Only validate, don't auto-update (for CI)

Exit Codes:
    0 - Manifest is in sync (or was auto-updated)
    1 - Check-only mode and files are out of sync
"""

import json
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


def scan_source_files(plugin_dir: Path) -> dict:
    """Scan source directories and return files by component.

    Returns:
        Dict mapping component name to list of file paths
    """
    components = {}

    # Define what to scan: (directory, pattern, component_name, recursive)
    scans = [
        ("hooks", "*.py", "hooks", False),
        ("lib", "*.py", "lib", False),
        ("agents", "*.md", "agents", False),
        ("commands", "*.md", "commands", False),  # Top level only, excludes archive/
        ("scripts", "*.py", "scripts", False),
        ("config", "*.json", "config", False),
        ("templates", "*.json", "templates", False),
        ("templates", "*.template", "templates", False),  # .env template
        ("skills", "*.md", "skills", True),  # Recursive - includes docs/, examples/, templates/
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

            # Build manifest path (supports recursive subdirectories)
            relative_to_source = f.relative_to(source_dir)
            relative = f"plugins/autonomous-dev/{dir_name}/{relative_to_source}"
            files.append(relative)

        # Extend existing component files (for multiple patterns on same dir)
        if component_name in components:
            components[component_name] = sorted(set(components[component_name] + files))
        else:
            components[component_name] = sorted(files)

    return components


def sync_manifest(manifest_path: Path, scanned: dict) -> tuple[bool, list[str], list[str]]:
    """Bidirectionally sync manifest with scanned files.

    Returns:
        Tuple of (was_updated, list of added files, list of removed files)
    """
    # Load existing manifest
    manifest = json.loads(manifest_path.read_text())

    added = []
    removed = []

    for component_name, scanned_files in scanned.items():
        if component_name not in manifest.get("components", {}):
            continue

        existing = set(manifest["components"][component_name].get("files", []))
        scanned_set = set(scanned_files)

        # Find new files (in source but not in manifest)
        new_files = scanned_set - existing
        if new_files:
            added.extend(new_files)

        # Find removed files (in manifest but not in source)
        deleted_files = existing - scanned_set
        if deleted_files:
            removed.extend(deleted_files)

        # Update manifest to match source exactly
        if new_files or deleted_files:
            manifest["components"][component_name]["files"] = sorted(scanned_files)

    if added or removed:
        # Write updated manifest
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        return True, added, removed

    return False, [], []


def validate_manifest(check_only: bool = False) -> tuple[bool, list[str], list[str]]:
    """Validate and optionally update manifest.

    Args:
        check_only: If True, only validate without updating

    Returns:
        Tuple of (success, list of missing files, list of orphan files)
    """
    project_root = get_project_root()
    plugin_dir = project_root / "plugins" / "autonomous-dev"
    manifest_path = plugin_dir / "config" / "install_manifest.json"

    if not manifest_path.exists():
        return False, ["install_manifest.json not found"], []

    # Scan source files
    scanned = scan_source_files(plugin_dir)

    # Load manifest and compare
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON in manifest: {e}"], []

    # Find differences
    missing = []  # In source but not in manifest
    orphan = []   # In manifest but not in source

    for component_name, scanned_files in scanned.items():
        if component_name not in manifest.get("components", {}):
            continue
        existing = set(manifest["components"][component_name].get("files", []))
        scanned_set = set(scanned_files)

        # Files that need to be added
        for f in scanned_set - existing:
            missing.append(f)

        # Files that need to be removed
        for f in existing - scanned_set:
            orphan.append(f)

    if not missing and not orphan:
        return True, [], []

    if check_only:
        return False, missing, orphan

    # Auto-sync manifest
    updated, added, removed = sync_manifest(manifest_path, scanned)
    if updated:
        return True, added, removed

    return True, [], []


def main() -> int:
    """Main entry point."""
    check_only = "--check-only" in sys.argv

    success, missing_or_added, orphan_or_removed = validate_manifest(check_only=check_only)

    if success:
        if missing_or_added or orphan_or_removed:
            total_changes = len(missing_or_added) + len(orphan_or_removed)
            print(f"✅ Auto-synced install_manifest.json ({total_changes} changes)")

            if missing_or_added:
                print(f"\n  Added ({len(missing_or_added)}):")
                for f in sorted(missing_or_added):
                    print(f"    + {f}")

            if orphan_or_removed:
                print(f"\n  Removed ({len(orphan_or_removed)}):")
                for f in sorted(orphan_or_removed):
                    print(f"    - {f}")

            print("")
            print("Manifest updated. Run: git add plugins/autonomous-dev/config/install_manifest.json")
        else:
            print("✅ install_manifest.json is in sync")
        return 0
    else:
        print("❌ install_manifest.json is OUT OF SYNC!")
        print("")

        if missing_or_added:
            print(f"Missing from manifest ({len(missing_or_added)}):")
            for f in sorted(missing_or_added):
                print(f"  + {f}")

        if orphan_or_removed:
            print(f"\nOrphan entries (files deleted) ({len(orphan_or_removed)}):")
            for f in sorted(orphan_or_removed):
                print(f"  - {f}")

        if check_only:
            print("")
            print("Run without --check-only to auto-sync")
        return 1


if __name__ == "__main__":
    sys.exit(main())
