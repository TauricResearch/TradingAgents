#!/usr/bin/env python3
"""
Manifest-Documentation Alignment Validator.

DEPRECATED: This regex-based validator is deprecated as of v3.44.0.
Use hybrid_validator.py instead, which provides GenAI-powered semantic
validation with automatic fallback to regex if no API key is available.

Migration:
    # Old (deprecated):
    from validate_manifest_doc_alignment import validate_alignment
    result = validate_alignment(manifest_path)

    # New (recommended):
    from hybrid_validator import validate_manifest_alignment
    report = validate_manifest_alignment(repo_root)

Removal planned: v3.45.0

---

Validates that CLAUDE.md, PROJECT.md, and health-check.py component counts
match install_manifest.json (the single source of truth).

This prevents documentation drift by failing loudly when counts mismatch.

Usage:
    python validate_manifest_doc_alignment.py
    python validate_manifest_doc_alignment.py --fix  # Show fix instructions
    python validate_manifest_doc_alignment.py --manifest path/to/manifest.json

Issue #159: Prevent documentation drift after manifest completeness audit
Issue #160: GenAI-powered validation replaces regex-based approach
"""

import argparse
import json
import re
import sys
import warnings
from pathlib import Path
from typing import Dict, Any, Optional, List

# Emit deprecation warning on module import
warnings.warn(
    "validate_manifest_doc_alignment is deprecated as of v3.44.0. "
    "Use hybrid_validator.validate_manifest_alignment() instead. "
    "This module will be removed in v3.45.0.",
    DeprecationWarning,
    stacklevel=2,
)


class DocumentationDriftError(Exception):
    """Raised when documentation structure prevents count extraction."""
    pass


def find_project_root() -> Path:
    """Find the project root by looking for CLAUDE.md."""
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        if (parent / "CLAUDE.md").exists():
            return parent
        if (parent / "plugins" / "autonomous-dev").exists():
            return parent
    return current


def load_manifest_counts(manifest_path: Path) -> Dict[str, Any]:
    """
    Load component counts from install_manifest.json.

    Args:
        manifest_path: Path to install_manifest.json

    Returns:
        Dict with counts for each component type and version

    Raises:
        FileNotFoundError: If manifest doesn't exist
        json.JSONDecodeError: If manifest is invalid JSON
    """
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    with open(manifest_path) as f:
        manifest = json.load(f)

    # Handle nested "components" structure (actual manifest format)
    # or flat structure (test fixtures)
    components = manifest.get("components", manifest)

    # Count libs (key is "lib" not "libs" in manifest)
    lib_files = components.get("lib", {}).get("files", [])
    # Fallback to "libs" for test fixtures
    if not lib_files:
        lib_files = components.get("libs", {}).get("files", [])

    # Count skill packages (directories), not individual files
    # Each skill is in a directory like "skills/skill-name/skill.md"
    skill_files = components.get("skills", {}).get("files", [])
    # Extract unique skill directories
    skill_dirs = set()
    for f in skill_files:
        # Extract directory name: "plugins/.../skills/skill-name/file.md" -> "skill-name"
        parts = f.split("/")
        if "skills" in parts:
            skills_idx = parts.index("skills")
            if skills_idx + 1 < len(parts):
                skill_dirs.add(parts[skills_idx + 1])

    counts = {
        "version": manifest.get("version", "unknown"),
        "agents": len(components.get("agents", {}).get("files", [])),
        "commands": len(components.get("commands", {}).get("files", [])),
        "hooks": len(components.get("hooks", {}).get("files", [])),
        "libs": len(lib_files),
        "skills": len(skill_dirs) if skill_dirs else len(skill_files),
    }

    return counts


def extract_claude_md_counts(claude_md_path: Path) -> Dict[str, int]:
    """
    Extract component counts from CLAUDE.md table format.

    Looks for table like:
    | Component | Version | Count | Status |
    | Agents | 1.0.0 | 21 | ✅ |

    Args:
        claude_md_path: Path to CLAUDE.md

    Returns:
        Dict with counts for each component type

    Raises:
        DocumentationDriftError: If table format not found
    """
    content = claude_md_path.read_text()

    # Match table rows: | Component | ... | Count | ... |
    # Pattern: | Agents | 1.0.0 | 21 | ✅ Compliant |
    table_pattern = r'\|\s*(Skills|Commands|Agents|Hooks)\s*\|\s*[\d.]+\s*\|\s*(\d+)\s*\|'

    matches = re.findall(table_pattern, content, re.IGNORECASE)

    if not matches:
        raise DocumentationDriftError(
            f"Component table not found in {claude_md_path}. "
            "Expected format: | Component | Version | Count | Status |"
        )

    counts = {}
    for component, count in matches:
        key = component.lower()
        counts[key] = int(count)

    return counts


