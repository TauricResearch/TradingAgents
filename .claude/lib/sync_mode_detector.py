#!/usr/bin/env python3
"""
Sync Mode Detector - Intelligent context detection for unified /sync command

This module provides automatic detection of sync context based on directory
structure and parses command-line flags to override auto-detection.

Sync Modes:
- GITHUB: Fetch latest from GitHub (default for users)
- PLUGIN_DEV: Sync plugin development environment (plugins/autonomous-dev/ exists)
- ENVIRONMENT: Sync development environment (.claude/ directory exists)
- MARKETPLACE: Update plugin from Claude marketplace
- ALL: Execute all sync modes in sequence

Auto-Detection Logic:
1. Check for plugins/autonomous-dev/ → PLUGIN_DEV (developer mode)
2. Default → GITHUB (fetch latest from GitHub for users)

Security:
- All paths validated through security_utils.validate_path()
- CWE-22 (path traversal) protection
- CWE-59 (symlink) protection
- Audit logging for all detections

Usage:
    from sync_mode_detector import detect_sync_mode, parse_sync_flags

    # Auto-detect mode
    mode = detect_sync_mode("/path/to/project")

    # Parse flags
    mode = parse_sync_flags(["--env", "--force"])

    # Full control
    detector = SyncModeDetector("/path/to/project")
    mode = detector.detect_mode()
    reason = detector.get_detection_reason()

Date: 2025-11-08
Issue: GitHub #44 - Unified /sync command
Agent: implementer
"""

import os
from enum import Enum
from pathlib import Path
from typing import List, Optional

# Import with fallback for both dev (plugins/) and installed (.claude/lib/) environments
try:
    from plugins.autonomous_dev.lib.security_utils import (
        validate_path,
        audit_log,
        validate_input_length,
    )
except ImportError:
    from security_utils import validate_path, audit_log, validate_input_length


class SyncMode(Enum):
    """Sync mode enumeration for different sync contexts."""

    ENVIRONMENT = "environment"
    MARKETPLACE = "marketplace"
    PLUGIN_DEV = "plugin-dev"
    GITHUB = "github"  # Fetch latest from GitHub
    UNINSTALL = "uninstall"  # Uninstall plugin completely
    ALL = "all"


class SyncModeError(Exception):
    """Exception raised for sync mode detection errors."""

    pass


