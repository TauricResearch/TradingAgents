#!/usr/bin/env python3
"""
PROJECT.md Updater - Atomic updates to project goal progress

This library provides safe, atomic updates to PROJECT.md goal progress tracking.
All operations include security validation and backup/rollback capabilities.

Security Features:
- Path traversal prevention (no ../../etc/passwd attacks)
- Symlink detection and rejection
- Atomic file writes (temp file + rename pattern)
- Backup creation before modifications
- Merge conflict detection
- Shared security validation via security_utils module

Usage:
    from project_md_updater import ProjectMdUpdater

    updater = ProjectMdUpdater(Path("PROJECT.md"))
    updater.update_goal_progress("Goal 1", 25)  # Update to 25%

Date: 2025-11-07
Feature: PROJECT.md auto-update with shared security_utils
Agent: implementer
Issue: GitHub #46 (refactor to use shared security module)

Relevant Skills:
    - project-alignment-validation: Conflict resolution patterns for PROJECT.md updates
    - library-design-patterns: Standardized design patterns
"""

import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any

# Import shared security utilities
# Handle both module import (from package) and direct script execution
try:
    from .security_utils import validate_path, audit_log
except ImportError:
    # Direct script execution - add lib dir to path
    lib_dir = Path(__file__).parent.resolve()
    sys.path.insert(0, str(lib_dir))
    from security_utils import validate_path, audit_log


