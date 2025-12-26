#!/usr/bin/env python3
"""
Uninstall Orchestrator - Complete uninstallation of autonomous-dev plugin

This module handles complete uninstallation of the autonomous-dev plugin with
backup and rollback capabilities. Implements three-phase execution:
Validate → Preview → Execute.

Security:
- Path traversal prevention (CWE-22)
- Symlink attack prevention (CWE-59)
- TOCTOU detection (CWE-367)
- Whitelist enforcement for allowed directories
- Audit logging for all operations

Features:
- Three-phase execution (validate, preview, execute)
- Automatic backup creation before deletion
- Rollback support to restore from backup
- Protected file preservation (PROJECT.md, .env, settings.local.json)
- Dry-run mode for safe preview
- Local-only mode to preserve global files

Usage:
    from uninstall_orchestrator import uninstall_plugin

    # Simple uninstall with preview
    result = uninstall_plugin(project_root, dry_run=True)
    print(f"Would remove {result.files_to_remove} files")

    # Execute actual uninstall
    result = uninstall_plugin(project_root, force=True)
    if result.status == "success":
        print(f"Removed {result.files_removed} files")
        print(f"Backup: {result.backup_path}")

    # Rollback if needed
    orchestrator = UninstallOrchestrator(project_root)
    rollback_result = orchestrator.rollback(result.backup_path)

Date: 2025-12-14
Issue: GitHub #131 - Add uninstall capability to install.sh and /sync command
Agent: implementer

Design Patterns:
    See library-design-patterns skill for standardized design patterns.
"""

import json
import os
import tarfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# Import with fallback for both dev (plugins/) and installed (.claude/lib/) environments
try:
    from plugins.autonomous_dev.lib.security_utils import validate_path, audit_log
    from plugins.autonomous_dev.lib.protected_file_detector import ProtectedFileDetector
except ImportError:
    # Fallback for installed environment (.claude/lib/)
    from security_utils import audit_log
    from protected_file_detector import ProtectedFileDetector


# Whitelist of allowed directories for uninstallation
ALLOWED_DIRECTORIES = [
    ".claude",
    ".autonomous-dev",
]

# Global directories (under home)
GLOBAL_DIRECTORIES = [
    ".claude",
    ".autonomous-dev",
]


