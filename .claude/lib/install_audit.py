#!/usr/bin/env python3
"""
Install Audit - Audit logging for GenAI-first installation system

This module provides audit trail logging for installation operations,
tracking protected files, conflicts, resolutions, and outcomes.

Key Features:
- JSONL format audit logs (one JSON per line)
- Installation attempt tracking with unique IDs
- Protected file recording
- Conflict tracking and resolution logging
- Report generation from audit trail
- Crash-resistant (append-only, recoverable)

Usage:
    from install_audit import InstallAudit

    # Start installation
    audit = InstallAudit(Path.home() / ".autonomous-dev" / "install_audit.jsonl")
    install_id = audit.start_installation("fresh")

    # Log events
    audit.record_protected_file(install_id, ".env", "secrets")
    audit.log_success(install_id, files_copied=42)

    # Generate report
    report = audit.generate_report(install_id)

Date: 2025-12-09
Issue: #106 (GenAI-first installation system)
Agent: implementer

Design Patterns:
    See library-design-patterns skill for standardized design patterns.
"""

import json
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Security utilities
try:
    from plugins.autonomous_dev.lib.security_utils import audit_log
except ImportError:
    from security_utils import audit_log


class AuditEntry:
    """Audit log entry data class."""

    def __init__(
        self,
        event: str,
        install_id: str,
        timestamp: Optional[str] = None,
        **kwargs
    ):
        """Initialize audit entry.

        Args:
            event: Event type (installation_start, protected_file, etc.)
            install_id: Unique installation ID
            timestamp: ISO 8601 timestamp (auto-generated if None)
            **kwargs: Additional event-specific data
        """
        self.event = event
        self.install_id = install_id
        self.timestamp = timestamp or (datetime.utcnow().isoformat() + "Z")
        self.data = kwargs

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "event": self.event,
            "install_id": self.install_id,
            "timestamp": self.timestamp,
            **self.data
        }