def extract_claude_md_version(claude_md_path: Path) -> str:
    """
    Extract version from CLAUDE.md header.

    Looks for: **Version**: v3.44.0

    Args:
        claude_md_path: Path to CLAUDE.md

    Returns:
        Version string (without 'v' prefix)
    """
    content = claude_md_path.read_text()

    # Match: **Version**: v3.44.0
    version_pattern = r'\*\*Version\*\*:\s*v?([\d.]+)'
    match = re.search(version_pattern, content)

    if match:
        return match.group(1)

    return "unknown"


def extract_project_md_counts(project_md_path: Path) -> Dict[str, int]:
    """
    Extract component counts from PROJECT.md table format.

    Looks for table like:
    | Component | Count | Purpose |
    | Agents | 21 | Specialized AI assistants |

    Args:
        project_md_path: Path to PROJECT.md

    Returns:
        Dict with counts for each component type
    """
    content = project_md_path.read_text()

    # Match table rows: | Component | Count | ... |
    # Pattern: | Agents | 21 | Purpose text |
    table_pattern = r'\|\s*(Agents|Skills|Commands|Hooks|Libraries)\s*\|\s*(\d+)\s*\|'

    matches = re.findall(table_pattern, content, re.IGNORECASE)

    counts = {}
    for component, count in matches:
        key = component.lower()
        # Normalize "Libraries" to "libs"
        if key == "libraries":
            key = "libs"
        counts[key] = int(count)

    return counts


def extract_project_md_version(project_md_path: Path) -> str:
    """
    Extract version from PROJECT.md header.

    Looks for: **Version**: v3.44.0

    Args:
        project_md_path: Path to PROJECT.md

    Returns:
        Version string (without 'v' prefix)
    """
    content = project_md_path.read_text()

    # Match: **Version**: v3.44.0
    version_pattern = r'\*\*Version\*\*:\s*v?([\d.]+)'
    match = re.search(version_pattern, content)

    if match:
        return match.group(1)

    return "unknown"


def extract_health_check_counts(health_check_path: Path) -> Dict[str, int]:
    """
    Extract expected component counts from health_check.py lists.

    Looks for EXPECTED_AGENTS, EXPECTED_HOOKS, EXPECTED_COMMANDS lists.

    Args:
        health_check_path: Path to health_check.py

    Returns:
        Dict with counts for each component type
    """
    content = health_check_path.read_text()

    counts = {}

    # Count items in EXPECTED_AGENTS list
    agents_match = re.search(r'EXPECTED_AGENTS\s*=\s*\[(.*?)\]', content, re.DOTALL)
    if agents_match:
        items = re.findall(r'"([^"]+)"', agents_match.group(1))
        counts["agents"] = len(items)

    # Count items in EXPECTED_HOOKS list
    hooks_match = re.search(r'EXPECTED_HOOKS\s*=\s*\[(.*?)\]', content, re.DOTALL)
    if hooks_match:
        items = re.findall(r'"([^"]+)"', hooks_match.group(1))
        counts["hooks"] = len(items)

    # Count items in EXPECTED_COMMANDS list
    commands_match = re.search(r'EXPECTED_COMMANDS\s*=\s*\[(.*?)\]', content, re.DOTALL)
    if commands_match:
        items = re.findall(r'"([^"]+)"', commands_match.group(1))
        counts["commands"] = len(items)

    return counts


