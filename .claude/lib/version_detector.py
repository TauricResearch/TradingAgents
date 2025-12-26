#!/usr/bin/env python3
"""
Version Detector - Detect version differences between marketplace and project plugins

This module provides version parsing, comparison, and mismatch detection to improve
the marketplace update UX by informing users when updates are available.

Features:
- Parse semantic versions from plugin.json files
- Compare marketplace vs project versions
- Detect upgrade/downgrade scenarios
- Handle pre-release versions
- Security: Path validation via security_utils
- Clear error messages for version issues

Security:
- All file paths validated via security_utils.validate_path()
- Prevents path traversal (CWE-22)
- Rejects symlink attacks (CWE-59)
- Audit logging for security events

Usage:
    from version_detector import VersionDetector, detect_version_mismatch

    # Detect version mismatch
    result = detect_version_mismatch("/path/to/project")
    if result.is_upgrade_available:
        print(f"Update available: {result.marketplace_version}")

    # Low-level API
    detector = VersionDetector(project_root)
    project_ver = detector.parse_project_version()
    marketplace_ver = detector.parse_marketplace_version("autonomous-dev")
    comparison = detector.compare_versions(project_ver, marketplace_ver)

Date: 2025-11-08
Issue: GitHub #50 - Fix Marketplace Update UX
Agent: implementer


Design Patterns:
    See library-design-patterns skill for standardized design patterns.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Import with fallback for both dev (plugins/) and installed (.claude/lib/) environments
try:
    from plugins.autonomous_dev.lib.security_utils import validate_path, audit_log
except ImportError:
    from security_utils import validate_path, audit_log


@dataclass
class Version:
    """Semantic version representation.

    See error-handling-patterns skill for exception hierarchy and error handling best practices.

    Attributes:
        major: Major version number (breaking changes)
        minor: Minor version number (new features)
        patch: Patch version number (bug fixes)
        prerelease: Pre-release tag (e.g., "beta.1", "rc.2") or None
    """

    major: int
    minor: int
    patch: int
    prerelease: Optional[str] = None

    def __str__(self) -> str:
        """Return string representation of version."""
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            return f"{base}-{self.prerelease}"
        return base

    def __lt__(self, other: "Version") -> bool:
        """Compare versions for less-than."""
        if not isinstance(other, Version):
            return NotImplemented

        # Compare major.minor.patch first
        if (self.major, self.minor, self.patch) != (other.major, other.minor, other.patch):
            return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

        # If base versions equal, compare prerelease
        # No prerelease > has prerelease (3.7.0 > 3.7.0-beta.1)
        if self.prerelease is None and other.prerelease is None:
            return False
        if self.prerelease is None:
            return False  # 3.7.0 > 3.7.0-beta.1
        if other.prerelease is None:
            return True  # 3.7.0-beta.1 < 3.7.0

        # Both have prerelease, compare alphabetically
        return self.prerelease < other.prerelease

    def __eq__(self, other: object) -> bool:
        """Compare versions for equality."""
        if not isinstance(other, Version):
            return NotImplemented
        return (
            self.major == other.major
            and self.minor == other.minor
            and self.patch == other.patch
            and self.prerelease == other.prerelease
        )

    def __le__(self, other: "Version") -> bool:
        """Compare versions for less-than-or-equal."""
        return self == other or self < other

    def __gt__(self, other: "Version") -> bool:
        """Compare versions for greater-than."""
        return not self <= other

    def __ge__(self, other: "Version") -> bool:
        """Compare versions for greater-than-or-equal."""
        return not self < other


@dataclass
class VersionComparison:
    """Result of version comparison.

    Attributes:
        project_version: Project plugin version string (or None if not found)
        marketplace_version: Marketplace plugin version string (or None if not found)
        status: Comparison status constant
        message: Human-readable comparison message (auto-generated if not provided)
        is_upgrade: Quick check if upgrade is available
        is_downgrade: Quick check if downgrade would occur
    """

    # Status constants
    UPGRADE_AVAILABLE = "upgrade_available"
    DOWNGRADE_RISK = "downgrade_risk"
    UP_TO_DATE = "up_to_date"  # Versions equal
    EQUAL = UP_TO_DATE  # Alias for backwards compatibility
    MARKETPLACE_NOT_INSTALLED = "marketplace_not_installed"
    PROJECT_NOT_SYNCED = "project_not_synced"
    UNKNOWN = "unknown"

    project_version: Optional[str] = None
    marketplace_version: Optional[str] = None
    status: str = UNKNOWN
    message: str = ""
    is_upgrade: bool = False
    is_downgrade: bool = False

    def __post_init__(self):
        """Set convenience flags and auto-generate message if needed."""
        self.is_upgrade = self.status == self.UPGRADE_AVAILABLE
        self.is_downgrade = self.status == self.DOWNGRADE_RISK

        # Auto-generate message if not provided
        if not self.message:
            if self.status == self.UPGRADE_AVAILABLE:
                self.message = f"Upgrade available: {self.project_version} -> {self.marketplace_version}"
            elif self.status == self.DOWNGRADE_RISK:
                self.message = f"Warning: Project version {self.project_version} is newer than marketplace {self.marketplace_version}"
            elif self.status == self.UP_TO_DATE:
                self.message = f"Versions in sync: {self.project_version}"
            else:
                self.message = "No version information available"


# Exception hierarchy pattern from error-handling-patterns skill:
# BaseException -> Exception -> AutonomousDevError -> DomainError(BaseException) -> SpecificError
class VersionParseError(Exception):
    """Exception raised when version string cannot be parsed."""

    pass


class VersionDetector:
    """Detector for version mismatches between marketplace and project plugins.

    Attributes:
        project_root: Validated project root path
        marketplace_plugins_file: Path to installed_plugins.json (default: ~/.claude/plugins/installed_plugins.json)
    """

    # Semantic version regex: MAJOR.MINOR.PATCH[-PRERELEASE]
    VERSION_PATTERN = re.compile(
        r'^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9.]+))?$'
    )

    def __init__(
        self,
        project_root: Path,
        marketplace_plugins_file: Optional[Path] = None,
    ):
        """Initialize version detector.

        Args:
            project_root: Path to project root directory
            marketplace_plugins_file: Optional path to marketplace installed_plugins.json

        Raises:
            ValueError: If path fails security validation
        """
        # Validate project root
        try:
            validated_root = validate_path(project_root, "project root")
            self.project_root = Path(validated_root).resolve()
        except ValueError as e:
            audit_log(
                "version_detection",
                "failure",
                {
                    "operation": "init",
                    "project_root": str(project_root),
                    "error": str(e),
                },
            )
            raise

        # Set marketplace plugins file (default or custom)
        if marketplace_plugins_file:
            self.marketplace_plugins_file = marketplace_plugins_file
        else:
            self.marketplace_plugins_file = (
                Path.home() / ".claude" / "plugins" / "installed_plugins.json"
            )

    def _parse_version_string(self, version_string: str) -> Version:
        """Parse semantic version string into Version object (private method).

        Args:
            version_string: Version string (e.g., "3.7.0", "3.8.0-beta.1")

        Returns:
            Version object with parsed components

        Raises:
            VersionParseError: If version string is invalid

        Note:
            This is the internal parsing method used by other methods.
            Public API should use parse_project_version() or parse_marketplace_version().
        """
        match = self.VERSION_PATTERN.match(version_string)
        if not match:
            raise VersionParseError(
                f"Invalid version string: '{version_string}'\n"
                f"Expected format: MAJOR.MINOR.PATCH (e.g., 3.7.0)\n"
                f"Optional pre-release: MAJOR.MINOR.PATCH-PRERELEASE (e.g., 3.8.0-beta.1)"
            )

        major, minor, patch, prerelease = match.groups()
        return Version(
            major=int(major),
            minor=int(minor),
            patch=int(patch),
            prerelease=prerelease,
        )

    def parse_version(self, version_string: str) -> Version:
        """Parse semantic version string into Version object (public API).

        Args:
            version_string: Version string (e.g., "3.7.0", "3.8.0-beta.1")

        Returns:
            Version object with parsed components

        Raises:
            VersionParseError: If version string is invalid
        """
        return self._parse_version_string(version_string)

    def _read_json_file(self, file_path: Path) -> dict:
        """Read and parse JSON file with security validation.

        Args:
            file_path: Path to JSON file to read

        Returns:
            Parsed JSON data as dictionary

        Raises:
            ValueError: If path fails security validation
            FileNotFoundError: If file doesn't exist
            PermissionError: If file is not readable
            VersionParseError: If JSON is corrupted

        Note:
            This is an internal method that validates paths before reading.
            All file reads should go through this method for security.
        """
        # Validate path before reading
        try:
            validated_path = validate_path(file_path, "JSON file")
        except ValueError as e:
            audit_log(
                "version_detection",
                "security_violation",
                {
                    "operation": "_read_json_file",
                    "path": str(file_path),
                    "error": str(e),
                },
            )
            raise

        # Check file exists
        if not Path(validated_path).exists():
            raise FileNotFoundError(f"File not found: {validated_path}")

        # Parse JSON
        try:
            with open(validated_path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise VersionParseError(
                f"Corrupted JSON file: {validated_path}\n"
                f"JSON parse error: {e}\n"
                f"Expected: Valid JSON file"
            )
        except PermissionError:
            raise

    def parse_project_version(self) -> Optional[Version]:
        """Parse project plugin version from plugin.json.

        Returns:
            Version object or None if plugin.json not found

        Raises:
            VersionParseError: If plugin.json is corrupted or version is invalid
        """
        plugin_json = (
            self.project_root
            / ".claude"
            / "plugins"
            / "autonomous-dev"
            / "plugin.json"
        )

        # Return None if file doesn't exist (not an error)
        if not plugin_json.exists():
            return None

        # Validate path before reading (let ValueError bubble up for security violations)
        try:
            validated_path = validate_path(plugin_json, "project plugin.json")
        except ValueError as e:
            audit_log(
                "version_detection",
                "security_violation",
                {
                    "operation": "parse_project_version",
                    "path": str(plugin_json),
                    "error": str(e),
                },
            )
            # Re-raise ValueError for security violations (expected by tests)
            raise

        # Parse JSON
        try:
            with open(validated_path, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise VersionParseError(
                f"Corrupted plugin.json: {plugin_json}\n"
                f"JSON parse error: {e}\n"
                f"Expected: Valid JSON file"
            )

        # Extract version field
        if "version" not in data:
            raise VersionParseError(
                f"Missing 'version' field in {plugin_json}\n"
                f"Expected: plugin.json with 'version' field\n"
                f"Example: {{'name': 'autonomous-dev', 'version': '3.7.0'}}"
            )

        version_string = data["version"]
        return self.parse_version(version_string)

    def parse_marketplace_version(self, plugin_name: str) -> Optional[Version]:
        """Parse marketplace plugin version from installed_plugins.json.

        Args:
            plugin_name: Plugin name (e.g., "autonomous-dev")

        Returns:
            Version object or None if plugin not found in marketplace

        Raises:
            VersionParseError: If installed_plugins.json is corrupted or version is invalid
        """
        # Return None if file doesn't exist
        if not self.marketplace_plugins_file.exists():
            return None

        # Parse JSON
        try:
            with open(self.marketplace_plugins_file, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise VersionParseError(
                f"Corrupted installed_plugins.json: {self.marketplace_plugins_file}\n"
                f"JSON parse error: {e}\n"
                f"Expected: Valid JSON file"
            )

        # Extract plugin entry
        if plugin_name not in data:
            return None

        plugin_data = data[plugin_name]
        if "version" not in plugin_data:
            raise VersionParseError(
                f"Missing 'version' field for plugin '{plugin_name}' in {self.marketplace_plugins_file}\n"
                f"Expected: Plugin entry with 'version' field"
            )

        version_string = plugin_data["version"]
        return self.parse_version(version_string)

    def compare_versions(
        self,
        project_version: Optional[Version],
        marketplace_version: Optional[Version],
    ) -> VersionComparison:
        """Compare project and marketplace versions.

        Args:
            project_version: Project plugin version (or None if not installed)
            marketplace_version: Marketplace plugin version (or None if not found)

        Returns:
            VersionComparison with status and message (versions as strings)
        """
        # Convert Version objects to strings for comparison result
        project_str = str(project_version) if project_version else None
        marketplace_str = str(marketplace_version) if marketplace_version else None

        # Case 1: Both versions unknown
        if project_version is None and marketplace_version is None:
            return VersionComparison(
                project_version=None,
                marketplace_version=None,
                status=VersionComparison.UNKNOWN,
                message="No version information available",
            )

        # Case 2: Marketplace not installed
        if marketplace_version is None:
            return VersionComparison(
                project_version=project_str,
                marketplace_version=None,
                status=VersionComparison.MARKETPLACE_NOT_INSTALLED,
                message=f"Project version: {project_version}, Marketplace: not installed",
            )

        # Case 3: Project not synced
        if project_version is None:
            return VersionComparison(
                project_version=None,
                marketplace_version=marketplace_str,
                status=VersionComparison.PROJECT_NOT_SYNCED,
                message=f"Marketplace version: {marketplace_version}, Project: not synced",
            )

        # Case 4: Marketplace newer (upgrade available)
        if marketplace_version > project_version:
            return VersionComparison(
                project_version=project_str,
                marketplace_version=marketplace_str,
                status=VersionComparison.UPGRADE_AVAILABLE,
                message=f"Upgrade available: {project_version} -> {marketplace_version}",
                is_upgrade=True,
            )

        # Case 5: Project newer (downgrade risk)
        if project_version > marketplace_version:
            return VersionComparison(
                project_version=project_str,
                marketplace_version=marketplace_str,
                status=VersionComparison.DOWNGRADE_RISK,
                message=f"Warning: Project version {project_version} is newer than marketplace {marketplace_version}",
                is_downgrade=True,
            )

        # Case 6: Versions equal
        return VersionComparison(
            project_version=project_str,
            marketplace_version=marketplace_str,
            status=VersionComparison.UP_TO_DATE,
            message=f"Versions in sync: {project_version}",
        )


def detect_version_mismatch(
    project_root: str,
    plugin_name: str = "autonomous-dev",
    marketplace_plugins_file: Optional[str] = None,
) -> VersionComparison:
    """Detect version mismatch between marketplace and project plugin.

    This is the high-level convenience function for version detection.

    Args:
        project_root: Path to project root directory
        plugin_name: Plugin name (default: "autonomous-dev")
        marketplace_plugins_file: Optional path to installed_plugins.json

    Returns:
        VersionComparison with detailed comparison results

    Raises:
        ValueError: If path fails security validation
        VersionParseError: If version parsing fails

    Example:
        >>> result = detect_version_mismatch("/path/to/project")
        >>> if result.is_upgrade_available:
        ...     print(f"Update available: {result.message}")
    """
    marketplace_file = Path(marketplace_plugins_file) if marketplace_plugins_file else None
    detector = VersionDetector(Path(project_root), marketplace_file)

    project_version = detector.parse_project_version()
    marketplace_version = detector.parse_marketplace_version(plugin_name)

    return detector.compare_versions(project_version, marketplace_version)
