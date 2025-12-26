#!/usr/bin/env python3
"""
Validate README.md synchronization between root and plugin directories.

Ensures that key sections (skills, agents, commands) stay consistent across:
- /README.md (root - for contributors/developers)
- /plugins/autonomous-dev/README.md (plugin - for users)

**IMPORTANT**: This hook only runs in the autonomous-dev plugin repository.
It automatically detects user projects and silently succeeds (no blocking).
Plugin users will never see validation errors from this hook.

Exit codes:
  0 - READMEs in sync (or hook skipped in user project)
  1 - Warning (show message but allow commit)
  2 - Block commit (critical sections out of sync in plugin repo)
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple


# Sections that MUST be in sync (critical)
CRITICAL_SECTIONS = [
    "Skills",  # Skill count and architecture
    "Agents",  # Agent count and list
]

# Sections that SHOULD be in sync (warning only)
WARNING_SECTIONS = [
    "Commands",  # Command list
    "Version",   # Version number
]


def extract_section(readme_content: str, section_name: str) -> str:
    """Extract a section from README content."""
    # Match: ### Section Name or ## Section Name
    pattern = rf"^#{2,3}\s+{section_name}.*?(?=^#{2,3}\s+|\Z)"
    match = re.search(pattern, readme_content, re.MULTILINE | re.DOTALL)
    return match.group(0) if match else ""


def extract_key_stats(content: str) -> Dict[str, str]:
    """Extract key statistics from README content."""
    stats = {}

    # Extract skill count (e.g., "19 Active Skills")
    skill_match = re.search(r"(\d+)\s+[Aa]ctive\s+[Ss]kills", content)
    if skill_match:
        stats["skill_count"] = skill_match.group(1)

    # Extract agent count (e.g., "18 AI Specialists" or "18 specialist agents")
    agent_match = re.search(r"(\d+)\s+(?:[Aa][Ii]\s+)?[Ss]pecialists?(?:\s+agents)?", content)
    if agent_match:
        stats["agent_count"] = agent_match.group(1)

    # Extract command count (e.g., "18 Commands")
    command_match = re.search(r"(\d+)\s+[Cc]ommands", content)
    if command_match:
        stats["command_count"] = command_match.group(1)

    # Extract version (e.g., "v3.5.0")
    version_match = re.search(r"[Vv]ersion[:\s]+(v?\d+\.\d+\.\d+)", content)
    if version_match:
        stats["version"] = version_match.group(1)

    return stats


def compare_stats(root_stats: Dict[str, str], plugin_stats: Dict[str, str]) -> List[Tuple[str, str, str]]:
    """Compare stats between root and plugin READMEs."""
    mismatches = []

    for key in set(root_stats.keys()) | set(plugin_stats.keys()):
        root_val = root_stats.get(key, "NOT FOUND")
        plugin_val = plugin_stats.get(key, "NOT FOUND")

        if root_val != plugin_val:
            mismatches.append((key, root_val, plugin_val))

    return mismatches


def main():
    """Main validation function."""
    repo_root = Path(__file__).resolve().parents[3]  # Up 3 levels from hooks/

    root_readme = repo_root / "README.md"
    plugin_readme = repo_root / "plugins" / "autonomous-dev" / "README.md"

    # Auto-detect if we're in the autonomous-dev repository
    # If not, silently skip (this hook is for the plugin repo only)
    is_plugin_repo = (repo_root / "plugins" / "autonomous-dev").exists()

    if not is_plugin_repo:
        # User project - this hook doesn't apply
        # Silently succeed so we don't block user workflows
        return 0

    # Check both READMEs exist (only in plugin repo)
    if not root_readme.exists():
        print(f"❌ Root README not found: {root_readme}", file=sys.stderr)
        print("", file=sys.stderr)
        print("This hook is for the autonomous-dev plugin repository only.", file=sys.stderr)
        print("If you're a plugin user, you can safely ignore this.", file=sys.stderr)
        sys.exit(2)

    if not plugin_readme.exists():
        print(f"❌ Plugin README not found: {plugin_readme}", file=sys.stderr)
        print("", file=sys.stderr)
        print("This hook is for the autonomous-dev plugin repository only.", file=sys.stderr)
        print("If you're a plugin user, you can safely ignore this.", file=sys.stderr)
        sys.exit(2)

    # Read both READMEs
    root_content = root_readme.read_text()
    plugin_content = plugin_readme.read_text()

    # Extract key statistics
    root_stats = extract_key_stats(root_content)
    plugin_stats = extract_key_stats(plugin_content)

    # Compare statistics
    mismatches = compare_stats(root_stats, plugin_stats)

    if not mismatches:
        # All stats match - success
        return 0

    # Check if mismatches are critical
    critical_mismatches = [
        (key, root, plugin)
        for key, root, plugin in mismatches
        if key in ["skill_count", "agent_count"]
    ]

    warning_mismatches = [
        (key, root, plugin)
        for key, root, plugin in mismatches
        if key not in ["skill_count", "agent_count"]
    ]

    # Report critical mismatches (block commit)
    if critical_mismatches:
        print("❌ CRITICAL: README.md files out of sync", file=sys.stderr)
        print("", file=sys.stderr)
        print("The following critical statistics differ:", file=sys.stderr)
        print("", file=sys.stderr)
        for key, root_val, plugin_val in critical_mismatches:
            print(f"  {key}:", file=sys.stderr)
            print(f"    Root README:   {root_val}", file=sys.stderr)
            print(f"    Plugin README: {plugin_val}", file=sys.stderr)
            print("", file=sys.stderr)
        print("Please update both READMEs to match.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Files to update:", file=sys.stderr)
        print(f"  - {root_readme}", file=sys.stderr)
        print(f"  - {plugin_readme}", file=sys.stderr)
        sys.exit(2)

    # Report warning mismatches (allow commit with warning)
    if warning_mismatches:
        print("⚠️  WARNING: README.md minor differences detected", file=sys.stderr)
        print("", file=sys.stderr)
        for key, root_val, plugin_val in warning_mismatches:
            print(f"  {key}:", file=sys.stderr)
            print(f"    Root README:   {root_val}", file=sys.stderr)
            print(f"    Plugin README: {plugin_val}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Consider updating both READMEs for consistency.", file=sys.stderr)
        sys.exit(1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