class InstallAudit:
    """Audit logging for installation operations.

    This class provides append-only audit logging in JSONL format,
    tracking all installation events for security and debugging.

    Attributes:
        audit_file: Path to audit log file (JSONL format)

    Examples:
        >>> audit = InstallAudit(Path("install_audit.jsonl"))
        >>> install_id = audit.start_installation("fresh")
        >>> audit.log_success(install_id, files_copied=42)
    """

    def __init__(self, audit_file: Path | str):
        """Initialize audit logger.

        Args:
            audit_file: Path to audit log file

        Note:
            Parent directories are created automatically.
            File is created in append mode (preserves existing entries).
        """
        self.audit_file = Path(audit_file) if isinstance(audit_file, str) else audit_file

        # Create parent directories
        self.audit_file.parent.mkdir(parents=True, exist_ok=True)

        # Security audit log
        audit_log("install_audit", "initialized", {
            "audit_file": str(self.audit_file)
        })

    def start_installation(self, install_type: str) -> str:
        """Log installation start and return unique install ID.

        Args:
            install_type: Installation type (fresh, brownfield, upgrade)

        Returns:
            Unique installation ID (UUID)

        Examples:
            >>> audit = InstallAudit(Path("audit.jsonl"))
            >>> install_id = audit.start_installation("fresh")
        """
        install_id = str(uuid.uuid4())

        entry = AuditEntry(
            event="installation_start",
            install_id=install_id,
            install_type=install_type
        )

        self._write_entry(entry)
        return install_id

    def log_success(self, install_id: str, files_copied: int, **kwargs) -> None:
        """Log successful installation completion.

        Args:
            install_id: Installation ID from start_installation()
            files_copied: Number of files copied
            **kwargs: Additional context (files_skipped, files_backed_up, etc.)

        Examples:
            >>> audit.log_success(install_id, files_copied=42, files_skipped=2)
        """
        entry = AuditEntry(
            event="installation_success",
            install_id=install_id,
            files_copied=files_copied,
            **kwargs
        )

        self._write_entry(entry)

    def log_failure(self, install_id: str, error: str, **kwargs) -> None:
        """Log failed installation.

        Args:
            install_id: Installation ID from start_installation()
            error: Error message
            **kwargs: Additional context

        Examples:
            >>> audit.log_failure(install_id, error="Permission denied")
        """
        entry = AuditEntry(
            event="installation_failure",
            install_id=install_id,
            error=error,
            **kwargs
        )

        self._write_entry(entry)

    def record_protected_file(
        self,
        install_id: str,
        file_path: str,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Record a protected file.

        Args:
            install_id: Installation ID
            file_path: Relative path to protected file
            reason: Why file is protected
            metadata: Optional additional metadata

        Examples:
            >>> audit.record_protected_file(
            ...     install_id,
            ...     ".env",
            ...     "secrets",
            ...     metadata={"size": 1024}
            ... )
        """
        # Validate path for security
        self._validate_path(file_path)

        entry = AuditEntry(
            event="protected_file",
            install_id=install_id,
            file=file_path,
            reason=reason
        )

        if metadata:
            entry.data["metadata"] = metadata

        self._write_entry(entry)

    def record_conflict(
        self,
        install_id: str,
        file_path: str,
        existing_hash: str,
        staging_hash: str,
        **kwargs
    ) -> None:
        """Record a file conflict.

        Args:
            install_id: Installation ID
            file_path: Relative path to conflicting file
            existing_hash: Hash of existing file
            staging_hash: Hash of staging file
            **kwargs: Additional context

        Examples:
            >>> audit.record_conflict(
            ...     install_id,
            ...     "file.py",
            ...     existing_hash="abc",
            ...     staging_hash="def"
            ... )
        """
        self._validate_path(file_path)

        entry = AuditEntry(
            event="conflict",
            install_id=install_id,
            file=file_path,
            existing_hash=existing_hash,
            staging_hash=staging_hash,
            **kwargs
        )

        self._write_entry(entry)

    def record_conflict_resolution(
        self,
        install_id: str,
        file_path: str,
        action: str,
        **kwargs
    ) -> None:
        """Record conflict resolution action.

        Args:
            install_id: Installation ID
            file_path: Relative path to file
            action: Action taken (backup, skip, overwrite)
            **kwargs: Additional context (backup_path, etc.)

        Examples:
            >>> audit.record_conflict_resolution(
            ...     install_id,
            ...     "file.py",
            ...     action="backup",
            ...     backup_path="file.py.bak"
            ... )
        """
        self._validate_path(file_path)

        entry = AuditEntry(
            event="conflict_resolution",
            install_id=install_id,
            file=file_path,
            action=action,
            **kwargs
        )

        self._write_entry(entry)

    def generate_report(self, install_id: str) -> Dict[str, Any]:
        """Generate installation report from audit trail.

        Args:
            install_id: Installation ID to generate report for

        Returns:
            Dict with installation report:
            - install_id: Installation ID
            - status: Status (success, failure, in_progress)
            - timeline: Chronological list of events
            - summary: Summary statistics
            - protected_files: List of protected files
            - conflicts: List of conflicts

        Raises:
            ValueError: If install ID not found in audit log

        Examples:
            >>> report = audit.generate_report(install_id)
            >>> print(f"Status: {report['status']}")
        """
        entries = self._read_entries_for_install(install_id)

        if not entries:
            raise ValueError(f"Install ID not found: {install_id}")

        # Parse entries
        status = "in_progress"
        timeline = []
        protected_files = []
        conflicts = []
        stats = {
            "total_protected_files": 0,
            "total_conflicts": 0,
            "files_copied": 0
        }

        for entry_dict in entries:
            event = entry_dict["event"]
            timeline.append(entry_dict)

            if event == "installation_success":
                status = "success"
                stats["files_copied"] = entry_dict.get("files_copied", 0)

            elif event == "installation_failure":
                status = "failure"

            elif event == "protected_file":
                protected_files.append(entry_dict["file"])
                stats["total_protected_files"] += 1

            elif event == "conflict":
                conflicts.append(entry_dict["file"])
                stats["total_conflicts"] += 1

        return {
            "install_id": install_id,
            "status": status,
            "timeline": timeline,
            "summary": stats,
            "protected_files": protected_files,
            "conflicts": conflicts
        }

    def export_report(self, install_id: str, report_file: Path | str) -> None:
        """Export installation report to JSON file.

        Args:
            install_id: Installation ID
            report_file: Path to output report file

        Examples:
            >>> audit.export_report(install_id, Path("report.json"))
        """
        report = self.generate_report(install_id)

        report_path = Path(report_file) if isinstance(report_file, str) else report_file
        report_path.parent.mkdir(parents=True, exist_ok=True)

        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

    def get_all_installations(self) -> List[Dict[str, Any]]:
        """Get all installation attempts from audit log.

        Returns:
            List of installation info dicts (one per install_id)

        Examples:
            >>> history = audit.get_all_installations()
            >>> print(f"Found {len(history)} installations")
        """
        if not self.audit_file.exists():
            return []

        installations = {}

        with open(self.audit_file, "r") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    install_id = entry.get("install_id")

                    if not install_id:
                        continue

                    # Track start entries
                    if entry["event"] == "installation_start":
                        installations[install_id] = {
                            "install_id": install_id,
                            "install_type": entry.get("install_type"),
                            "timestamp": entry.get("timestamp")
                        }

                except json.JSONDecodeError:
                    # Skip corrupted lines
                    continue

        return list(installations.values())

    def get_installations_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get installations filtered by status.

        Args:
            status: Status to filter by (success, failure)

        Returns:
            List of installation info dicts matching status

        Examples:
            >>> successful = audit.get_installations_by_status("success")
        """
        installations = []

        for install_info in self.get_all_installations():
            install_id = install_info["install_id"]

            try:
                report = self.generate_report(install_id)
                if report["status"] == status:
                    installations.append(install_info)
            except ValueError:
                continue

        return installations

    def _write_entry(self, entry: AuditEntry) -> None:
        """Write audit entry to log file.

        Args:
            entry: AuditEntry to write
        """
        # Append to audit file
        with open(self.audit_file, "a") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

    def _read_entries_for_install(self, install_id: str) -> List[Dict[str, Any]]:
        """Read all entries for a specific installation.

        Args:
            install_id: Installation ID

        Returns:
            List of entry dicts for this installation
        """
        if not self.audit_file.exists():
            return []

        entries = []

        with open(self.audit_file, "r") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry.get("install_id") == install_id:
                        entries.append(entry)
                except json.JSONDecodeError:
                    # Skip corrupted lines
                    continue

        return entries

    def _validate_path(self, file_path: str) -> None:
        """Validate file path for security.

        Args:
            file_path: Relative file path

        Raises:
            ValueError: If path contains traversal or is absolute
        """
        # Check for path traversal
        if ".." in file_path:
            raise ValueError(f"Path traversal not allowed (invalid path): {file_path}")

        # Check for absolute paths
        if Path(file_path).is_absolute():
            raise ValueError(f"Absolute paths not allowed (invalid path): {file_path}")