def detect_mismatches(
    expected: Dict[str, Any],
    actual: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """
    Detect mismatches between expected (manifest) and actual (doc) counts.

    Args:
        expected: Counts from manifest (source of truth)
        actual: Counts from documentation file

    Returns:
        Dict of mismatches with expected and actual values
    """
    mismatches = {}

    for key in expected:
        if key == "version":
            continue  # Handle version separately
        if key in actual and expected[key] != actual[key]:
            mismatches[key] = {
                "expected": expected[key],
                "actual": actual[key],
            }

    return mismatches


def detect_version_mismatch(expected: str, actual: str) -> Dict[str, Dict[str, str]]:
    """
    Detect version mismatch.

    Args:
        expected: Version from manifest
        actual: Version from document

    Returns:
        Dict with version mismatch if different
    """
    if expected != actual and expected != "unknown" and actual != "unknown":
        return {
            "version": {
                "expected": expected,
                "actual": actual,
            }
        }
    return {}


def validate_alignment(
    manifest_path: Path,
    claude_md_path: Optional[Path] = None,
    project_md_path: Optional[Path] = None,
    health_check_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Validate alignment between manifest and documentation files.

    Args:
        manifest_path: Path to install_manifest.json
        claude_md_path: Optional path to CLAUDE.md
        project_md_path: Optional path to PROJECT.md
        health_check_path: Optional path to health_check.py

    Returns:
        Dict with status, mismatches, and details
    """
    result = {
        "status": "ALIGNED",
        "mismatches": {},
        "details": {},
    }

    # Load manifest counts (source of truth)
    manifest_counts = load_manifest_counts(manifest_path)
    result["details"]["manifest"] = manifest_counts

    # Validate CLAUDE.md
    if claude_md_path and claude_md_path.exists():
        try:
            claude_counts = extract_claude_md_counts(claude_md_path)
            claude_version = extract_claude_md_version(claude_md_path)

            mismatches = detect_mismatches(manifest_counts, claude_counts)
            version_mismatch = detect_version_mismatch(
                manifest_counts["version"], claude_version
            )

            if mismatches or version_mismatch:
                result["status"] = "DRIFTED"
                for key, value in mismatches.items():
                    value["file"] = "CLAUDE.md"
                    result["mismatches"][f"claude_md_{key}"] = value
                if version_mismatch:
                    version_mismatch["version"]["file"] = "CLAUDE.md"
                    result["mismatches"]["claude_md_version"] = version_mismatch["version"]

            result["details"]["claude_md"] = {
                "counts": claude_counts,
                "version": claude_version,
            }

        except DocumentationDriftError as e:
            result["status"] = "ERROR"
            result["mismatches"]["claude_md_format"] = {"error": str(e)}

    # Validate PROJECT.md
    if project_md_path and project_md_path.exists():
        project_counts = extract_project_md_counts(project_md_path)
        project_version = extract_project_md_version(project_md_path)

        mismatches = detect_mismatches(manifest_counts, project_counts)
        version_mismatch = detect_version_mismatch(
            manifest_counts["version"], project_version
        )

        if mismatches or version_mismatch:
            result["status"] = "DRIFTED"
            for key, value in mismatches.items():
                value["file"] = "PROJECT.md"
                result["mismatches"][f"project_md_{key}"] = value
            if version_mismatch:
                version_mismatch["version"]["file"] = "PROJECT.md"
                result["mismatches"]["project_md_version"] = version_mismatch["version"]

        result["details"]["project_md"] = {
            "counts": project_counts,
            "version": project_version,
        }

    # Note: health_check.py validates "core" components (8 agents, 12 hooks, 8 commands)
    # not ALL installed components. So we don't compare it to manifest counts.
    # health_check.py is intentionally a subset for essential pipeline validation.

    return result


def generate_fix_instructions(mismatches: Dict[str, Dict[str, Any]]) -> str:
    """
    Generate actionable fix instructions for mismatches.

    Args:
        mismatches: Dict of detected mismatches

    Returns:
        Human-readable fix instructions
    """
    if not mismatches:
        return "✅ All documentation is aligned with manifest."

    lines = [
        "❌ Documentation drift detected!",
        "",
        "The following files need updates to match install_manifest.json:",
        "",
    ]

    # Group by file
    by_file: Dict[str, List[str]] = {}
    for key, value in mismatches.items():
        file = value.get("file", "unknown")
        if file not in by_file:
            by_file[file] = []

        if "error" in value:
            by_file[file].append(f"  - ERROR: {value['error']}")
        else:
            component = key.split("_")[-1]  # Extract component name
            by_file[file].append(
                f"  - {component}: expected {value['expected']}, found {value['actual']}"
            )

    for file, issues in by_file.items():
        lines.append(f"**{file}**:")
        lines.extend(issues)
        lines.append("")

    lines.extend([
        "To fix:",
        "1. Update the counts in the affected files to match install_manifest.json",
        "2. Update version numbers to match manifest version",
        "3. Run this validator again to confirm alignment",
    ])

    return "\n".join(lines)


def should_block_commit(result: Dict[str, Any]) -> bool:
    """
    Determine if a commit should be blocked based on validation result.

    Args:
        result: Validation result from validate_alignment()

    Returns:
        True if commit should be blocked
    """
    return result["status"] in ("DRIFTED", "ERROR")


def main(args: Optional[List[str]] = None) -> int:
    """
    CLI entry point.

    Args:
        args: Command line arguments (defaults to sys.argv)

    Returns:
        Exit code (0 = aligned, 1 = drifted, 2 = error)
    """
    parser = argparse.ArgumentParser(
        description="Validate manifest-documentation alignment"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Path to install_manifest.json",
    )
    parser.add_argument(
        "--claude-md",
        type=Path,
        help="Path to CLAUDE.md",
    )
    parser.add_argument(
        "--project-md",
        type=Path,
        help="Path to PROJECT.md",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Show fix instructions",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    parsed = parser.parse_args(args)

    # Find project root and default paths
    root = find_project_root()

    manifest_path = parsed.manifest or (
        root / "plugins" / "autonomous-dev" / "config" / "install_manifest.json"
    )
    claude_md_path = parsed.claude_md or (root / "CLAUDE.md")
    project_md_path = parsed.project_md or (root / "PROJECT.md")

    try:
        result = validate_alignment(
            manifest_path=manifest_path,
            claude_md_path=claude_md_path,
            project_md_path=project_md_path,
        )

        if parsed.json:
            print(json.dumps(result, indent=2))
        else:
            if result["status"] == "ALIGNED":
                print("✅ Documentation is aligned with install_manifest.json")
                return 0
            else:
                print(generate_fix_instructions(result["mismatches"]))
                return 1

    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        return 2
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in manifest: {e}")
        return 2

    return 0 if result["status"] == "ALIGNED" else 1


if __name__ == "__main__":
    sys.exit(main())