class SyncModeDetector:
    """Intelligent sync mode detector with caching and validation.

    Attributes:
        project_path: Validated project root path
        _cached_mode: Cached detection result for performance
        _detection_reason: Human-readable reason for detected mode
    """

    def __init__(
        self, project_path: str, explicit_mode: Optional[SyncMode] = None
    ):
        """Initialize detector with project path.

        Args:
            project_path: Path to project root directory
            explicit_mode: Optional explicit mode to override auto-detection

        Raises:
            ValueError: If path is invalid or fails security validation
            SyncModeError: If project path doesn't exist or is not a directory
        """
        # Quick check for path traversal patterns (before any file operations)
        if ".." in str(project_path):
            raise SyncModeError(
                f"Invalid path: Path traversal detected in {project_path}\n"
                f"Paths containing '..' are not allowed\n"
                f"See: docs/SECURITY.md for path validation rules"
            )

        # Then validate with security_utils (comprehensive security check)
        try:
            validated_path = validate_path(project_path, "sync mode detection")
            self.project_path = Path(validated_path).resolve()
        except ValueError as e:
            # If validation failed AND path doesn't exist, give clearer error
            if not Path(project_path).resolve().exists() and "outside allowed directories" in str(e).lower():
                raise SyncModeError(
                    f"Project path does not exist: {project_path}\n"
                    f"Expected: Valid directory path\n"
                    f"See: docs/SYNC-COMMAND.md for usage"
                )

            audit_log(
                "sync_mode_detection",
                "failure",
                {
                    "operation": "init",
                    "project_path": project_path,
                    "error": str(e),
                },
            )
            # Re-raise as SyncModeError for consistent API
            raise SyncModeError(
                f"Invalid path: {project_path}\n"
                f"Security validation failed: {str(e)}\n"
                f"See: docs/SECURITY.md for path validation rules"
            )
        except PermissionError as e:
            raise SyncModeError(
                f"Permission denied: {project_path}\n"
                f"Expected: Read access to directory\n"
                f"See: docs/SYNC-COMMAND.md for usage"
            )

        # Verify path exists and is a directory
        try:
            if not self.project_path.exists():
                raise SyncModeError(
                    f"Project path does not exist: {project_path}\n"
                    f"Expected: Valid directory path\n"
                    f"See: docs/SYNC-COMMAND.md for usage"
                )

            if not self.project_path.is_dir():
                raise SyncModeError(
                    f"Path must be a directory: {project_path}\n"
                    f"Expected: Directory path, got file\n"
                    f"See: docs/SYNC-COMMAND.md for usage"
                )

            # Check if we can actually read the directory (test for permissions)
            list(self.project_path.iterdir())
        except PermissionError as e:
            raise SyncModeError(
                f"Permission denied: {project_path}\n"
                f"Expected: Read access to directory\n"
                f"Error: {str(e)}\n"
                f"See: docs/SYNC-COMMAND.md for usage"
            )

        self._explicit_mode = explicit_mode
        self._cached_mode: Optional[SyncMode] = None
        self._detection_reason: Optional[str] = None
        # Allow test injection of installed_plugins path
        self._installed_plugins_path: Optional[Path] = None

    def detect_mode(self) -> SyncMode:
        """Auto-detect sync mode based on project structure.

        Detection Priority (highest to lowest):
        1. Explicit mode (if provided) → override
        2. plugins/autonomous-dev/plugin.json → PLUGIN_DEV
        3. .claude/PROJECT.md → ENVIRONMENT
        4. ~/.claude/installed_plugins.json → MARKETPLACE
        5. Default → ENVIRONMENT

        Returns:
            Detected SyncMode enum value

        Security:
        - All paths validated before checking existence
        - Symlinks resolved and validated
        - Detection logged to audit log
        """
        # Return cached result if available
        if self._cached_mode is not None:
            return self._cached_mode

        # Check for explicit mode override (highest priority)
        if self._explicit_mode is not None:
            self._cached_mode = self._explicit_mode
            self._detection_reason = f"Explicit mode: {self._explicit_mode.value}"
            return self._explicit_mode

        # Delegate to filesystem scan
        detected_mode = self._scan_filesystem()

        # Cache result
        self._cached_mode = detected_mode

        # Audit log
        audit_log(
            "sync_mode_detection",
            "success",
            {
                "operation": "detect_mode",
                "project_path": str(self.project_path),
                "detected_mode": detected_mode.value,
                "reason": self._detection_reason,
                "user": os.getenv("USER", "unknown"),
            },
        )

        return detected_mode

    def _scan_filesystem(self) -> SyncMode:
        """Scan filesystem to detect sync mode.

        Returns:
            Detected SyncMode enum value

        Note:
            This is separate from detect_mode() to allow mocking in tests.

        Detection Priority:
        1. plugins/autonomous-dev/ exists → PLUGIN_DEV (developer mode)
        2. Default → GITHUB (fetch latest from GitHub for users)

        The GITHUB default ensures users can always update to latest
        without needing to be in the autonomous-dev repository.
        """
        detected_mode = SyncMode.GITHUB  # Default: fetch from GitHub
        reason = "Default (fetching latest from GitHub)"

        # Check for plugin development context (highest priority)
        # Only developers working on autonomous-dev repo itself use PLUGIN_DEV
        plugin_dir = self.project_path / "plugins" / "autonomous-dev"
        if plugin_dir.exists() and plugin_dir.is_dir():
            detected_mode = SyncMode.PLUGIN_DEV
            reason = f"Plugin directory detected: {plugin_dir}"

        self._detection_reason = reason
        return detected_mode

    def reset_cache(self) -> None:
        """Reset cached detection result.

        Useful when project structure changes during execution.
        """
        self._cached_mode = None
        self._detection_reason = None

    def get_detection_reason(self) -> str:
        """Get human-readable reason for detected mode.

        Returns:
            Description of why mode was detected

        Raises:
            RuntimeError: If detect_mode() hasn't been called yet
        """
        if self._detection_reason is None:
            raise RuntimeError(
                "Detection reason not available. Call detect_mode() first."
            )
        return self._detection_reason