class ProjectMdUpdater:
    """

    See error-handling-patterns skill for exception hierarchy and error handling best practices.

    Safe, atomic updater for PROJECT.md goal progress."""

    def __init__(self, project_file: Path):
        """Initialize updater with security validation.

        Args:
            project_file: Path to PROJECT.md file

        Raises:
            ValueError: If path is symlink, outside project, or invalid

        Security:
            Uses shared security_utils.validate_path() for consistent validation
            across all modules. Logs all validation attempts to security audit log.
        """
        # SECURITY: Validate path using shared validation module
        # This ensures consistent security enforcement across all components
        resolved_path = validate_path(
            project_file,
            purpose="PROJECT.md update",
            allow_missing=True  # Allow non-existent PROJECT.md (will be created)
        )

        self.project_file = resolved_path
        # Keep original path's parent for mkstemp (avoids /var vs /private/var mismatch on macOS)
        self._mkstemp_dir = str(project_file.parent)
        self.backup_file: Optional[Path] = None

        # Audit log initialization
        audit_log("project_md_updater", "initialized", {
            "operation": "init",
            "project_file": str(self.project_file),
            "mkstemp_dir": self._mkstemp_dir
        })

    def _create_backup(self) -> Path:
        """Create timestamped backup of PROJECT.md.

        Returns:
            Path to backup file

        Format: PROJECT.md.backup.YYYYMMDD-HHMMSS
        """
        if not self.project_file.exists():
            raise FileNotFoundError(
                f"PROJECT.md not found: {self.project_file}\n"
                f"Cannot create backup of non-existent file"
            )

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = self.project_file.parent / f"{self.project_file.name}.backup.{timestamp}"

        # Copy content to backup
        content = self.project_file.read_text()
        backup_path.write_text(content)

        self.backup_file = backup_path
        return backup_path

    def _detect_merge_conflict(self, content: str) -> bool:
        """Detect merge conflict markers in content.

        Args:
            content: File content to check

        Returns:
            True if conflict markers detected, False otherwise
        """
        conflict_markers = ["<<<<<<<", "=======", ">>>>>>>"]
        return any(marker in content for marker in conflict_markers)

    def _atomic_write(self, content: str):
        """Write content to PROJECT.md atomically using tempfile.mkstemp().

        Security Rationale (GitHub Issue #45):
        ========================================
        This method uses tempfile.mkstemp() instead of PID-based temp file creation
        to prevent race condition vulnerabilities:

        - PID-based naming: f".PROJECT_{os.getpid()}.tmp" is VULNERABLE
          * Attacker can predict temp filename (PID observable via /proc or ps)
          * Race condition: Attacker creates symlink before process writes
          * Result: Process writes to attacker-controlled location

        - mkstemp() approach: SECURE
          * Uses cryptographic random suffix (unpredictable)
          * Fails if file exists (atomic creation, no TOCTOU)
          * Returns file descriptor (exclusive access guaranteed)
          * Mode 0600 permissions (owner-only access)

        Atomic Write Pattern:
        =====================
        1. CREATE: mkstemp() creates temp file with random name in same directory
        2. WRITE: Content written via os.write(fd, ...) for atomicity
        3. CLOSE: File descriptor closed before rename
        4. RENAME: temp_path.replace(target) atomically updates file

        Failure Safety:
        ===============
        - Process crash before rename: Original file unchanged (data intact)
        - Write error: Temp file cleaned up, FD closed (no resource leak)
        - Rename error: Temp file cleaned up (no orphaned files)

        Args:
            content: New content to write

        Raises:
            IOError: If write or rename fails
        """
        temp_fd = None
        temp_path = None

        try:
            # Create temp file in same directory as target (ensures same filesystem)
            # mkstemp() returns (fd, path) with:
            # - Unique filename (includes random suffix)
            # - Exclusive access (fd is open, file exists)
            # - Mode 0600 (readable/writable by owner only)
            # Use _mkstemp_dir to avoid /var vs /private/var mismatch on macOS
            temp_fd, temp_path_str = tempfile.mkstemp(
                dir=self._mkstemp_dir,
                prefix='.PROJECT.',
                suffix='.tmp',
                text=False  # Binary mode for cross-platform compatibility
            )
            temp_path = Path(temp_path_str)

            # Write content via file descriptor for atomic operation
            # os.write() writes exactly to the fd, no Python buffering
            os.write(temp_fd, content.encode('utf-8'))

            # Close FD before rename (required for Windows, good practice for POSIX)
            os.close(temp_fd)
            temp_fd = None  # Mark as closed to prevent double-close in except block

            # Atomic rename (POSIX guarantees atomicity)
            # Path.replace() on Windows 3.8+ also atomic
            # After this line: target file has new content OR is unchanged
            # Never in a partially-written state
            temp_path.replace(self.project_file)

            # Audit log successful write
            audit_log("project_md_updater", "success", {
                "operation": "atomic_write",
                "target_file": str(self.project_file),
                "temp_file": str(temp_path),
                "content_size": len(content)
            })

        except Exception as e:
            # Audit log failure
            audit_log("project_md_updater", "failure", {
                "operation": "atomic_write",
                "target_file": str(self.project_file),
                "temp_file": str(temp_path) if temp_path else None,
                "error": str(e)
            })

            # Cleanup file descriptor on any error
            # This prevents resource exhaustion (FD leak)
            if temp_fd is not None:
                try:
                    os.close(temp_fd)
                except:
                    pass

            # Cleanup temp file on error
            # This prevents orphaned .tmp files accumulating
            if temp_path:
                try:
                    temp_path.unlink()
                except:
                    # Ignore errors during cleanup (file might not exist)
                    pass

            raise IOError(f"Failed to write PROJECT.md: {e}") from e

    def update_goal_progress(self, updates: Dict[str, int]) -> bool:
        """Update goal progress percentages.

        Args:
            updates: Dict mapping goal names to progress percentages
                    e.g., {"goal_1": 45, "goal_2": 30}

        Returns:
            True if any goals were updated, False if none found

        Raises:
            ValueError: If percentage invalid or merge conflict detected
            FileNotFoundError: If PROJECT.md doesn't exist
        """
        # If single goal, delegate to update_multiple_goals for consistency
        return self.update_multiple_goals(updates)

    def update_metric(self, metric_name: str, value: int) -> bool:
        """Update metric value in PROJECT.md.

        Args:
            metric_name: Name of the metric (e.g., "Features completed")
            value: New metric value

        Returns:
            True if updated, False if metric not found

        Raises:
            ValueError: If merge conflict detected
            FileNotFoundError: If PROJECT.md doesn't exist
        """
        # Check file exists
        if not self.project_file.exists():
            raise FileNotFoundError(
                f"PROJECT.md not found: {self.project_file}\n"
                f"Cannot update non-existent file"
            )

        # Read current content
        content = self.project_file.read_text()

        # Check for merge conflicts
        if self._detect_merge_conflict(content):
            raise ValueError(
                f"merge conflict detected in {self.project_file}\n"
                f"Cannot update PROJECT.md with unresolved conflicts."
            )

        # Create backup
        self._create_backup()

        # Pattern: "- Metric Name: 123" -> "- Metric Name: 456"
        pattern = rf"(- {re.escape(metric_name)}:\s*)\d+"
        replacement = rf"\g<1>{value}"

        updated_content = re.sub(pattern, replacement, content)

        # Check if anything was updated
        if updated_content == content:
            return False

        # Write atomically
        self._atomic_write(updated_content)

        return True

    def update_multiple_goals(self, updates: Dict[str, int]) -> bool:
        """Update multiple goals in a single atomic operation.

        Args:
            updates: Dict mapping goal names to progress percentages

        Returns:
            True if any goals were updated, False if none found

        Raises:
            ValueError: If any percentage invalid or merge conflict detected
            FileNotFoundError: If PROJECT.md doesn't exist
        """
        # Validate all percentages first
        for goal_name, percentage in updates.items():
            if not isinstance(percentage, int) or percentage < 0 or percentage > 100:
                raise ValueError(
                    f"Invalid progress percentage for {goal_name}: {percentage}\n"
                    f"Expected: Integer 0-100"
                )

        # Check file exists
        if not self.project_file.exists():
            raise FileNotFoundError(
                f"PROJECT.md not found: {self.project_file}\n"
                f"Cannot update non-existent file"
            )

        # Read current content
        content = self.project_file.read_text()

        # Check for merge conflicts
        if self._detect_merge_conflict(content):
            raise ValueError(
                f"merge conflict detected in {self.project_file}\n"
                f"Cannot update PROJECT.md with unresolved conflicts."
            )

        # Create backup
        self._create_backup()

        # Apply all updates
        updated_content = content
        any_updated = False
        for goal_name, percentage in updates.items():
            # Match format: "- goal_name: Description (Target: XX%)"
            # Update to: "- goal_name: Description (Target: XX%, Current: YY%)"

            # First check if Current already exists
            current_pattern = rf"(- {re.escape(goal_name)}:.*?Target:\s*\d+%,\s*Current:\s*)\d+(%\))"
            if re.search(current_pattern, updated_content):
                # Update existing Current value
                new_content = re.sub(current_pattern, rf"\g<1>{percentage}\g<2>", updated_content)
            else:
                # Add Current value after Target
                add_current_pattern = rf"(- {re.escape(goal_name)}:.*?Target:\s*\d+%)(\))"
                new_content = re.sub(add_current_pattern, rf"\g<1>, Current: {percentage}%\g<2>", updated_content)

            if new_content != updated_content:
                any_updated = True
            updated_content = new_content

        # Write atomically only if something changed
        if any_updated:
            self._atomic_write(updated_content)

        return any_updated

    def validate_syntax(self) -> Dict[str, Any]:
        """Validate PROJECT.md syntax after updates.

        Returns:
            Dict with validation results:
            - valid: bool (True if valid)
            - sections: list of section headers found
            - errors: list of error messages (if any)
        """
        if not self.project_file.exists():
            return {
                "valid": False,
                "sections": [],
                "errors": ["PROJECT.md not found"]
            }

        content = self.project_file.read_text()

        # Check for required sections
        required_sections = ["## GOALS"]
        found_sections = []
        errors = []

        for section in required_sections:
            if section in content:
                found_sections.append(section)
            else:
                errors.append(f"Missing required section: {section}")

        # Check for merge conflicts
        if self._detect_merge_conflict(content):
            errors.append("Merge conflict markers detected")

        return {
            "valid": len(errors) == 0,
            "sections": found_sections,
            "errors": errors
        }

    def rollback(self):
        """Rollback to backup if something went wrong.

        Raises:
            ValueError: If no backup exists to rollback to
        """
        if not self.backup_file or not self.backup_file.exists():
            raise ValueError(
                "No backup available to rollback to.\n"
                f"Backup file: {self.backup_file}"
            )

        # Restore from backup
        content = self.backup_file.read_text()
        self._atomic_write(content)
