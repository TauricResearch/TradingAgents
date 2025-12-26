#!/usr/bin/env python3
"""
Staging Manager - Manage staging directory for GenAI-first installation

This module provides staging directory management for the GenAI-first installation
system, including validation, file listing, conflict detection, and cleanup.

Key Features:
- Staging directory validation and initialization
- File listing with metadata (size, hash)
- Conflict detection between staging and target
- Security validation (path traversal, symlinks)
- Cleanup operations (full and partial)

Usage:
    from staging_manager import StagingManager

    # Initialize staging directory
    manager = StagingManager(Path.home() / ".autonomous-dev-staging")

    # List staged files
    files = manager.list_files()

    # Detect conflicts with target
    conflicts = manager.detect_conflicts(project_dir)

    # Cleanup
    manager.cleanup()

Date: 2025-12-09
Issue: #106 (GenAI-first installation system)
Agent: implementer

Design Patterns:
    See library-design-patterns skill for standardized design patterns.
"""

import hashlib
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional

# Security utilities for path validation
try:
    from plugins.autonomous_dev.lib.security_utils import validate_path, audit_log
except ImportError:
    from security_utils import audit_log


class StagingManager:
    """Manage staging directory for GenAI-first installation.

    This class handles staging directory operations including validation,
    file listing, conflict detection, and cleanup.

    Attributes:
        staging_dir: Path to staging directory

    Examples:
        >>> manager = StagingManager(Path.home() / ".autonomous-dev-staging")
        >>> files = manager.list_files()
        >>> print(f"Staged {len(files)} files")
    """

    def __init__(self, staging_dir: Path | str):
        """Initialize staging manager with security validation.

        Args:
            staging_dir: Path to staging directory

        Raises:
            ValueError: If path is not a directory or validation fails
        """
        # Convert to Path if string
        staging_path = Path(staging_dir) if isinstance(staging_dir, str) else staging_dir
        staging_path = staging_path.resolve()

        # Check if path exists and is not a directory
        if staging_path.exists() and not staging_path.is_dir():
            raise ValueError(f"Staging path must be a directory, got file: {staging_path}")

        # Create staging directory if it doesn't exist
        if not staging_path.exists():
            staging_path.mkdir(parents=True, exist_ok=True)

        self.staging_dir = staging_path

        # Audit log initialization
        audit_log("staging_manager", "initialized", {
            "staging_dir": str(self.staging_dir)
        })

    def is_secure(self) -> bool:
        """Check if staging directory has secure permissions.

        Returns:
            True if directory has appropriate permissions (readable/writable)
        """
        try:
            # Check if directory is readable and writable
            return os.access(self.staging_dir, os.R_OK | os.W_OK)
        except Exception:
            return False

    def list_files(self) -> List[Dict[str, Any]]:
        """List all files in staging directory with metadata.

        Returns:
            List of dicts with file info:
            - path: Relative path from staging dir
            - size: File size in bytes
            - hash: SHA256 hash of file content

        Examples:
            >>> manager = StagingManager(staging_dir)
            >>> files = manager.list_files()
            >>> for f in files:
            ...     print(f"{f['path']} ({f['size']} bytes)")
        """
        files = []

        # Skip if staging directory doesn't exist
        if not self.staging_dir.exists():
            return files

        # Walk staging directory
        for file_path in self.staging_dir.rglob("*"):
            # Skip directories and hidden files
            if file_path.is_dir():
                continue
            if file_path.name.startswith("."):
                continue

            # Get relative path from staging dir
            relative_path = file_path.relative_to(self.staging_dir)

            # Calculate file metadata
            file_info = {
                "path": str(relative_path).replace("\\", "/"),  # Normalize path separators
                "size": file_path.stat().st_size,
                "hash": self._calculate_hash(file_path)
            }

            files.append(file_info)

        return files

    def get_file_hash(self, relative_path: str) -> Optional[str]:
        """Get SHA256 hash of a specific file.

        Args:
            relative_path: Relative path from staging dir

        Returns:
            SHA256 hex digest or None if file not found

        Raises:
            ValueError: If path contains traversal or is outside staging
        """
        # Validate path for security
        file_path = self.staging_dir / relative_path
        self.validate_path(relative_path)

        if not file_path.exists():
            return None

        return self._calculate_hash(file_path)

    def detect_conflicts(self, target_dir: Path | str) -> List[Dict[str, Any]]:
        """Detect conflicts between staging and target directory.

        A conflict occurs when:
        - File exists in both locations
        - File content differs (different hashes)

        Args:
            target_dir: Target directory to compare against

        Returns:
            List of conflict dicts with:
            - file: Relative path
            - reason: Why it conflicts
            - staging_hash: Hash in staging
            - target_hash: Hash in target

        Examples:
            >>> conflicts = manager.detect_conflicts(project_dir)
            >>> if conflicts:
            ...     print(f"Found {len(conflicts)} conflicts")
        """
        target_path = Path(target_dir) if isinstance(target_dir, str) else target_dir
        target_path = target_path.resolve()

        conflicts = []

        # Get all staged files
        staged_files = self.list_files()

        for file_info in staged_files:
            relative_path = file_info["path"]
            target_file = target_path / relative_path

            # Skip if file doesn't exist in target
            if not target_file.exists():
                continue

            # Calculate target file hash
            target_hash = self._calculate_hash(target_file)

            # Check if content differs
            if target_hash != file_info["hash"]:
                conflicts.append({
                    "file": relative_path,
                    "reason": "content_differs",
                    "staging_hash": file_info["hash"],
                    "target_hash": target_hash
                })

        return conflicts

    def cleanup(self) -> None:
        """Remove entire staging directory.

        This is idempotent - can be called multiple times safely.

        Examples:
            >>> manager.cleanup()
            >>> assert not staging_dir.exists()
        """
        if self.staging_dir.exists():
            shutil.rmtree(self.staging_dir)

            # Audit log cleanup
            audit_log("staging_manager", "cleanup", {
                "staging_dir": str(self.staging_dir)
            })

    def cleanup_files(self, file_paths: List[str]) -> None:
        """Remove specific files from staging directory.

        Args:
            file_paths: List of relative paths to remove

        Examples:
            >>> manager.cleanup_files(["file1.py", "file2.py"])
        """
        for relative_path in file_paths:
            # Validate path
            self.validate_path(relative_path)

            file_path = self.staging_dir / relative_path
            if file_path.exists() and file_path.is_file():
                file_path.unlink()

    def validate_path(self, relative_path: str) -> None:
        """Validate that path is safe (no traversal, no external symlinks).

        Args:
            relative_path: Relative path to validate

        Raises:
            ValueError: If path is unsafe (traversal, external symlink, injection)
        """
        # Check for path traversal
        if ".." in relative_path:
            audit_log("staging_manager", "security_violation", {
                "path": relative_path,
                "reason": "path traversal detected"
            })
            raise ValueError(f"Path contains path traversal: {relative_path}")

        # Check for absolute paths
        if Path(relative_path).is_absolute():
            audit_log("staging_manager", "security_violation", {
                "path": relative_path,
                "reason": "absolute path outside staging"
            })
            raise ValueError(f"Absolute path outside staging directory: {relative_path}")

        # Check for dangerous characters (shell injection prevention)
        dangerous_chars = [";", "|", "&", "$", "`", "(", ")"]
        if any(char in relative_path for char in dangerous_chars):
            audit_log("staging_manager", "security_violation", {
                "path": relative_path,
                "reason": "invalid filename"
            })
            raise ValueError(f"Path contains invalid filename characters: {relative_path}")

        # Get full path (don't resolve yet)
        full_path = self.staging_dir / relative_path

        # Check for symlinks pointing outside staging (check before resolving)
        if full_path.exists() and full_path.is_symlink():
            target = full_path.readlink()
            if target.is_absolute():
                resolved_target = target.resolve()
            else:
                resolved_target = (full_path.parent / target).resolve()

            try:
                resolved_target.relative_to(self.staging_dir)
            except ValueError:
                audit_log("staging_manager", "security_violation", {
                    "path": relative_path,
                    "reason": "symlink outside staging"
                })
                raise ValueError(f"Path contains symlink outside staging: {relative_path}")

        # Resolve full path and check it's within staging
        resolved_path = full_path.resolve()
        try:
            resolved_path.relative_to(self.staging_dir)
        except ValueError:
            audit_log("staging_manager", "security_violation", {
                "path": relative_path,
                "reason": "resolved path outside staging"
            })
            raise ValueError(f"Path resolves outside staging directory: {relative_path}")

    def _calculate_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file.

        Args:
            file_path: Path to file

        Returns:
            SHA256 hex digest
        """
        sha256 = hashlib.sha256()

        # Read file in chunks to handle large files
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)

        return sha256.hexdigest()


# Import os for is_secure method
import os
