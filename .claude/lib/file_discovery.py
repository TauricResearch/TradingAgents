#!/usr/bin/env python3
"""
File Discovery Engine - Comprehensive plugin file discovery for installation

This module provides comprehensive file discovery for plugin installation,
ensuring 100% file coverage (all 201+ files) instead of the current ~76% (152 files).

Key Features:
- Recursive directory traversal (finds all files, not just *.md)
- Intelligent exclusion patterns (cache, build artifacts, hidden files)
- Nested skill structure support (skills/[name].skill/docs/...)
- Installation manifest generation
- Coverage validation

Current Problem:
- install.sh uses shallow glob patterns (*.md) - misses Python files
- Only copies ~152 of 201 files (76% coverage)
- Missing: All 9 scripts/, 23 of 48 lib/ files, 3 agent implementations

Solution:
- Comprehensive recursive file discovery
- Structured copy preserving directory hierarchy
- Validation to detect missing files

Usage:
    from file_discovery import FileDiscovery

    # Discover all files
    discovery = FileDiscovery(plugin_dir)
    files = discovery.discover_all_files()  # Returns list of Path objects

    # Generate manifest
    manifest = discovery.generate_manifest()

    # Validate against manifest
    missing = discovery.validate_against_manifest(manifest)

Date: 2025-11-17
Issue: GitHub #80 (Bootstrap overhaul - 100% file coverage)
Agent: implementer

Design Patterns:
    See library-design-patterns skill for standardized design patterns.
    See file-organization skill for directory structure patterns.
"""

import json
from pathlib import Path
from typing import List, Dict, Any

# Security utilities for path validation and audit logging
try:
    from plugins.autonomous_dev.lib.security_utils import validate_path, audit_log
except ImportError:
    from security_utils import validate_path, audit_log


# Exclusion patterns for file discovery
EXCLUDE_PATTERNS = {
    # Cache and build artifacts
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    ".pytest_cache",
    "*.egg-info",
    ".eggs",
    "*.egg",
    "build",
    "dist",

    # Version control
    ".git",
    ".gitignore",
    ".gitattributes",

    # IDE and editor files
    ".vscode",
    ".idea",
    "*.swp",
    "*.swo",
    ".DS_Store",

    # Temporary files
    "*.tmp",
    "*.bak",
    "*.log",
    "*~",
}

# Directory patterns to exclude (partial match)
EXCLUDE_DIR_PATTERNS = [
    ".egg-info",
    "__pycache__",
    ".pytest_cache",
    ".git",
    ".eggs",
    "build",
    "dist",
]

# Hidden files to INCLUDE (exceptions to hidden file exclusion)
INCLUDE_HIDDEN = {
    ".env.example",
}


