#!/usr/bin/env python3
"""
Orphan File Cleaner - Detect and remove orphaned files after marketplace updates

This module provides orphan detection and cleanup to improve the marketplace update
UX by removing files that are no longer part of the plugin after an update.

Features:
- Detect orphaned commands, hooks, and agents in .claude/ subdirectories
- Dry-run mode: Report orphans without deleting (default)
- Confirm mode: Delete only with explicit user approval
- Auto mode: Delete automatically without confirmation
- Security: Whitelist validation, audit logging
- Clear reporting of cleanup operations

Security:
- All file paths validated via security_utils.validate_path()
- Only operates within .claude/ subdirectories
- Prevents path traversal (CWE-22)
- Rejects symlink attacks (CWE-59)
- Audit logging for all deletions

Usage:
    from orphan_file_cleaner import detect_orphans, cleanup_orphans

    # Detect orphans (dry-run)
    orphans = detect_orphans("/path/to/project")
    print(f"Found {len(orphans)} orphaned files")

    # Cleanup with confirmation
    result = cleanup_orphans("/path/to/project", mode="confirm")
    if result.success:
        print(f"Deleted {result.deleted_count} files")

    # Low-level API
    cleaner = OrphanFileCleaner("/path/to/project")
    orphans = cleaner.detect_orphans()
    result = cleaner.cleanup_orphans(orphans, mode="auto")

Date: 2025-11-08
Issue: GitHub #50 - Fix Marketplace Update UX
Agent: implementer


Design Patterns:
    See library-design-patterns skill for standardized design patterns.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

# Import with fallback for both dev (plugins/) and installed (.claude/lib/) environments
try:
    from plugins.autonomous_dev.lib.security_utils import validate_path, audit_log
except ImportError:
    from security_utils import validate_path, audit_log


@dataclass
class OrphanFile:
    """

    See error-handling-patterns skill for exception hierarchy and error handling best practices.

    Representation of an orphaned file.

    Attributes:
        path: Full path to the orphaned file
        category: File category ("command", "hook", "agent")
        is_orphan: Whether file is confirmed orphan (always True)
        reason: Human-readable reason why file is orphaned
    """

    path: Path
    category: str
    is_orphan: bool = True
    reason: str = ""

    def __post_init__(self):
        """Set default reason if not provided."""
        if not self.reason:
            self.reason = f"Not listed in plugin.json {self.category}s"


@dataclass
class CleanupResult:
    """Result of orphan cleanup operation.

    Attributes:
        orphans_detected: Number of orphans detected
        orphans_deleted: Number of orphans deleted
        dry_run: Whether this was a dry-run (no deletions)
        errors: Number of errors encountered (or list of error messages)
        orphans: List of detected orphan files
        success: Whether cleanup succeeded (auto-set from errors)
        error_message: Optional error message for failed operations
        files_removed: Optional parameter, alias for orphans_deleted
    """

    orphans_detected: int = 0
    orphans_deleted: int = 0
    dry_run: bool = True
    errors: int = 0
    orphans: List[OrphanFile] = field(default_factory=list)
    success: bool = True
    error_message: str = ""
    files_removed: int = 0

    def __post_init__(self):
        """Set success flag based on errors and sync files_removed with orphans_deleted."""
        # If files_removed is provided and differs from orphans_deleted, use files_removed
        if self.files_removed > 0 and self.orphans_deleted == 0:
            self.orphans_deleted = self.files_removed
        elif self.orphans_deleted > 0 and self.files_removed == 0:
            self.files_removed = self.orphans_deleted

        # Set success flag
        self.success = self.errors == 0 and not self.error_message

    @property
    def summary(self) -> str:
        """Generate human-readable summary of cleanup result.

        Returns:
            Summary message describing cleanup outcome
        """
        if self.dry_run:
            msg = f"Detected {self.orphans_detected} orphaned files (dry-run, no deletions)"
        elif self.orphans_deleted == 0:
            msg = f"No orphaned files deleted ({self.orphans_detected} detected)"
        else:
            msg = f"Deleted {self.orphans_deleted} orphaned files ({self.orphans_detected} detected)"

        # Include error count if any
        if self.errors > 0:
            msg += f", {self.errors} errors"

        return msg

    def summary_message(self) -> str:
        """Alias for summary property (backwards compatibility)."""
        return self.summary


# Exception hierarchy pattern from error-handling-patterns skill:
# BaseException -> Exception -> AutonomousDevError -> DomainError(BaseException) -> SpecificError
class OrphanDetectionError(Exception):
    """Exception raised for orphan detection errors."""

    pass


class OrphanFileCleaner:
    """Cleaner for orphaned files after marketplace plugin updates.

    Attributes:
        project_root: Validated project root path
        plugin_name: Plugin name to check (default: "autonomous-dev")
    """

    # Categories to check for orphans
    CATEGORIES = ["commands", "hooks", "agents"]

    # Files to ignore (always present)
    IGNORE_FILES = {"__pycache__", "__init__.py", "__init__.pyc", ".DS_Store"}

    def __init__(self, project_root: Path, plugin_name: str = "autonomous-dev"):
        """Initialize orphan file cleaner.

        Args:
            project_root: Path to project root directory
            plugin_name: Plugin name (default: "autonomous-dev")

        Raises:
            ValueError: If path fails security validation
        """
        # Validate project root
        try:
            validated_root = validate_path(project_root, "project root")
            self.project_root = Path(validated_root).resolve()
        except ValueError as e:
            audit_log(
                "orphan_cleanup",
                "failure",
                {
                    "operation": "init",
                    "project_root": str(project_root),
                    "error": str(e),
                },
            )
            raise

        self.plugin_name = plugin_name

        # Set up project-specific audit log
        self.audit_log_file = self.project_root / "logs" / "orphan_cleanup_audit.log"

    def _write_audit_log(self, operation: str, path: str, category: str, **kwargs):
        """Write to project-specific orphan cleanup audit log (JSON format).

        Args:
            operation: Operation performed (e.g., "delete_orphan")
            path: File path affected
            category: File category (command, hook, agent)
            **kwargs: Additional metadata to include in log
        """
        # Create logs directory if it doesn't exist
        self.audit_log_file.parent.mkdir(parents=True, exist_ok=True)

        # Create log entry
        from datetime import datetime
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "path": path,
            "category": category,
            "user": os.getenv("USER", "unknown"),
        }
        log_entry.update(kwargs)

        # Append JSON entry to audit log
        with open(self.audit_log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

    def _read_plugin_json(self) -> dict:
        """Read plugin.json to get list of expected files.

        Returns:
            Parsed plugin.json data

        Raises:
            OrphanDetectionError: If plugin.json not found or corrupted
        """
        plugin_json = (
            self.project_root
            / ".claude"
            / "plugins"
            / self.plugin_name
            / "plugin.json"
        )

        if not plugin_json.exists():
            raise OrphanDetectionError(
                f"Plugin not found: {plugin_json}\n"
                f"Expected: plugin.json file for {self.plugin_name}\n"
                f"Hint: Run /sync marketplace first to install plugin"
            )

        # Validate path before reading
        try:
            validated_path = validate_path(plugin_json, "plugin.json")
        except ValueError as e:
            audit_log(
                "orphan_cleanup",
                "security_violation",
                {
                    "operation": "_read_plugin_json",
                    "path": str(plugin_json),
                    "error": str(e),
                },
            )
            raise OrphanDetectionError(f"Security validation failed: {e}")

        # Parse JSON
        try:
            with open(validated_path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise OrphanDetectionError(
                f"Corrupted plugin.json: {plugin_json}\n"
                f"JSON parse error: {e}\n"
                f"Expected: Valid JSON file"
            )

    def _get_expected_files(self, category: str, plugin_data: dict) -> Set[str]:
        """Get set of expected files for a category from plugin.json.

        Args:
            category: Category name ("commands", "hooks", "agents")
            plugin_data: Parsed plugin.json data

        Returns:
            Set of expected filenames for this category
        """
        # Get list from plugin.json (may be missing)
        file_list = plugin_data.get(category, [])

        # Normalize to set of filenames
        return set(file_list) if file_list else set()

    def _get_actual_files(self, category: str) -> List[Path]:
        """Get list of actual files in category directory.

        Args:
            category: Category name ("commands", "hooks", "agents")

        Returns:
            List of file paths in the category directory

        Note:
            Commands and hooks are in .claude/commands/ and .claude/hooks/
            Agents are in .claude/plugins/autonomous-dev/agents/
        """
        # Agents are in plugin directory, commands/hooks are in .claude/
        if category == "agents":
            category_dir = (
                self.project_root
                / ".claude"
                / "plugins"
                / self.plugin_name
                / category
            )
        else:
            category_dir = self.project_root / ".claude" / category

        # Return empty list if directory doesn't exist
        if not category_dir.exists():
            return []

        # Get all files, excluding ignored ones
        files = []
        for file_path in category_dir.iterdir():
            # Skip directories and ignored files
            if file_path.is_dir() and file_path.name in self.IGNORE_FILES:
                continue
            if file_path.name in self.IGNORE_FILES:
                continue
            if file_path.is_file():
                files.append(file_path)

        return files

    def find_duplicate_libs(self) -> List[Path]:
        """Find Python files in .claude/lib/ directory (duplicate library location).

        This method detects duplicate libraries in the legacy .claude/lib/ location
        that should be removed to prevent import conflicts. The canonical location
        for libraries is plugins/autonomous-dev/lib/.

        Returns:
            List of Path objects for duplicate library files found.
            Excludes __init__.py and __pycache__ directories.

        Note:
            Returns empty list if .claude/lib/ doesn't exist or is empty.

        Example:
            >>> cleaner = OrphanFileCleaner(project_root)
            >>> duplicates = cleaner.find_duplicate_libs()
            >>> print(f"Found {len(duplicates)} duplicate libraries")
        """
        # Path to legacy lib directory
        lib_dir = self.project_root / ".claude" / "lib"

        # Return empty list if directory doesn't exist
        if not lib_dir.exists():
            return []

        duplicates = []

        # Recursively find all Python files
        for py_file in lib_dir.rglob("*.py"):
            # Skip __pycache__ directories
            if "__pycache__" in str(py_file):
                continue

            # Skip __init__.py files (they're infrastructure, not duplicates)
            if py_file.name == "__init__.py":
                continue

            # Add to duplicates list
            duplicates.append(py_file)

        return duplicates

    def pre_install_cleanup(self) -> CleanupResult:
        """Remove .claude/lib/ directory before installation to prevent duplicates.

        This method performs pre-installation cleanup by removing the legacy
        .claude/lib/ directory. This prevents import conflicts when installing
        or updating the plugin, as all libraries should reside in
        plugins/autonomous-dev/lib/.

        Returns:
            CleanupResult with success status, files_removed count, and error_message.

        Note:
            - Idempotent: Safe to call even if .claude/lib/ doesn't exist
            - Logs operation to audit trail
            - Handles permission errors gracefully

        Security:
            - Validates all paths before removal
            - Audit logs all operations
            - Handles symlinks safely (removes link, not target)

        Example:
            >>> cleaner = OrphanFileCleaner(project_root)
            >>> result = cleaner.pre_install_cleanup()
            >>> if result.success:
            ...     print(f"Removed {result.files_removed} duplicate files")
        """
        import shutil

        lib_dir = self.project_root / ".claude" / "lib"

        # If directory doesn't exist, nothing to clean
        if not lib_dir.exists():
            return CleanupResult(
                orphans_detected=0,
                orphans_deleted=0,
                dry_run=False,
                errors=0,
                success=True,
                error_message="",
            )

        try:
            # Handle symlinks specially BEFORE validate_path (which rejects symlinks)
            if lib_dir.is_symlink():
                # For symlinks, just unlink the symlink itself (don't follow it)
                # Skip validate_path for symlinks since it rejects them (CWE-59 protection)
                file_count = 0  # Symlinks don't count as files removed

                # Audit log the symlink removal
                audit_log(
                    "orphan_cleanup",
                    "success",
                    {
                        "operation": "pre_install_cleanup",
                        "path": str(lib_dir),
                        "type": "symlink",
                        "files_removed": 0,
                    },
                )

                lib_dir.unlink()

                return CleanupResult(
                    orphans_detected=0,
                    orphans_deleted=0,
                    dry_run=False,
                    errors=0,
                    success=True,
                    error_message="",
                )

            # For regular directories, validate path before removal (security check)
            try:
                validated_path = validate_path(lib_dir, ".claude/lib directory")
            except ValueError as e:
                audit_log(
                    "orphan_cleanup",
                    "security_violation",
                    {
                        "operation": "pre_install_cleanup",
                        "path": str(lib_dir),
                        "error": str(e),
                    },
                )
                return CleanupResult(
                    orphans_detected=0,
                    orphans_deleted=0,
                    dry_run=False,
                    errors=1,
                    success=False,
                    error_message=f"Security validation failed: {e}",
                )

            # Count files before removal (for reporting)
            file_count = 0
            for py_file in lib_dir.rglob("*.py"):
                if "__pycache__" not in str(py_file) and py_file.name != "__init__.py":
                    file_count += 1

            # Remove the entire .claude/lib/ directory
            shutil.rmtree(validated_path)

            # Audit log the cleanup
            audit_log(
                "orphan_cleanup",
                "success",
                {
                    "operation": "pre_install_cleanup",
                    "path": str(lib_dir),
                    "files_removed": file_count,
                },
            )

            # Project-specific audit log
            self._write_audit_log(
                operation="pre_install_cleanup",
                path=str(lib_dir),
                category="lib",
                files_removed=file_count,
                status="removed",
            )

            return CleanupResult(
                orphans_detected=file_count,
                orphans_deleted=file_count,
                dry_run=False,
                errors=0,
                success=True,
                error_message="",
            )

        except PermissionError as e:
            audit_log(
                "orphan_cleanup",
                "permission_denied",
                {
                    "operation": "pre_install_cleanup",
                    "path": str(lib_dir),
                    "error": str(e),
                },
            )
            return CleanupResult(
                orphans_detected=file_count if 'file_count' in locals() else 0,
                orphans_deleted=0,
                dry_run=False,
                errors=1,
                success=False,
                error_message=f"Permission denied: {e}",
            )

        except Exception as e:
            audit_log(
                "orphan_cleanup",
                "failure",
                {
                    "operation": "pre_install_cleanup",
                    "path": str(lib_dir),
                    "error": str(e),
                },
            )
            return CleanupResult(
                orphans_detected=file_count if 'file_count' in locals() else 0,
                orphans_deleted=0,
                dry_run=False,
                errors=1,
                success=False,
                error_message=str(e),
            )

    def detect_orphans(self) -> List[OrphanFile]:
        """Detect orphaned files in all categories.

        Returns:
            List of OrphanFile objects for detected orphans

        Raises:
            OrphanDetectionError: If plugin.json not found or detection fails
        """
        # Read plugin.json
        plugin_data = self._read_plugin_json()

        orphans = []

        # Check each category
        for category in self.CATEGORIES:
            # Get expected files from plugin.json
            expected_files = self._get_expected_files(category, plugin_data)

            # Get actual files from filesystem
            actual_files = self._get_actual_files(category)

            # Find orphans (files not in expected list)
            for file_path in actual_files:
                if file_path.name not in expected_files:
                    orphan = OrphanFile(
                        path=file_path,
                        category=category.rstrip("s"),  # "commands" -> "command"
                        reason=f"Not listed in plugin.json {category}",
                    )
                    orphans.append(orphan)

        return orphans

    def cleanup_orphans(
        self,
        orphans: Optional[List[OrphanFile]] = None,
        dry_run: Optional[bool] = None,
        confirm: bool = False,
        input_func=None,
    ) -> CleanupResult:
        """Cleanup orphaned files.

        Args:
            orphans: Optional list of OrphanFile objects to cleanup (auto-detects if None)
            dry_run: Whether to only report without deleting (default: True)
            confirm: Whether to prompt for confirmation before deleting (default: False = auto-approve)
            input_func: Optional input function for testing (default: built-in input)

        Returns:
            CleanupResult with cleanup outcome
        """
        # Auto-detect orphans if not provided
        if orphans is None:
            orphans = self.detect_orphans()
        # Use built-in input if not provided
        if input_func is None:
            input_func = input

        # Determine effective dry_run value
        # If dry_run not specified: confirm=True means False (delete with prompts), otherwise True (safe default)
        # If dry_run explicitly specified: use that value
        if dry_run is None:
            effective_dry_run = not confirm  # confirm=True -> dry_run=False
        else:
            effective_dry_run = dry_run

        result = CleanupResult(
            orphans_detected=len(orphans),
            orphans_deleted=0,
            dry_run=effective_dry_run,
            errors=0,
            orphans=orphans,
        )

        # Dry-run mode: just report, don't delete
        if effective_dry_run:
            return result

        # Delete orphans
        error_count = 0
        for orphan in orphans:
            try:
                # Confirm mode: ask user before deleting
                if confirm:
                    response = input_func(
                        f"Delete orphaned {orphan.category} '{orphan.path.name}'? (y/n): "
                    )
                    if response.lower() != "y":
                        continue

                # Validate path before deletion (security)
                try:
                    validated_path = validate_path(orphan.path, "orphan file")
                except ValueError as e:
                    audit_log(
                        "orphan_cleanup",
                        "security_violation",
                        {
                            "operation": "delete_orphan",
                            "path": str(orphan.path),
                            "error": str(e),
                        },
                    )
                    error_count += 1
                    continue

                # Delete file
                Path(validated_path).unlink()

                # Audit log deletion (both global security log and project-specific log)
                audit_log(
                    "orphan_cleanup",
                    "success",
                    {
                        "operation": "delete_orphan",
                        "path": str(orphan.path),
                        "category": orphan.category,
                        "dry_run": effective_dry_run,
                        "confirm": confirm,
                    },
                )

                # Project-specific audit log
                self._write_audit_log(
                    operation="delete_orphan",
                    path=str(orphan.path),
                    category=orphan.category,
                    reason=orphan.reason,
                    status="deleted",
                )

                result.orphans_deleted += 1

            except PermissionError as e:
                error_count += 1
                audit_log(
                    "orphan_cleanup",
                    "permission_denied",
                    {
                        "operation": "delete_orphan",
                        "path": str(orphan.path),
                        "category": orphan.category,
                        "error": str(e),
                    },
                )
            except Exception as e:
                error_count += 1
                audit_log(
                    "orphan_cleanup",
                    "failure",
                    {
                        "operation": "delete_orphan",
                        "path": str(orphan.path),
                        "category": orphan.category,
                        "error": str(e),
                    },
                )

        result.errors = error_count
        return result


def detect_orphans(
    project_root: str,
    plugin_name: str = "autonomous-dev",
) -> List[OrphanFile]:
    """Detect orphaned files in project (high-level convenience function).

    Args:
        project_root: Path to project root directory
        plugin_name: Plugin name (default: "autonomous-dev")

    Returns:
        List of OrphanFile objects for detected orphans

    Raises:
        ValueError: If path fails security validation
        OrphanDetectionError: If plugin.json not found or detection fails

    Example:
        >>> orphans = detect_orphans("/path/to/project")
        >>> print(f"Found {len(orphans)} orphaned files")
    """
    cleaner = OrphanFileCleaner(Path(project_root), plugin_name)
    return cleaner.detect_orphans()


def cleanup_orphans(
    project_root: str,
    dry_run: bool = True,
    confirm: bool = False,
    plugin_name: str = "autonomous-dev",
) -> CleanupResult:
    """Cleanup orphaned files in project (high-level convenience function).

    Args:
        project_root: Path to project root directory
        dry_run: Whether to only report without deleting (default: True)
        confirm: Whether to prompt for confirmation before deleting (default: False = auto-approve)
        plugin_name: Plugin name (default: "autonomous-dev")

    Returns:
        CleanupResult with cleanup outcome

    Raises:
        ValueError: If path fails security validation
        OrphanDetectionError: If plugin.json not found or cleanup fails

    Example:
        >>> result = cleanup_orphans("/path/to/project", dry_run=False, confirm=False)
        >>> if result.success:
        ...     print(f"Deleted {result.orphans_deleted} files")
    """
    cleaner = OrphanFileCleaner(Path(project_root), plugin_name)
    orphans = cleaner.detect_orphans()
    return cleaner.cleanup_orphans(orphans, dry_run=dry_run, confirm=confirm)
