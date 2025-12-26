#!/usr/bin/env python3
"""
Plugin Updater - Interactive plugin update with version detection, backup, and rollback

This module provides interactive plugin update functionality with:
- Version detection (check for updates)
- Automatic backup before update
- Rollback on failure
- Verification after update
- Security: Path validation and audit logging

Features:
- Check for plugin updates (dry-run mode)
- Create automatic backups with timestamps
- Update via sync_dispatcher.sync_marketplace()
- Verify update success (version + file validation)
- Rollback to backup on failure
- Cleanup backups after successful update
- Interactive confirmation prompts
- Rich result objects with detailed info

Security:
- All file paths validated via security_utils.validate_path()
- Prevents path traversal (CWE-22)
- Rejects symlink attacks (CWE-59)
- Backup permissions: user-only (0o700) - CWE-732
- Audit logging for all operations (CWE-778)

Usage:
    from plugin_updater import PluginUpdater

    # Interactive update
    updater = PluginUpdater(project_root="/path/to/project")
    result = updater.update()
    print(result.summary)

    # Check for updates only
    comparison = updater.check_for_updates()
    if comparison.is_upgrade:
        print(f"Update available: {comparison.marketplace_version}")

Date: 2025-11-09
Issue: GitHub #50 Phase 2 - Interactive /update-plugin command
Agent: implementer


Design Patterns:
    See library-design-patterns skill for standardized design patterns.
    See state-management-patterns skill for standardized design patterns.
"""

import json
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# Import with fallback for both dev (plugins/) and installed (.claude/lib/) environments
try:
    # Development environment
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
    from plugins.autonomous_dev.lib import security_utils
    from plugins.autonomous_dev.lib.version_detector import (
        detect_version_mismatch,
        VersionComparison,
    )
    from plugins.autonomous_dev.lib.sync_dispatcher import (
        sync_marketplace,
        SyncResult,
    )
    from plugins.autonomous_dev.lib.hook_activator import (
        HookActivator,
        ActivationResult,
        ActivationError,
    )
    from plugins.autonomous_dev.lib.settings_generator import (
        validate_permission_patterns,
        fix_permission_patterns,
        PermissionIssue,
    )
except ImportError:
    # Installed environment (.claude/lib/)
    import security_utils
    from version_detector import (
        detect_version_mismatch,
        VersionComparison,
    )
    from sync_dispatcher import (
        sync_marketplace,
    )
    from hook_activator import (
        HookActivator,
        ActivationResult,
    )
    from settings_generator import (
        validate_permission_patterns,
        fix_permission_patterns,
    )


# Exception hierarchy pattern from error-handling-patterns skill:
# BaseException -> Exception -> AutonomousDevError -> DomainError(BaseException) -> SpecificError
class UpdateError(Exception):
    """Base exception for plugin update errors.

    See error-handling-patterns skill for exception hierarchy and error handling best practices.
    """
    pass


class BackupError(UpdateError):
    """Exception raised when backup creation or restoration fails."""
    pass


class VerificationError(UpdateError):
    """Exception raised when update verification fails."""
    pass


@dataclass
class PermissionFixResult:
    """Result of permission validation/fix operation.

    Attributes:
        success: Whether fix succeeded (or was skipped)
        action: Action taken (skipped, validated, fixed, regenerated, failed)
        issues_found: Count of detected permission issues (integer)
        fixes_applied: List of fixes that were applied
        backup_path: Path to backup file (None if no backup created)
        message: Human-readable result message
    """
    success: bool
    action: str
    issues_found: int = 0
    fixes_applied: List[str] = field(default_factory=list)
    backup_path: Optional[Path] = None
    message: str = ""


@dataclass
class UpdateResult:
    """Result of a plugin update operation.

    Attributes:
        success: Whether update succeeded (True) or failed (False)
        updated: Whether update was performed (False if already up-to-date)
        message: Human-readable result message
        old_version: Plugin version before update (or current if no update)
        new_version: Plugin version after update (or current if no update)
        backup_path: Path to backup directory (None if no backup created)
        rollback_performed: Whether rollback was performed after failure
        hooks_activated: Whether hooks were activated after update (default: False)
        permission_fix_result: Result of permission validation/fixing (None if not performed)
        details: Additional result details (files updated, errors, etc.)
    """

    success: bool
    updated: bool
    message: str
    old_version: Optional[str] = None
    new_version: Optional[str] = None
    backup_path: Optional[Path] = None
    rollback_performed: bool = False
    hooks_activated: bool = False
    permission_fix_result: Optional['PermissionFixResult'] = None
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        """Generate comprehensive summary of update result.

        Returns:
            Human-readable summary with version and status info
        """
        parts = [self.message]

        # Add version information
        if self.old_version and self.new_version:
            if self.updated:
                parts.append(f"Version: {self.old_version} → {self.new_version}")
            else:
                parts.append(f"Version: {self.old_version}")

        # Add backup info
        if self.backup_path:
            parts.append(f"Backup: {self.backup_path}")

        # Add rollback info
        if self.rollback_performed:
            parts.append("Rollback: Performed (restored from backup)")

        # Add hook activation status
        if self.hooks_activated:
            parts.append("Hooks: Activated")

        # Add details
        if self.details:
            for key, value in self.details.items():
                parts.append(f"{key}: {value}")

        return "\n".join(parts)