@dataclass
class UninstallResult:
    """Result of uninstall operation.

    Attributes:
        status: Operation status ("success", "failure", "preview")
        files_removed: Number of files actually removed
        total_size_bytes: Total size of files removed/to be removed
        backup_path: Path to backup tar.gz file
        errors: List of error messages
        dry_run: Whether this was a dry-run preview
        files_to_remove: Number of files to be removed (preview mode)
        file_list: List of file paths to be removed (preview mode)
        manifest_found: Whether install manifest was found
        files_restored: Number of files restored (rollback mode)
    """

    status: str
    files_removed: int = 0
    total_size_bytes: int = 0
    backup_path: Optional[Path] = None
    errors: List[str] = field(default_factory=list)
    dry_run: bool = False
    files_to_remove: int = 0
    file_list: List[Path] = field(default_factory=list)
    manifest_found: bool = False
    files_restored: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for JSON serialization.

        Returns:
            Dictionary representation of result
        """
        return {
            "status": self.status,
            "files_removed": self.files_removed,
            "total_size_bytes": self.total_size_bytes,
            "backup_path": str(self.backup_path) if self.backup_path else None,
            "errors": self.errors,
            "dry_run": self.dry_run,
            "files_to_remove": self.files_to_remove,
            "file_list": [str(f) for f in self.file_list],
            "manifest_found": self.manifest_found,
            "files_restored": self.files_restored,
        }


class UninstallError(Exception):
    """Exception raised for uninstall errors."""

    pass


class UninstallOrchestrator:
    """Orchestrate complete uninstallation of autonomous-dev plugin.

    This class handles three-phase uninstallation:
    1. Validate: Check manifest exists and paths are valid
    2. Preview: Show what will be deleted without deleting
    3. Execute: Create backup and delete files

    Examples:
        >>> orchestrator = UninstallOrchestrator(project_root)
        >>> # Phase 1: Validate
        >>> result = orchestrator.validate()
        >>> if result.status == "success":
        ...     # Phase 2: Preview
        ...     preview = orchestrator.preview()
        ...     print(f"Would remove {preview.files_to_remove} files")
        ...     # Phase 3: Execute
        ...     result = orchestrator.execute(force=True)
        ...     print(f"Backup: {result.backup_path}")
    """

    def __init__(self, project_root: Path | str):
        """Initialize uninstall orchestrator.

        Args:
            project_root: Root directory of project to uninstall from

        Raises:
            ValueError: If path validation fails
        """
        # Convert to Path if string
        self.project_root = Path(project_root) if isinstance(project_root, str) else project_root

        # Validate path (CWE-22: path traversal prevention)
        self.project_root = self.project_root.resolve()

        # Check for path traversal
        try:
            # Get the original path without resolving
            original_path = Path(project_root) if isinstance(project_root, str) else project_root
            original_str = str(original_path)

            # Detect path traversal patterns
            if ".." in original_str or "/./" in original_str:
                raise ValueError(f"Path traversal detected: {original_str}")

        except Exception as e:
            audit_log("uninstall_orchestrator", "path_validation_error", {
                "path": str(project_root),
                "error": str(e)
            })
            raise ValueError(f"Path traversal detected: {project_root}")

        self.claude_dir = self.project_root / ".claude"
        self.manifest_path = self.claude_dir / "config" / "install_manifest.json"
        self.protected_detector = ProtectedFileDetector()

        # State tracking for TOCTOU detection
        self._preview_state: Dict[str, Any] = {}

        audit_log("uninstall_orchestrator", "initialized", {
            "project_root": str(self.project_root),
            "claude_dir": str(self.claude_dir),
        })

    def validate(self) -> UninstallResult:
        """Phase 1: Validate manifest exists and paths are valid.

        Returns:
            UninstallResult with validation status
        """
        audit_log("uninstall_orchestrator", "validate_start", {
            "manifest_path": str(self.manifest_path)
        })

        errors = []

        # Check if manifest exists
        if not self.manifest_path.exists():
            errors.append(f"Install manifest not found: {self.manifest_path}")
            audit_log("uninstall_orchestrator", "validate_failure", {
                "error": "manifest_not_found"
            })
            return UninstallResult(
                status="failure",
                errors=errors,
                manifest_found=False
            )

        # Check for multi-project installations
        self._check_multi_project_installations()

        audit_log("uninstall_orchestrator", "validate_success", {})

        return UninstallResult(
            status="success",
            manifest_found=True
        )

    def preview(self) -> UninstallResult:
        """Phase 2: Preview files to be deleted without deleting.

        Returns:
            UninstallResult with preview information (files_to_remove, total_size_bytes, file_list)

        Raises:
            ValueError: If security validation fails
        """
        audit_log("uninstall_orchestrator", "preview_start", {})

        # Validate manifest exists
        if not self.manifest_path.exists():
            return UninstallResult(
                status="failure",
                errors=[f"Install manifest not found: {self.manifest_path}"],
                manifest_found=False
            )

        # Load manifest
        with open(self.manifest_path, "r") as f:
            manifest = json.load(f)

        # Get files to remove (this may raise ValueError for security violations)
        files_to_remove, total_size, file_list = self._collect_files_to_remove(manifest)

        # Store state for TOCTOU detection
        self._preview_state = {
            "files": {str(f): os.stat(f).st_mtime if f.exists() else None for f in file_list},
            "timestamp": datetime.now().isoformat()
        }

        audit_log("uninstall_orchestrator", "preview_success", {
            "files_to_remove": files_to_remove,
            "total_size_bytes": total_size
        })

        return UninstallResult(
            status="success",
            files_to_remove=files_to_remove,
            total_size_bytes=total_size,
            file_list=file_list,
            manifest_found=True
        )

    def execute(
        self,
        force: bool = False,
        dry_run: bool = False,
        local_only: bool = False
    ) -> UninstallResult:
        """Phase 3: Execute uninstallation with backup.

        Args:
            force: If True, execute deletion; if False, return error
            dry_run: If True, only preview (same as preview() method)
            local_only: If True, skip global ~/.claude/ and ~/.autonomous-dev/

        Returns:
            UninstallResult with execution status

        Raises:
            ValueError: If security validation fails
        """
        audit_log("uninstall_orchestrator", "execute_start", {
            "force": force,
            "dry_run": dry_run,
            "local_only": local_only
        })

        # Dry-run mode - just return preview
        if dry_run:
            result = self.preview()
            result.dry_run = True
            return result

        # Force required for actual deletion
        if not force:
            audit_log("uninstall_orchestrator", "execute_force_required", {})
            return UninstallResult(
                status="failure",
                errors=["Uninstall requires --force flag for confirmation"]
            )

        # Validate manifest exists
        if not self.manifest_path.exists():
            return UninstallResult(
                status="failure",
                errors=[f"Install manifest not found: {self.manifest_path}"],
                manifest_found=False
            )

        try:
            # Load manifest
            with open(self.manifest_path, "r") as f:
                manifest = json.load(f)

            # Get files to remove
            files_to_remove, total_size, file_list = self._collect_files_to_remove(
                manifest,
                local_only=local_only
            )

            # TOCTOU detection - check if files changed since preview
            self._detect_toctou_changes(file_list)

            # Create backup
            backup_path = self._create_backup(file_list)

            # Remove files
            files_removed, errors = self._remove_files(file_list)

            status = "success" if not errors or files_removed > 0 else "failure"

            audit_log("uninstall_orchestrator", "execute_success", {
                "files_removed": files_removed,
                "backup_path": str(backup_path),
                "errors": len(errors)
            })

            return UninstallResult(
                status=status,
                files_removed=files_removed,
                total_size_bytes=total_size,
                backup_path=backup_path,
                errors=errors,
                manifest_found=True
            )

        except Exception as e:
            audit_log("uninstall_orchestrator", "execute_error", {
                "error": str(e)
            })
            return UninstallResult(
                status="failure",
                errors=[f"Execution failed: {str(e)}"]
            )

    def rollback(self, backup_path: Path | str) -> UninstallResult:
        """Rollback uninstallation by restoring from backup.

        Args:
            backup_path: Path to backup tar.gz file

        Returns:
            UninstallResult with rollback status
        """
        audit_log("uninstall_orchestrator", "rollback_start", {
            "backup_path": str(backup_path)
        })

        backup = Path(backup_path) if isinstance(backup_path, str) else backup_path

        # Validate backup exists
        if not backup.exists():
            return UninstallResult(
                status="failure",
                errors=[f"Backup file not found: {backup}"]
            )

        try:
            # Extract backup with Zip Slip prevention (CVE-2007-4559)
            with tarfile.open(backup, "r:gz") as tar:
                # Validate all members before extraction (Zip Slip prevention)
                project_root_resolved = self.project_root.resolve()
                for member in tar.getmembers():
                    member_path = (self.project_root / member.name).resolve()
                    if not str(member_path).startswith(str(project_root_resolved)):
                        raise ValueError(f"Path traversal detected in archive: {member.name}")

                # Safe to extract after validation
                tar.extractall(path=self.project_root)

                files_restored = len(tar.getmembers())

            audit_log("uninstall_orchestrator", "rollback_success", {
                "files_restored": files_restored
            })

            return UninstallResult(
                status="success",
                files_restored=files_restored
            )

        except Exception as e:
            audit_log("uninstall_orchestrator", "rollback_error", {
                "error": str(e)
            })
            return UninstallResult(
                status="failure",
                errors=[f"Rollback failed: {str(e)}"]
            )

    def _collect_files_to_remove(
        self,
        manifest: Dict[str, Any],
        local_only: bool = False
    ) -> tuple[int, int, List[Path]]:
        """Collect files to remove from manifest.

        Args:
            manifest: Install manifest dictionary
            local_only: If True, skip global directories

        Returns:
            Tuple of (count, total_size_bytes, file_list)

        Raises:
            ValueError: If security validation fails
        """
        file_list = []
        total_size = 0

        # Get protected files
        protected = self.protected_detector.detect_protected_files(self.project_root)
        protected_paths = {Path(self.project_root) / p["path"] for p in protected}

        # Process each component
        components = manifest.get("components", {})
        for component_name, component_data in components.items():
            target = component_data.get("target", "")
            files = component_data.get("files", [])

            # Security: Check for path traversal in target (CWE-22)
            if ".." in target or "/./" in target:
                raise ValueError(f"Path traversal detected - target not in whitelist: {target}")

            # Build target directory
            target_dir = self.project_root / target

            # Security: Validate target directory is within allowed paths
            self._validate_file_path(target_dir)

            # Skip global directories if local_only
            if local_only and self._is_global_directory(target_dir):
                audit_log("uninstall_orchestrator", "skip_global_directory", {
                    "target": str(target_dir),
                    "local_only": True
                })
                continue

            for file_rel_path in files:
                # Security: Check for path traversal in file path (CWE-22)
                if ".." in file_rel_path or "/./" in file_rel_path:
                    raise ValueError(f"Path traversal detected in file path: {file_rel_path}")

                # Extract relative structure from manifest path
                # e.g., "plugins/autonomous-dev/commands/helpers/utility.md" -> "helpers/utility.md"
                # This preserves nested directory structure
                file_rel = Path(file_rel_path)
                file_parts = file_rel.parts

                # Manifest paths are like "plugins/autonomous-dev/component/..."
                # We need everything after the component type (4th part onwards)
                if len(file_parts) > 3:
                    # Has subdirectory structure (e.g., commands/helpers/utility.md)
                    relative_structure = Path(*file_parts[3:])
                    file_path = target_dir / relative_structure
                else:
                    # Simple file (e.g., commands/auto-implement.md)
                    file_path = target_dir / file_rel.name

                # Skip if file doesn't exist (partial install)
                if not file_path.exists():
                    continue

                # Security: Check for symlinks BEFORE resolving path (CWE-59)
                if file_path.is_symlink():
                    real_path = file_path.resolve()
                    # Symlink detected - reject it
                    raise ValueError(f"Symlink detected: {file_path} -> {real_path}")

                # Security: Validate path (CWE-22)
                # Now safe to validate since we know it's not a symlink
                self._validate_file_path(file_path)

                # Skip protected files
                if file_path in protected_paths:
                    audit_log("uninstall_orchestrator", "skip_protected_file", {
                        "file": str(file_path)
                    })
                    continue

                # Add to list
                file_list.append(file_path)
                total_size += file_path.stat().st_size

        return len(file_list), total_size, file_list

    def _validate_file_path(self, file_path: Path) -> None:
        """Validate file path for security.

        Args:
            file_path: Path to validate

        Raises:
            ValueError: If path validation fails
        """
        # Resolve to absolute path
        resolved = file_path.resolve()

        # Check path is within allowed directories
        allowed = False
        for allowed_dir in ALLOWED_DIRECTORIES:
            # Check if path contains allowed directory (as a path component)
            path_parts = resolved.parts
            if allowed_dir in path_parts:
                allowed = True
                break

        if not allowed:
            raise ValueError(f"Path not in whitelist: {file_path}")

        # Additional check: ensure path is within project_root or global home
        project_root_resolved = self.project_root.resolve()
        home_dir = Path.home()

        within_project = str(resolved).startswith(str(project_root_resolved))
        within_home = str(resolved).startswith(str(home_dir))

        if not (within_project or within_home):
            raise ValueError(f"Path not in whitelist: {file_path}")

    def _is_global_directory(self, path: Path) -> bool:
        """Check if path is a global directory (~/.claude/ or ~/.autonomous-dev/).

        Args:
            path: Path to check

        Returns:
            True if path is under global directory
        """
        resolved = path.resolve()
        home_dir = Path.home()

        for global_dir in GLOBAL_DIRECTORIES:
            global_path = home_dir / global_dir
            if str(resolved).startswith(str(global_path)):
                return True

        return False

    def _detect_toctou_changes(self, file_list: List[Path]) -> None:
        """Detect TOCTOU race conditions (CWE-367).

        Args:
            file_list: List of files to check
        """
        if not self._preview_state:
            # No preview state to compare against
            return

        preview_files = self._preview_state.get("files", {})

        for file_path in file_list:
            file_key = str(file_path)

            if file_key not in preview_files:
                continue

            preview_mtime = preview_files[file_key]
            if preview_mtime is None:
                continue

            if not file_path.exists():
                # File was deleted between preview and execute (TOCTOU race condition)
                audit_log("uninstall_orchestrator", "TOCTOU_detected_file_deleted", {
                    "file": file_key
                })
                continue

            current_mtime = os.stat(file_path).st_mtime

            if current_mtime != preview_mtime:
                # File was modified between preview and execute (TOCTOU race condition)
                audit_log("uninstall_orchestrator", "TOCTOU_detected_file_changed", {
                    "file": file_key,
                    "preview_mtime": preview_mtime,
                    "current_mtime": current_mtime
                })

    def _create_backup(self, file_list: List[Path]) -> Path:
        """Create backup tar.gz of files before deletion.

        Args:
            file_list: List of files to backup

        Returns:
            Path to backup tar.gz file
        """
        # Create backup directory
        backup_dir = self.project_root / ".autonomous-dev"
        backup_dir.mkdir(exist_ok=True)

        # Generate timestamped backup filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"uninstall_backup_{timestamp}.tar.gz"

        audit_log("uninstall_orchestrator", "backup_start", {
            "backup_path": str(backup_path),
            "files": len(file_list)
        })

        # Create tar.gz backup
        with tarfile.open(backup_path, "w:gz") as tar:
            for file_path in file_list:
                if file_path.exists():
                    # Add file with relative path from project root
                    arcname = file_path.relative_to(self.project_root)
                    tar.add(file_path, arcname=arcname)

        audit_log("uninstall_orchestrator", "backup_success", {
            "backup_path": str(backup_path)
        })

        return backup_path

    def _remove_files(self, file_list: List[Path]) -> tuple[int, List[str]]:
        """Remove files from filesystem.

        Args:
            file_list: List of files to remove

        Returns:
            Tuple of (files_removed_count, errors_list)
        """
        files_removed = 0
        errors = []

        for file_path in file_list:
            try:
                if file_path.exists():
                    file_path.unlink()
                    files_removed += 1
                    audit_log("uninstall_orchestrator", "file_removed", {
                        "file": str(file_path)
                    })
            except PermissionError as e:
                error_msg = f"Permission denied: {file_path}"
                errors.append(error_msg)
                audit_log("uninstall_orchestrator", "permission_error", {
                    "file": str(file_path),
                    "error": str(e)
                })
            except Exception as e:
                error_msg = f"Error removing {file_path}: {str(e)}"
                errors.append(error_msg)
                audit_log("uninstall_orchestrator", "removal_error", {
                    "file": str(file_path),
                    "error": str(e)
                })

        return files_removed, errors

    def _check_multi_project_installations(self) -> None:
        """Check for multiple project installations and log warning."""
        try:
            home_dir = Path.home()

            # Find .claude directories (limit search to avoid hanging)
            claude_dirs = []

            # Only check immediate subdirectories to avoid deep recursive search
            for search_dir in [home_dir, home_dir / "Documents", home_dir / "projects"]:
                if not search_dir.exists():
                    continue

                # Only check one level deep to avoid performance issues
                for item in search_dir.iterdir():
                    if not item.is_dir():
                        continue

                    claude_path = item / ".claude"
                    if claude_path.exists() and claude_path.is_dir():
                        claude_dirs.append(claude_path)

                    # Limit to first 10 directories to avoid hanging
                    if len(claude_dirs) >= 10:
                        break

            if len(claude_dirs) > 1:
                audit_log("uninstall_orchestrator", "multi_project_warning", {
                    "count": len(claude_dirs),
                    "directories": [str(d) for d in claude_dirs[:5]]  # Log first 5
                })

        except Exception as e:
            # Don't fail validation on multi-project detection
            audit_log("uninstall_orchestrator", "multi_project_check_error", {
                "error": str(e)
            })


def uninstall_plugin(
    project_root: Path | str,
    force: bool = False,
    dry_run: bool = False,
    local_only: bool = False
) -> UninstallResult:
    """Standalone function to uninstall autonomous-dev plugin.

    This is a convenience wrapper around UninstallOrchestrator for simple usage.

    Args:
        project_root: Root directory of project to uninstall from
        force: If True, execute deletion; if False, show preview only
        dry_run: If True, only preview (overrides force)
        local_only: If True, skip global ~/.claude/ and ~/.autonomous-dev/

    Returns:
        UninstallResult with operation status

    Examples:
        >>> # Preview uninstall
        >>> result = uninstall_plugin("/path/to/project", dry_run=True)
        >>> print(f"Would remove {result.files_to_remove} files")
        >>>
        >>> # Execute uninstall
        >>> result = uninstall_plugin("/path/to/project", force=True)
        >>> if result.status == "success":
        ...     print(f"Backup: {result.backup_path}")
    """
    orchestrator = UninstallOrchestrator(project_root)

    # Validate first
    validation = orchestrator.validate()
    if validation.status != "success":
        return validation

    # Execute with requested mode
    return orchestrator.execute(force=force, dry_run=dry_run, local_only=local_only)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python uninstall_orchestrator.py <project_root> [--force] [--dry-run] [--local-only]")
        sys.exit(1)

    project_root = sys.argv[1]
    force = "--force" in sys.argv
    dry_run = "--dry-run" in sys.argv
    local_only = "--local-only" in sys.argv

    result = uninstall_plugin(project_root, force=force, dry_run=dry_run, local_only=local_only)

    print(json.dumps(result.to_dict(), indent=2))

    sys.exit(0 if result.status == "success" else 1)