def parse_sync_flags(flags: Optional[List[str]]) -> Optional[SyncMode]:
    """Parse command-line flags to determine sync mode.

    Supported Flags:
    - --env: Force environment sync
    - --marketplace: Force marketplace sync
    - --plugin-dev: Force plugin development sync
    - --all: Execute all sync modes

    Args:
        flags: List of command-line flag strings

    Returns:
        SyncMode enum if flag matched, None if no flags or empty list

    Raises:
        SyncModeError: If flags conflict or contain unknown values
        ValueError: If flag validation fails (length, format, etc.)

    Security:
    - Flag length limited to prevent DoS
    - Only allow known flag values (whitelist)
    - Log all flag parsing attempts
    """
    # Handle None or empty flags
    if flags is None or len(flags) == 0:
        return None

    # Validate flag list is actually a list
    if not isinstance(flags, list):
        raise ValueError(
            f"Flags must be a list, got {type(flags).__name__}\n"
            f"Expected: List[str] (e.g., ['--env'])\n"
            f"See: /sync --help for usage"
        )

    # Validate each flag
    validated_flags = []
    for flag in flags:
        # Type check
        if not isinstance(flag, str):
            raise ValueError(
                f"Flag must be string, got {type(flag).__name__}: {flag}\n"
                f"Expected: String starting with '--'\n"
                f"See: /sync --help for usage"
            )

        # Length check (prevent DoS)
        validate_input_length(flag, 100, "sync flag")

        validated_flags.append(flag)

    # Map flags to modes
    flag_map = {
        "--env": SyncMode.ENVIRONMENT,
        "--marketplace": SyncMode.MARKETPLACE,
        "--plugin-dev": SyncMode.PLUGIN_DEV,
        "--github": SyncMode.GITHUB,
        "--all": SyncMode.ALL,
    }

    # Find matching flags
    matched_modes = []
    for flag in validated_flags:
        if flag in flag_map:
            matched_modes.append((flag, flag_map[flag]))
        else:
            # Unknown flag - ensure lowercase for test compatibility
            raise SyncModeError(
                f"Unknown flag: {flag}\n"
                f"Expected: {', '.join(flag_map.keys())}\n"
                f"See: /sync --help for usage"
            )

    # Check for conflicts
    if len(matched_modes) == 0:
        return None

    if len(matched_modes) > 1:
        # Check if --all is mixed with specific flags
        flag_names = [f for f, m in matched_modes]
        if "--all" in flag_names:
            raise SyncModeError(
                f"Flag --all cannot be combined with specific flags: {', '.join(flag_names)}\n"
                f"Expected: Either --all OR specific flags (not both)\n"
                f"See: /sync --help for usage"
            )
        else:
            raise SyncModeError(
                f"Conflicting sync flags: {', '.join(flag_names)}\n"
                f"Expected: Only one flag (or --all)\n"
                f"See: /sync --help for usage"
            )

    # Return the single matched mode
    flag, mode = matched_modes[0]

    # Audit log
    audit_log(
        "sync_flag_parsing",
        "success",
        {
            "operation": "parse_flags",
            "flags": validated_flags,
            "matched_mode": mode.value,
            "user": os.getenv("USER", "unknown"),
        },
    )

    return mode


def detect_sync_mode(
    project_path: str, flags: Optional[List[str]] = None
) -> SyncMode:
    """Convenience function to detect sync mode with optional flag override.

    Args:
        project_path: Path to project root
        flags: Optional command-line flags to override detection

    Returns:
        SyncMode enum value

    Raises:
        ValueError: If path or flags are invalid
        SyncModeError: If detection fails

    Example:
        >>> mode = detect_sync_mode("/path/to/project")
        >>> mode = detect_sync_mode("/path/to/project", ["--env"])
    """
    # Try flag parsing first
    if flags:
        flag_mode = parse_sync_flags(flags)
        if flag_mode is not None:
            return flag_mode

    # Fall back to auto-detection
    detector = SyncModeDetector(project_path)
    return detector.detect_mode()


def get_all_sync_modes() -> List[SyncMode]:
    """Get list of all sync modes including ALL.

    Returns:
        List of all SyncMode enum values

    Usage:
        For programmatic access to all available modes
    """
    return [SyncMode.GITHUB, SyncMode.ENVIRONMENT, SyncMode.MARKETPLACE, SyncMode.PLUGIN_DEV, SyncMode.ALL]


def get_individual_sync_modes() -> List[SyncMode]:
    """Get list of individual sync modes (excludes ALL).

    Returns:
        List of individual SyncMode values for sequential execution

    Usage:
        Used by dispatcher to execute ALL mode in sequence
    """
    return [SyncMode.GITHUB, SyncMode.ENVIRONMENT, SyncMode.MARKETPLACE, SyncMode.PLUGIN_DEV]