class FileDiscovery:
    """Comprehensive file discovery for plugin installation.

    Discovers all files in plugin directory with intelligent exclusions,
    supporting nested structures (skills, lib, scripts, etc.).

    Attributes:
        plugin_dir: Path to plugin directory (e.g., plugins/autonomous-dev/)

    Examples:
        >>> discovery = FileDiscovery(plugin_dir)
        >>> files = discovery.discover_all_files()
        >>> print(f"Found {len(files)} files")
        >>> manifest = discovery.generate_manifest()
    """

    def __init__(self, plugin_dir: Path):
        """Initialize file discovery for plugin directory.

        Args:
            plugin_dir: Path to plugin directory

        Raises:
            FileNotFoundError: If plugin directory doesn't exist
            ValueError: If path validation fails (path traversal, symlink)
        """
        # Validate plugin directory path (prevents CWE-22, CWE-59)
        self.plugin_dir = validate_path(
            Path(plugin_dir).resolve(),
            purpose="plugin directory",
            allow_missing=False
        )

        # Audit log initialization
        audit_log("file_discovery", "initialized", {
            "plugin_dir": str(self.plugin_dir)
        })

    def discover_all_files(self) -> List[Path]:
        """Discover all files in plugin directory recursively.

        Returns:
            List of absolute Path objects for all discovered files

        Raises:
            FileNotFoundError: If plugin directory doesn't exist

        Examples:
            >>> files = discovery.discover_all_files()
            >>> for file in files:
            ...     print(file.relative_to(plugin_dir))
        """
        if not self.plugin_dir.exists():
            raise FileNotFoundError(
                f"Plugin directory not found: {self.plugin_dir}\n"
                f"Expected structure: plugins/autonomous-dev/"
            )

        files = []

        # Recursively walk directory tree
        for path in self.plugin_dir.rglob("*"):
            # Skip directories (we only want files)
            if path.is_dir():
                continue

            # Security: Skip symlinks to prevent CWE-59 (Symlink Following)
            if path.is_symlink():
                audit_log("file_discovery", "skipped_symlink", {
                    "path": str(path),
                    "reason": "Symlinks not allowed in plugin distribution"
                })
                continue

            # Skip if matches exclusion pattern
            if self._should_exclude(path):
                continue

            files.append(path)

        return sorted(files)  # Sort for deterministic ordering

    def _should_exclude(self, path: Path) -> bool:
        """Check if path should be excluded from discovery.

        Exclusion rules:
        - Cache directories (__pycache__, .pytest_cache)
        - Build artifacts (*.pyc, *.egg-info)
        - Version control (.git/)
        - Hidden files (.*) EXCEPT .env.example
        - Temporary files (*.tmp, *.bak)

        Args:
            path: Path to check

        Returns:
            True if path should be excluded, False otherwise
        """
        # Check if in excluded directory
        parts = path.relative_to(self.plugin_dir).parts
        for part in parts:
            # Excluded directory names (exact match)
            if part in EXCLUDE_PATTERNS:
                return True

            # Excluded directory patterns (partial match for .egg-info, etc.)
            for dir_pattern in EXCLUDE_DIR_PATTERNS:
                if dir_pattern in part:
                    return True

            # Hidden directories (except allowed)
            if part.startswith(".") and part not in INCLUDE_HIDDEN:
                return True

        # Check file name patterns
        name = path.name

        # Excluded file patterns
        for pattern in EXCLUDE_PATTERNS:
            if "*" in pattern:
                # Wildcard pattern (*.pyc, etc.)
                suffix = pattern.replace("*", "")
                if name.endswith(suffix):
                    return True
            elif name == pattern:
                return True

        # Hidden files (except allowed)
        if name.startswith(".") and name not in INCLUDE_HIDDEN:
            return True

        return False

    def count_files(self) -> int:
        """Count total number of files discovered.

        Returns:
            Total file count

        Examples:
            >>> count = discovery.count_files()
            >>> print(f"Total files: {count}")
        """
        return len(self.discover_all_files())

    def generate_manifest(self) -> Dict[str, Any]:
        """Generate installation manifest with file metadata.

        Manifest format:
        {
            "version": "1.0",
            "total_files": 201,
            "files": [
                {"path": "commands/auto-implement.md", "size": 1234},
                {"path": "lib/security_utils.py", "size": 5678},
                ...
            ]
        }

        Returns:
            Manifest dictionary

        Examples:
            >>> manifest = discovery.generate_manifest()
            >>> print(f"Total files: {manifest['total_files']}")
        """
        files = self.discover_all_files()

        manifest = {
            "version": "1.0",
            "total_files": len(files),
            "files": []
        }

        for file_path in files:
            relative = file_path.relative_to(self.plugin_dir)
            manifest["files"].append({
                "path": str(relative).replace("\\", "/"),  # Unix-style paths
                "size": file_path.stat().st_size
            })

        return manifest

    def save_manifest(self, manifest_path: Path) -> None:
        """Save installation manifest to JSON file.

        Args:
            manifest_path: Path to save manifest (e.g., config/installation_manifest.json)

        Examples:
            >>> manifest_path = plugin_dir / "config" / "installation_manifest.json"
            >>> discovery.save_manifest(manifest_path)
        """
        manifest = self.generate_manifest()

        # Create parent directory if needed
        manifest_path.parent.mkdir(parents=True, exist_ok=True)

        # Save as formatted JSON
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

    def validate_against_manifest(self, manifest: Dict[str, Any]) -> List[str]:
        """Validate current files against installation manifest.

        Detects files that are in manifest but missing from filesystem.

        Args:
            manifest: Installation manifest dictionary

        Returns:
            List of missing file paths (relative to plugin_dir)

        Examples:
            >>> missing = discovery.validate_against_manifest(manifest)
            >>> if missing:
            ...     print(f"Missing {len(missing)} files:")
            ...     for file in missing:
            ...         print(f"  - {file}")
        """
        current_files = self.discover_all_files()
        current_relative = {
            str(f.relative_to(self.plugin_dir)).replace("\\", "/")
            for f in current_files
        }

        expected_files = {f["path"] for f in manifest["files"]}

        missing = expected_files - current_relative

        return sorted(missing)

    def get_relative_path(self, file_path: Path) -> Path:
        """Get relative path for file (for copying).

        Args:
            file_path: Absolute path to file

        Returns:
            Relative path from plugin_dir

        Examples:
            >>> abs_path = plugin_dir / "lib" / "nested" / "utils.py"
            >>> rel_path = discovery.get_relative_path(abs_path)
            >>> print(rel_path)  # lib/nested/utils.py
        """
        return file_path.relative_to(self.plugin_dir)