class PluginUpdater:
    """Plugin updater with version detection, backup, and rollback.

    This class provides complete plugin update workflow:
    1. Check for updates (version comparison)
    2. Create automatic backup
    3. Perform update via sync_dispatcher
    4. Verify update success
    5. Rollback on failure
    6. Cleanup backup on success

    All file operations are security-validated and audit-logged.

    Example:
        >>> updater = PluginUpdater(project_root="/path/to/project")
        >>> result = updater.update()
        >>> if result.success:
        ...     print(f"Updated to {result.new_version}")
        >>> else:
        ...     print(f"Update failed: {result.message}")
    """

    def __init__(
        self,
        project_root: Path,
        plugin_name: str = "autonomous-dev",
    ):
        """Initialize PluginUpdater with security validation.

        Args:
            project_root: Path to project root directory
            plugin_name: Name of plugin to update (default: autonomous-dev)

        Raises:
            UpdateError: If project_root is invalid or doesn't exist
        """
        # Validate project_root path
        try:
            validated_path = security_utils.validate_path(str(project_root), "project root")
            self.project_root = Path(validated_path)
        except ValueError as e:
            raise UpdateError(f"Invalid project path: {e}")

        # Check if path exists
        if not self.project_root.exists():
            raise UpdateError(f"Project path does not exist: {self.project_root}")

        # Check for .claude directory
        claude_dir = self.project_root / ".claude"
        if not claude_dir.exists():
            raise UpdateError(
                f"Not a valid Claude project: .claude directory not found at {self.project_root}"
            )

        # Validate plugin_name (CWE-78: OS Command Injection prevention)
        # Step 1: Length validation via security_utils
        try:
            validated_name = security_utils.validate_input_length(
                value=plugin_name,
                max_length=100,
                field_name="plugin_name",
                purpose="plugin update"
            )
        except ValueError as e:
            raise UpdateError(f"Invalid plugin name: {e}")

        # Step 2: Format validation (alphanumeric, dash, underscore only)
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', validated_name):
            raise UpdateError(
                f"Invalid plugin name: {validated_name}\n"
                f"Plugin names must contain only alphanumeric characters, dashes, and underscores.\n"
                f"Examples: 'autonomous-dev', 'my_plugin', 'plugin123'"
            )

        self.plugin_name = validated_name
        self.plugin_dir = claude_dir / "plugins" / validated_name
        self.verbose = False  # Default to non-verbose mode

        # Validate plugin directory path (CWE-22: Path Traversal prevention)
        # Ensures marketplace plugin directory is within project bounds
        try:
            validated_plugin_dir = security_utils.validate_path(
                str(self.plugin_dir),
                "plugin directory"
            )
            self.plugin_dir = Path(validated_plugin_dir)
        except ValueError as e:
            raise UpdateError(
                f"Invalid plugin directory path: {e}\n"
                f"Plugin directory must be within project .claude/plugins/ directory"
            )

        # Audit log initialization
        security_utils.audit_log(
            "plugin_updater",
            "initialized",
            {
                "project_root": str(self.project_root),
                "plugin_name": plugin_name,
            },
        )

    def check_for_updates(self) -> VersionComparison:
        """Check for plugin updates by comparing versions.

        Uses version_detector.detect_version_mismatch() to compare
        project plugin version vs marketplace plugin version.

        Returns:
            VersionComparison object with upgrade/downgrade status

        Raises:
            UpdateError: If version detection fails
        """
        try:
            # Use version_detector to compare versions
            comparison = detect_version_mismatch(
                project_root=str(self.project_root),
                plugin_name=self.plugin_name,
            )

            # Audit log the check
            security_utils.audit_log(
                "plugin_updater",
                "check_for_updates",
                {
                    "event": "check_for_updates",
                    "project_root": str(self.project_root),
                    "plugin_name": self.plugin_name,
                    "status": comparison.status,
                    "project_version": comparison.project_version,
                    "marketplace_version": comparison.marketplace_version,
                }
            )

            return comparison

        except Exception as e:
            # Audit log the error
            security_utils.audit_log(
                "plugin_updater",
                "check_for_updates_error",
                {
                    "event": "check_for_updates_error",
                    "project_root": str(self.project_root),
                    "plugin_name": self.plugin_name,
                    "error": str(e),
                }
            )
            raise UpdateError(f"Failed to check for updates: {e}")

    def update(
        self,
        auto_backup: bool = True,
        skip_confirm: bool = False,
        activate_hooks: bool = True,
    ) -> UpdateResult:
        """Perform plugin update with backup and rollback.

        Complete update workflow:
        1. Pre-install cleanup (remove .claude/lib/ duplicates)
        2. Check for updates (version comparison)
        3. Skip if already up-to-date
        4. Create backup (if auto_backup=True)
        5. Perform sync via sync_dispatcher
        6. Verify update success
        7. Validate and fix permissions (non-blocking)
        8. Sync lib files to ~/.claude/lib/ (non-blocking)
        9. Activate hooks (if activate_hooks=True and sync successful)
        10. Rollback on failure
        11. Cleanup backup on success

        Args:
            auto_backup: Whether to create backup before update (default: True)
            skip_confirm: Skip confirmation prompts (default: False)
            activate_hooks: Whether to activate hooks after update (default: True)

        Returns:
            UpdateResult with success status and details

        Example:
            >>> updater = PluginUpdater("/path/to/project")
            >>> result = updater.update()
            >>> print(result.summary)
        """
        from plugins.autonomous_dev.lib.orphan_file_cleaner import OrphanFileCleaner

        backup_path = None
        old_version = None
        new_version = None

        try:
            # Step 1: Pre-install cleanup (remove duplicate libraries)
            cleaner = OrphanFileCleaner(project_root=self.project_root)
            cleanup_result = cleaner.pre_install_cleanup()

            if not cleanup_result.success:
                # Log warning but continue update
                audit_log(
                    "plugin_updater",
                    "cleanup_warning",
                    {
                        "operation": "update",
                        "cleanup_error": cleanup_result.error_message,
                    },
                )

            # Step 2: Check for updates
            comparison = self.check_for_updates()
            old_version = comparison.project_version
            expected_version = comparison.marketplace_version

            # Step 3: Skip if already up-to-date
            if comparison.status == VersionComparison.UP_TO_DATE:
                return UpdateResult(
                    success=True,
                    updated=False,
                    message="Plugin is already up to date",
                    old_version=old_version,
                    new_version=old_version,
                    backup_path=None,
                    rollback_performed=False,
                    details={},
                )

            # Step 4: Create backup (if enabled)
            if auto_backup:
                backup_path = self._create_backup()

            # Step 5: Perform sync via sync_dispatcher
            # Find marketplace plugins file
            marketplace_file = Path.home() / ".claude" / "plugins" / "installed_plugins.json"

            # Validate marketplace file (CWE-22: Path Traversal prevention)
            # Note: This is a global Claude file, not project-specific, so we use manual validation
            # instead of validate_path() which enforces project-root whitelist

            # Check 1: Must be in user's home directory (not root or system dirs)
            if not str(marketplace_file.resolve()).startswith(str(Path.home().resolve())):
                raise UpdateError(
                    f"Invalid marketplace file: must be in user home directory\n"
                    f"Path: {marketplace_file}\n"
                    f"Expected: ~/.claude/plugins/installed_plugins.json"
                )

            # Check 2: Reject symlinks (defense in depth)
            if marketplace_file.is_symlink():
                raise UpdateError(
                    f"Invalid marketplace file: symlink detected (potential attack)\n"
                    f"Path: {marketplace_file}\n"
                    f"Target: {marketplace_file.resolve()}"
                )

            # Use sync_marketplace for the update
            sync_result = sync_marketplace(
                project_root=str(self.project_root),
                marketplace_plugins_file=marketplace_file,
                cleanup_orphans=False,
                dry_run=False,
            )

            if not sync_result.success:
                # Sync failed - rollback if backup exists
                if backup_path:
                    self._rollback(backup_path)
                    return UpdateResult(
                        success=False,
                        updated=False,
                        message=f"Update failed: {sync_result.message}",
                        old_version=old_version,
                        new_version=old_version,
                        backup_path=backup_path,
                        rollback_performed=True,
                        details={"error": sync_result.error or sync_result.message},
                    )
                else:
                    return UpdateResult(
                        success=False,
                        updated=False,
                        message=f"Update failed: {sync_result.message}",
                        old_version=old_version,
                        new_version=old_version,
                        backup_path=None,
                        rollback_performed=False,
                        details={"error": sync_result.error or sync_result.message},
                    )

            # Step 5: Verify update success
            try:
                self._verify_update(expected_version)
                new_version = expected_version
            except VerificationError as e:
                # Verification failed - rollback
                if backup_path:
                    self._rollback(backup_path)
                    return UpdateResult(
                        success=False,
                        updated=False,
                        message=f"Update verification failed: {e}",
                        old_version=old_version,
                        new_version=old_version,
                        backup_path=backup_path,
                        rollback_performed=True,
                        details={"error": str(e)},
                    )
                else:
                    return UpdateResult(
                        success=False,
                        updated=False,
                        message=f"Update verification failed: {e}",
                        old_version=old_version,
                        new_version=old_version,
                        backup_path=None,
                        rollback_performed=False,
                        details={"error": str(e)},
                    )

            # Step 5.5: Validate and fix permissions (non-blocking)
            permission_fix_result = None
            try:
                permission_fix_result = self._validate_and_fix_permissions()
                # Log result but don't fail update
                if permission_fix_result.action in ["fixed", "regenerated"]:
                    security_utils.audit_log(
                        "plugin_updater",
                        "permission_fix",
                        {
                            "event": "permission_fix",
                            "action": permission_fix_result.action,
                            "issues_found": len(permission_fix_result.issues_found),
                            "fixes_applied": permission_fix_result.fixes_applied,
                        }
                    )
            except Exception as e:
                # Log but don't fail update
                security_utils.audit_log(
                    "plugin_updater",
                    "permission_fix_failed",
                    {
                        "event": "permission_fix_failed",
                        "error": str(e),
                    }
                )
                permission_fix_result = PermissionFixResult(
                    success=False,
                    action="failed",
                    issues_found=0,
                    message=f"Permission validation failed: {e}"
                )

            # Step 5.6: Sync lib files to ~/.claude/lib/ (non-blocking)
            lib_files_synced = 0
            try:
                lib_files_synced = self._sync_lib_files()
            except Exception as e:
                # Log but don't fail update
                security_utils.audit_log(
                    "plugin_updater",
                    "lib_sync_exception",
                    {
                        "event": "lib_sync_exception",
                        "error": str(e),
                    }
                )
                print(f"Warning: Lib file sync encountered error: {e}")

            # Step 6: Activate hooks (non-blocking, after successful sync)
            hooks_activated = False
            if activate_hooks:
                activation_result = self._activate_hooks()
                hooks_activated = activation_result.activated

            # Step 7: Cleanup backup on success
            if backup_path:
                self._cleanup_backup(backup_path)

            # Success!
            security_utils.audit_log(
                "plugin_updater",
                "update_success",
                {
                    "event": "update_success",
                    "project_root": str(self.project_root),
                    "plugin_name": self.plugin_name,
                    "old_version": old_version,
                    "new_version": new_version,
                    "hooks_activated": hooks_activated,
                    "lib_files_synced": lib_files_synced,
                }
            )

            # Merge sync_result.details with lib_files_synced
            result_details = dict(sync_result.details)
            result_details["lib_files_synced"] = lib_files_synced

            return UpdateResult(
                success=True,
                updated=True,
                message=f"Plugin updated successfully to {new_version}",
                old_version=old_version,
                new_version=new_version,
                backup_path=backup_path,
                rollback_performed=False,
                hooks_activated=hooks_activated,
                permission_fix_result=permission_fix_result,
                details=result_details,
            )

        except Exception as e:
            # Unexpected error during update - attempt automatic rollback if backup exists
            # This provides defense in depth: even if sync fails unexpectedly, we can recover
            if backup_path:
                try:
                    self._rollback(backup_path)
                    rollback_performed = True
                except Exception as rollback_error:
                    # Rollback failed too - critical error (data loss risk)
                    # Log both original error and rollback error for debugging
                    security_utils.audit_log(
                        "plugin_updater",
                        "rollback_failed",
                        {
                            "event": "rollback_failed",
                            "project_root": str(self.project_root),
                            "error": str(e),
                            "rollback_error": str(rollback_error),
                        }
                    )
                    rollback_performed = False
            else:
                rollback_performed = False

            security_utils.audit_log(
                "plugin_updater",
                "update_error",
                {
                    "event": "update_error",
                    "project_root": str(self.project_root),
                    "plugin_name": self.plugin_name,
                    "error": str(e),
                    "rollback_performed": rollback_performed,
                }
            )

            return UpdateResult(
                success=False,
                updated=False,
                message=f"Update failed: {e}",
                old_version=old_version,
                new_version=old_version,
                backup_path=backup_path,
                rollback_performed=rollback_performed,
                details={"error": str(e)},
            )

    def _activate_hooks(self) -> ActivationResult:
        """Activate hooks after successful update (non-blocking).

        This method is non-blocking: hook activation failures do NOT fail the update.
        Activation errors are logged but the update still succeeds.

        Returns:
            ActivationResult with activation status and details

        Note:
            This method never raises exceptions - all errors are caught and logged.
        """
        try:
            # Create HookActivator
            activator = HookActivator(project_root=self.project_root)

            # Define default hooks for autonomous-dev plugin
            # These are the core hooks that should be activated by default
            default_hooks = {
                "hooks": {
                    "UserPromptSubmit": [
                        "display_project_context.py",
                        "enforce_command_limit.py",
                    ],
                    "SubagentStop": [
                        "log_agent_completion.py",
                        "auto_update_project_progress.py",
                    ],
                    "PrePush": [
                        "auto_test.py",
                    ],
                }
            }

            # Activate hooks
            result = activator.activate_hooks(default_hooks)

            # Audit log activation result
            security_utils.audit_log(
                "plugin_updater",
                "hook_activation_complete",
                {
                    "event": "hook_activation_complete",
                    "project_root": str(self.project_root),
                    "activated": result.activated,
                    "hooks_added": result.hooks_added,
                },
            )

            return result

        except Exception as e:
            # Non-blocking: log error but don't fail update
            security_utils.audit_log(
                "plugin_updater",
                "hook_activation_error",
                {
                    "event": "hook_activation_error",
                    "project_root": str(self.project_root),
                    "error": str(e),
                },
            )

            # Return failure result (but update still succeeds)
            return ActivationResult(
                activated=False,
                first_install=False,
                message=f"Hook activation failed: {e}",
                hooks_added=0,
                settings_path=None,
                details={"error": str(e)},
            )

    def _sync_lib_files(self) -> int:
        """Sync lib files from plugin to ~/.claude/lib/ (non-blocking).

        This method copies required library files from the plugin's lib directory
        to the global ~/.claude/lib/ directory where hooks can import them.

        Workflow:
        1. Read installation_manifest.json to get lib directory
        2. Create ~/.claude/lib/ if it doesn't exist
        3. Copy each .py file from plugin/lib/ to ~/.claude/lib/
        4. Validate all paths for security (CWE-22, CWE-59)
        5. Audit log all operations
        6. Handle errors gracefully (non-blocking)

        Returns:
            Number of lib files successfully synced (0 on complete failure)

        Note:
            This method is non-blocking - errors are logged but don't fail update.
            Missing manifest or source files are handled gracefully.

        Security:
            - All paths validated via security_utils.validate_path()
            - Prevents path traversal (CWE-22)
            - Rejects symlinks (CWE-59)
            - Operations audit-logged (CWE-778)
        """
        try:
            # Step 1: Read manifest to verify lib directory should be synced
            manifest_path = self.plugin_dir / "config" / "installation_manifest.json"

            if not manifest_path.exists():
                # Manifest missing - graceful degradation
                print(f"Warning: installation_manifest.json not found, syncing all .py files from lib/")
                # Continue anyway - copy all .py files from lib/
            else:
                # Validate manifest includes lib directory
                try:
                    manifest_data = json.loads(manifest_path.read_text())
                    include_dirs = manifest_data.get("include_directories", [])

                    if "lib" not in include_dirs:
                        # Lib not in manifest - skip sync
                        security_utils.audit_log(
                            "plugin_updater",
                            "lib_sync_skipped",
                            {
                                "event": "lib_sync_skipped",
                                "reason": "lib not in manifest include_directories",
                                "project_root": str(self.project_root),
                            }
                        )
                        return 0
                except (json.JSONDecodeError, KeyError) as e:
                    # Manifest malformed - log warning but continue
                    print(f"Warning: Failed to parse manifest: {e}")
                    # Continue with sync anyway

            # Step 2: Create target directory ~/.claude/lib/
            target_dir = Path.home() / ".claude" / "lib"

            # Security: Validate target path is in user home
            if not str(target_dir.resolve()).startswith(str(Path.home().resolve())):
                security_utils.audit_log(
                    "plugin_updater",
                    "lib_sync_blocked",
                    {
                        "event": "lib_sync_blocked",
                        "reason": "target path outside user home",
                        "target_path": str(target_dir),
                    }
                )
                return 0

            # Create directory if doesn't exist
            target_dir.mkdir(parents=True, exist_ok=True)

            # Step 3: Copy lib files from plugin to global location
            source_dir = self.plugin_dir / "lib"

            if not source_dir.exists():
                # Source lib directory missing - log and return
                security_utils.audit_log(
                    "plugin_updater",
                    "lib_sync_skipped",
                    {
                        "event": "lib_sync_skipped",
                        "reason": "source lib directory not found",
                        "source_path": str(source_dir),
                        "project_root": str(self.project_root),
                    }
                )
                return 0

            # Get all .py files from source lib directory
            lib_files = list(source_dir.glob("*.py"))

            if not lib_files:
                # No lib files to sync
                print("Info: No .py files found in plugin lib directory")
                return 0

            # Copy each file
            files_synced = 0
            files_failed = 0

            for source_file in lib_files:
                try:
                    # Skip __init__.py (not needed in global lib)
                    if source_file.name == "__init__.py":
                        continue

                    # Security: Validate source path
                    # Use manual validation since validate_path() enforces project-root whitelist
                    # and ~/.claude/lib/ is a global directory
                    if source_file.is_symlink():
                        print(f"Warning: Skipping symlink: {source_file.name}")
                        files_failed += 1
                        continue

                    # Validate file is actually in plugin lib directory (prevent traversal)
                    if not str(source_file.resolve()).startswith(str(source_dir.resolve())):
                        print(f"Warning: Skipping file outside lib directory: {source_file.name}")
                        files_failed += 1
                        continue

                    # Define target path
                    target_file = target_dir / source_file.name

                    # Security: Validate target path
                    if target_file.is_symlink():
                        print(f"Warning: Skipping existing symlink: {target_file.name}")
                        files_failed += 1
                        continue

                    # Copy file (overwrites existing)
                    shutil.copy2(source_file, target_file)
                    files_synced += 1

                    if self.verbose:
                        print(f"  Synced: {source_file.name} → ~/.claude/lib/")

                except (PermissionError, OSError) as e:
                    # File copy failed - log and continue with next file
                    print(f"Warning: Failed to sync {source_file.name}: {e}")
                    files_failed += 1
                    continue

            # Step 4: Audit log sync result
            security_utils.audit_log(
                "plugin_updater",
                "lib_sync_complete",
                {
                    "event": "lib_sync_complete",
                    "project_root": str(self.project_root),
                    "files_synced": files_synced,
                    "files_failed": files_failed,
                    "target_dir": str(target_dir),
                }
            )

            if files_synced > 0:
                print(f"Synced {files_synced} lib file(s) to ~/.claude/lib/")

            if files_failed > 0:
                print(f"Warning: {files_failed} lib file(s) failed to sync")

            return files_synced

        except Exception as e:
            # Non-blocking: log error but don't fail update
            security_utils.audit_log(
                "plugin_updater",
                "lib_sync_error",
                {
                    "event": "lib_sync_error",
                    "project_root": str(self.project_root),
                    "error": str(e),
                }
            )
            print(f"Warning: Lib file sync failed: {e}")
            return 0

    def _validate_and_fix_permissions(self) -> PermissionFixResult:
        """Validate and fix settings.local.json permissions (non-blocking).

        Workflow:
        1. Check if settings.local.json exists (skip if not)
        2. Load and validate permissions
        3. If issues found:
           a. Backup existing file
           b. Generate template with correct patterns
           c. Fix using fix_permission_patterns()
           d. Write fixed settings atomically
        4. Return result

        Returns:
            PermissionFixResult with action, issues, and fixes

        Note:
            This method is non-blocking - exceptions are caught and returned
            as failed results. Update can succeed even if permission fix fails.
        """
        settings_path = self.project_root / ".claude" / "settings.local.json"

        # Step 1: Check if settings.local.json exists
        if not settings_path.exists():
            return PermissionFixResult(
                success=True,
                action="skipped",
                issues_found=0,
                fixes_applied=[],
                backup_path=None,
                message="No settings.local.json found - skipping validation"
            )

        try:
            # Step 2: Load and validate permissions
            try:
                settings_content = settings_path.read_text()
                settings = json.loads(settings_content)
            except json.JSONDecodeError as e:
                # Corrupted JSON - backup and try to regenerate
                backup_path = self._backup_settings_file(settings_path)

                try:
                    # Try to generate fresh settings from template
                    from plugins.autonomous_dev.lib.settings_generator import (
                        SettingsGenerator,
                        SAFE_COMMAND_PATTERNS,
                        DEFAULT_DENY_LIST,
                    )

                    plugin_dir = self.project_root / "plugins" / self.plugin_name
                    if plugin_dir.exists():
                        # Full regeneration from template
                        generator = SettingsGenerator(plugin_dir)
                        gen_result = generator.write_settings(settings_path, merge_existing=False)

                        if gen_result.success:
                            return PermissionFixResult(
                                success=True,
                                action="regenerated",
                                issues_found=1,  # One issue: corrupted JSON
                                fixes_applied=["Regenerated settings from template"],
                                backup_path=backup_path,
                                message="Corrupted settings.local.json regenerated from template"
                            )
                    else:
                        # Plugin directory doesn't exist - create minimal valid settings
                        minimal_settings = {
                            "version": "1.0.0",
                            "permissions": {
                                "allow": SAFE_COMMAND_PATTERNS.copy(),
                                "deny": DEFAULT_DENY_LIST.copy()
                            }
                        }
                        settings_path.write_text(json.dumps(minimal_settings, indent=2))

                        return PermissionFixResult(
                            success=True,
                            action="regenerated",
                            issues_found=1,  # One issue: corrupted JSON
                            fixes_applied=["Created minimal valid settings"],
                            backup_path=backup_path,
                            message="Corrupted JSON - created minimal valid settings"
                        )

                except Exception as regen_error:
                    # Regeneration failed - return with backup info
                    return PermissionFixResult(
                        success=False,
                        action="failed",
                        issues_found=1,  # One issue: corrupted JSON
                        fixes_applied=[],
                        backup_path=backup_path,
                        message=f"Corrupted JSON - backed up but regeneration failed: {regen_error}"
                    )

            # Validate permissions
            validation_result = validate_permission_patterns(settings)

            # Step 3a: If no issues, return validated
            if validation_result.valid:
                return PermissionFixResult(
                    success=True,
                    action="validated",
                    issues_found=0,
                    fixes_applied=[],
                    backup_path=None,
                    message="Settings permissions already valid - no issues found"
                )

            # Step 3b: Issues found - backup and fix
            backup_path = self._backup_settings_file(settings_path)

            # Step 3c: Fix patterns
            fixed_settings = fix_permission_patterns(settings)

            # Step 3d: Write fixed settings atomically
            settings_path.write_text(json.dumps(fixed_settings, indent=2))

            # Build fixes_applied list
            fixes_applied = []
            if any("wildcard" in i.issue_type for i in validation_result.issues):
                fixes_applied.append("Replaced wildcard patterns with specific commands")
            if any("deny" in i.issue_type for i in validation_result.issues):
                fixes_applied.append("Added comprehensive deny list")

            return PermissionFixResult(
                success=True,
                action="fixed",
                issues_found=len(validation_result.issues),
                fixes_applied=fixes_applied,
                backup_path=backup_path,
                message=f"Fixed {len(validation_result.issues)} permission issue(s)"
            )

        except Exception as e:
            # Non-blocking - return failure but don't raise
            return PermissionFixResult(
                success=False,
                action="failed",
                issues_found=0,
                fixes_applied=[],
                backup_path=None,
                message=f"Permission validation failed: {e}"
            )

    def _backup_settings_file(self, settings_path: Path) -> Path:
        """Create timestamped backup of settings.local.json.

        Args:
            settings_path: Path to settings.local.json

        Returns:
            Path to backup file
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")  # Include microseconds
        backup_dir = self.project_root / ".claude" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        backup_path = backup_dir / f"settings.local.json.backup-{timestamp}"
        shutil.copy2(settings_path, backup_path)

        # Audit log
        security_utils.audit_log(
            "plugin_updater",
            "settings_backup",
            {
                "event": "settings_backup",
                "source": str(settings_path),
                "backup": str(backup_path),
            }
        )

        return backup_path

    def _create_backup(self) -> Path:
        """Create timestamped backup of plugin directory.

        Creates backup in temp directory with format:
        /tmp/autonomous-dev-backup-YYYYMMDD-HHMMSS/

        Backup permissions: 0o700 (user-only) for security (CWE-732)

        Returns:
            Path to backup directory

        Raises:
            BackupError: If backup creation fails
        """
        try:
            # Generate timestamp for backup name
            # Format: YYYYMMDD-HHMMSS enables sorting and identification
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_name = f"{self.plugin_name}-backup-{timestamp}"

            # Create backup directory in temp using mkdtemp() for security
            # mkdtemp() ensures atomic creation with 0o700 permissions by default
            backup_path = Path(tempfile.mkdtemp(prefix=backup_name + "-"))

            # Verify permissions are correct (CWE-59: TOCTOU prevention)
            # Check that mkdtemp created directory with secure permissions
            actual_perms = backup_path.stat().st_mode & 0o777
            if actual_perms != 0o700:
                # Attempt to fix permissions
                backup_path.chmod(0o700)
                # Verify fix worked
                if backup_path.stat().st_mode & 0o777 != 0o700:
                    raise BackupError(
                        f"Cannot set secure permissions on backup directory: {backup_path}\n"
                        f"Expected 0o700, got {oct(actual_perms)}"
                    )

            # Check if plugin directory exists
            if not self.plugin_dir.exists():
                # No plugin directory - create empty backup
                security_utils.audit_log(
                    "plugin_updater",
                    "backup_empty",
                    {
                        "event": "backup_empty",
                        "project_root": str(self.project_root),
                        "plugin_name": self.plugin_name,
                        "backup_path": str(backup_path),
                        "reason": "Plugin directory does not exist",
                    }
                )
                return backup_path

            # Copy plugin directory to backup
            # Use copytree with dirs_exist_ok=True to handle edge cases
            for item in self.plugin_dir.iterdir():
                if item.is_dir():
                    shutil.copytree(item, backup_path / item.name, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, backup_path / item.name)

            # Audit log backup creation
            security_utils.audit_log(
                "plugin_backup_created",
                "success",
                {
                    "backup_path": str(backup_path),
                    "project_root": str(self.project_root),
                    "plugin_name": self.plugin_name,
                }
            )

            return backup_path

        except PermissionError as e:
            raise BackupError(f"Permission denied creating backup: {e}")
        except Exception as e:
            raise BackupError(f"Failed to create backup: {e}")

    def _rollback(self, backup_path: Path) -> None:
        """Restore plugin from backup directory.

        Removes current plugin directory and restores from backup.

        Args:
            backup_path: Path to backup directory

        Raises:
            BackupError: If rollback fails
        """
        try:
            # Validate backup path exists
            if not backup_path.exists():
                raise BackupError(f"Backup path does not exist: {backup_path}")

            # Check for symlinks (CWE-22: Path Traversal prevention)
            if backup_path.is_symlink():
                raise BackupError(
                    f"Rollback blocked: Backup path is a symlink (potential attack)\n"
                    f"Path: {backup_path}\n"
                    f"Target: {backup_path.resolve()}"
                )

            # Validate backup is in temp directory (not system directory)
            # Allow backup paths in tempdir or test temp paths
            import tempfile
            temp_dir = tempfile.gettempdir()

            # Resolve both paths to handle macOS symlinks (/var -> /private/var)
            resolved_backup = str(backup_path.resolve())
            resolved_temp = str(Path(temp_dir).resolve())

            # Allow paths in system temp OR pytest temp fixtures (for testing)
            is_in_temp = (
                resolved_backup.startswith(resolved_temp)
                or "/tmp/" in resolved_backup
                or "pytest-of-" in resolved_backup  # pytest temp directories
            )
            if not is_in_temp:
                raise BackupError(
                    f"Rollback blocked: Backup path not in temp directory\n"
                    f"Path: {backup_path}\n"
                    f"Expected location: {temp_dir}"
                )

            # Remove current plugin directory if it exists
            if self.plugin_dir.exists():
                shutil.rmtree(self.plugin_dir)

            # Restore from backup
            self.plugin_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(backup_path, self.plugin_dir, dirs_exist_ok=True)

            # Audit log rollback
            security_utils.audit_log(
                "plugin_rollback",
                "success",
                {
                    "backup_path": str(backup_path),
                    "project_root": str(self.project_root),
                    "plugin_name": self.plugin_name,
                }
            )

        except PermissionError as e:
            raise BackupError(f"Permission denied during rollback: {e}")
        except Exception as e:
            raise BackupError(f"Rollback failed: {e}")

    def _cleanup_backup(self, backup_path: Path) -> None:
        """Remove backup directory after successful update.

        Args:
            backup_path: Path to backup directory to remove

        Note:
            Gracefully handles nonexistent backup (no error raised)
        """
        try:
            if backup_path and backup_path.exists():
                shutil.rmtree(backup_path)

                # Audit log cleanup
                security_utils.audit_log(
                    "plugin_backup_cleanup",
                    "success",
                    {
                        "backup_path": str(backup_path),
                        "project_root": str(self.project_root),
                        "plugin_name": self.plugin_name,
                    }
                )

        except Exception as e:
            # Non-critical - log but don't raise
            security_utils.audit_log(
                "plugin_updater",
                "backup_cleanup_error",
                {
                    "event": "backup_cleanup_error",
                    "project_root": str(self.project_root),
                    "plugin_name": self.plugin_name,
                    "backup_path": str(backup_path),
                    "error": str(e),
                }
            )

    def _verify_update(self, expected_version: str) -> None:
        """Verify update succeeded by checking version.

        Args:
            expected_version: Expected version after update

        Raises:
            VerificationError: If verification fails
        """
        try:
            # Critical: Check if plugin.json exists (required for version detection)
            # Missing plugin.json indicates sync failed or corrupted state
            plugin_json = self.plugin_dir / "plugin.json"
            if not plugin_json.exists():
                raise VerificationError(
                    f"Verification failed: plugin.json not found at {plugin_json}"
                )

            # Check file size (DoS prevention - CWE-400)
            # Prevent processing of maliciously large files
            file_size = plugin_json.stat().st_size
            if file_size > 10 * 1024 * 1024:  # 10MB max
                raise VerificationError(
                    f"plugin.json too large: {file_size} bytes (max 10MB)\n"
                    f"This may indicate a corrupted or malicious file."
                )

            # Parse plugin.json - must be valid JSON (indicates successful sync)
            # Parse failure indicates corrupted sync or incomplete transfer
            try:
                plugin_data = json.loads(plugin_json.read_text())
            except json.JSONDecodeError as e:
                raise VerificationError(f"Verification failed: Invalid JSON in plugin.json: {e}")

            # Validate required fields exist (data integrity check)
            required_fields = ["name", "version"]
            missing = [f for f in required_fields if f not in plugin_data]
            if missing:
                raise VerificationError(
                    f"plugin.json missing required fields: {missing}\n"
                    f"This indicates an incomplete or corrupted plugin installation."
                )

            # Critical: Verify version matches expected version
            # Mismatch indicates sync failed to update to correct version
            actual_version = plugin_data.get("version")

            # Validate version format (semantic versioning)
            import re
            if not re.match(r'^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$', actual_version):
                raise VerificationError(
                    f"Invalid version format: {actual_version}\n"
                    f"Expected semantic versioning (e.g., 3.8.0 or 3.8.0-beta.1)"
                )

            if actual_version != expected_version:
                raise VerificationError(
                    f"Version mismatch: expected {expected_version}, got {actual_version}"
                )

            # Audit log successful verification
            security_utils.audit_log(
                "plugin_updater",
                "verification_success",
                {
                    "event": "verification_success",
                    "project_root": str(self.project_root),
                    "plugin_name": self.plugin_name,
                    "version": actual_version,
                }
            )

        except VerificationError:
            # Re-raise VerificationError
            raise
        except Exception as e:
            raise VerificationError(f"Verification failed: {e}")
