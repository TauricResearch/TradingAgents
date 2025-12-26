#!/usr/bin/env python3
"""
Alignment fixer library for PROJECT.md bidirectional sync.

Implements bidirectional alignment sync between PROJECT.md (strategic intent),
documentation (README.md, CLAUDE.md), and code (implementation).

Features:
- Proposes PROJECT.md updates with approval workflow
- Only allows SCOPE (In Scope) and ARCHITECTURE updates (never GOALS, CONSTRAINTS, Out of Scope)
- Backup before modification
- Atomic updates
- Security validation (CWE-22 path traversal prevention)
- Audit logging for all operations

Date: 2025-12-13
Issue: #129 (Bidirectional alignment sync)
Agent: implementer

See error-handling-patterns skill for exception hierarchy and error handling best practices.

Design Patterns:
    See library-design-patterns skill for standardized design patterns.
    See state-management-patterns skill for standardized design patterns.
"""

import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Import security utilities (standard pattern from project libraries)
try:
    from .security_utils import audit_log, validate_path
except ImportError:
    # Direct script execution - add lib dir to path
    lib_dir = Path(__file__).parent.resolve()
    sys.path.insert(0, str(lib_dir))
    from security_utils import audit_log

# Import user state manager for consent workflow
try:
    from .user_state_manager import (
        UserStateManager,
        DEFAULT_STATE_FILE,
        get_user_preference,
        set_user_preference,
    )
except ImportError:
    from user_state_manager import (
        DEFAULT_STATE_FILE,
        get_user_preference,
        set_user_preference,
    )


# Consent preference key
BIDIRECTIONAL_SYNC_CONSENT_KEY = "bidirectional_sync_enabled"

# Protected sections that should NEVER be auto-updated
PROTECTED_SECTIONS = ["GOALS", "CONSTRAINTS"]

# Sections that can be proposed for update (with approval)
PROPOSABLE_SECTIONS = ["SCOPE", "ARCHITECTURE"]

# Sub-sections within SCOPE that are protected
PROTECTED_SCOPE_SUBSECTIONS = ["Out of Scope"]


class AlignmentFixerError(Exception):
    """Exception raised for alignment fixer errors."""
    pass


class ProposedUpdate:
    """Represents a proposed update to PROJECT.md."""

    def __init__(
        self,
        section: str,
        subsection: Optional[str],
        action: str,  # "add", "update", "remove"
        current_value: Optional[str],
        proposed_value: str,
        reason: str,
    ):
        """
        Initialize a proposed update.

        Args:
            section: Section name (e.g., "SCOPE", "ARCHITECTURE")
            subsection: Optional subsection (e.g., "In Scope", "Commands")
            action: Type of change ("add", "update", "remove")
            current_value: Current value if updating/removing
            proposed_value: Proposed new value
            reason: Reason for the change
        """
        self.section = section
        self.subsection = subsection
        self.action = action
        self.current_value = current_value
        self.proposed_value = proposed_value
        self.reason = reason
        self.approved = False
        self.declined = False

    def __repr__(self) -> str:
        return (
            f"ProposedUpdate(section={self.section!r}, "
            f"subsection={self.subsection!r}, "
            f"action={self.action!r}, "
            f"proposed={self.proposed_value!r})"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "section": self.section,
            "subsection": self.subsection,
            "action": self.action,
            "current_value": self.current_value,
            "proposed_value": self.proposed_value,
            "reason": self.reason,
            "approved": self.approved,
            "declined": self.declined,
        }


class AlignmentFixer:
    """
    Manages bidirectional alignment sync for PROJECT.md.

    Handles proposing, reviewing, and applying updates to PROJECT.md
    with approval workflow and security validation.
    """

    def __init__(self, project_root: Path, state_file: Path = DEFAULT_STATE_FILE):
        """
        Initialize AlignmentFixer.

        Args:
            project_root: Root directory of the project
            state_file: Path to user state file for consent

        Raises:
            AlignmentFixerError: If path validation fails
        """
        self.project_root = self._validate_project_root(project_root)
        self.project_md_path = self._find_project_md()
        self.state_file = state_file
        self.pending_updates: List[ProposedUpdate] = []
        self.backup_path: Optional[Path] = None

    def _validate_project_root(self, path: Path) -> Path:
        """
        Validate project root path for security (CWE-22).

        Args:
            path: Path to validate

        Returns:
            Validated Path object

        Raises:
            AlignmentFixerError: If path is unsafe
        """
        if isinstance(path, str):
            path = Path(path)

        # Check for path traversal
        path_str = str(path)
        if ".." in path_str:
            audit_log(
                "security_violation",
                "failure",
                {
                    "type": "path_traversal",
                    "path": path_str,
                    "component": "alignment_fixer"
                }
            )
            raise AlignmentFixerError(f"Path traversal detected: {path_str}")

        # Resolve to absolute path
        try:
            resolved_path = path.resolve()
        except (OSError, RuntimeError) as e:
            raise AlignmentFixerError(f"Failed to resolve path: {e}")

        # Check if directory exists
        if not resolved_path.is_dir():
            raise AlignmentFixerError(f"Project root is not a directory: {resolved_path}")

        return resolved_path

    def _find_project_md(self) -> Path:
        """
        Find PROJECT.md in project root or .claude directory.

        Returns:
            Path to PROJECT.md

        Raises:
            AlignmentFixerError: If PROJECT.md not found
        """
        # Check root level first
        root_path = self.project_root / "PROJECT.md"
        if root_path.exists():
            return root_path

        # Check .claude directory (follow symlink if needed)
        claude_path = self.project_root / ".claude" / "PROJECT.md"
        if claude_path.exists():
            # If it's a symlink, resolve to actual file
            if claude_path.is_symlink():
                resolved = claude_path.resolve()
                if resolved.exists():
                    return resolved
            return claude_path

        raise AlignmentFixerError(
            f"PROJECT.md not found in {self.project_root} or {self.project_root / '.claude'}"
        )

    def is_consent_enabled(self) -> bool:
        """
        Check if bidirectional sync consent is enabled.

        Returns:
            True if consent given, False otherwise
        """
        # Check environment variable override first
        env_value = os.environ.get("BIDIRECTIONAL_SYNC_ENABLED", "").lower()
        if env_value in ("true", "1", "yes"):
            return True
        if env_value in ("false", "0", "no"):
            return False

        # Fall back to user state
        return get_user_preference(
            BIDIRECTIONAL_SYNC_CONSENT_KEY,
            self.state_file,
            default=None,  # None means not yet asked
        )

    def record_consent(self, enabled: bool) -> None:
        """
        Record user consent for bidirectional sync.

        Args:
            enabled: Whether sync is enabled
        """
        set_user_preference(
            BIDIRECTIONAL_SYNC_CONSENT_KEY,
            enabled,
            self.state_file,
        )
        audit_log(
            "bidirectional_sync_consent",
            "success",
            {
                "enabled": enabled,
                "state_file": str(self.state_file),
            }
        )

    def is_section_protected(self, section: str, subsection: Optional[str] = None) -> bool:
        """
        Check if a section is protected from auto-updates.

        Args:
            section: Section name
            subsection: Optional subsection name

        Returns:
            True if protected, False if can be proposed
        """
        # Top-level protected sections
        if section in PROTECTED_SECTIONS:
            return True

        # Protected subsections within SCOPE
        if section == "SCOPE" and subsection in PROTECTED_SCOPE_SUBSECTIONS:
            return True

        return False

    def propose_update(
        self,
        section: str,
        proposed_value: str,
        reason: str,
        subsection: Optional[str] = None,
        action: str = "add",
        current_value: Optional[str] = None,
    ) -> ProposedUpdate:
        """
        Propose an update to PROJECT.md.

        Args:
            section: Section to update (must be in PROPOSABLE_SECTIONS)
            proposed_value: Value to add/update
            reason: Reason for the change
            subsection: Optional subsection
            action: "add", "update", or "remove"
            current_value: Current value if updating/removing

        Returns:
            ProposedUpdate object

        Raises:
            AlignmentFixerError: If section is protected
        """
        # Validate section
        if section not in PROPOSABLE_SECTIONS:
            raise AlignmentFixerError(
                f"Section '{section}' cannot be proposed for update. "
                f"Only {PROPOSABLE_SECTIONS} can be updated. "
                f"Protected sections: {PROTECTED_SECTIONS}"
            )

        # Validate subsection
        if self.is_section_protected(section, subsection):
            raise AlignmentFixerError(
                f"Subsection '{subsection}' within '{section}' is protected and cannot be updated."
            )

        # Create proposal
        update = ProposedUpdate(
            section=section,
            subsection=subsection,
            action=action,
            current_value=current_value,
            proposed_value=proposed_value,
            reason=reason,
        )

        self.pending_updates.append(update)

        audit_log(
            "project_md_update_proposed",
            "success",
            {
                "section": section,
                "subsection": subsection,
                "action": action,
                "proposed_value": proposed_value[:100],  # Truncate for log
                "reason": reason,
            }
        )

        return update

    def format_proposals_for_display(self) -> str:
        """
        Format pending proposals for user display.

        Returns:
            Formatted string showing all proposals
        """
        if not self.pending_updates:
            return "No pending PROJECT.md updates."

        lines = [
            "Proposed PROJECT.md updates:",
            "━" * 40,
        ]

        for i, update in enumerate(self.pending_updates, 1):
            section_display = update.section
            if update.subsection:
                section_display = f"{update.section} ({update.subsection})"

            lines.append(f"\n{i}. {section_display}:")
            lines.append(f"   Action: {update.action}")

            if update.current_value:
                lines.append(f"   Current: {update.current_value}")

            lines.append(f"   Proposed: {update.proposed_value}")
            lines.append(f"   Reason: {update.reason}")

        lines.append("\n" + "━" * 40)

        return "\n".join(lines)

    def create_backup(self) -> Path:
        """
        Create a backup of PROJECT.md before modification.

        Returns:
            Path to backup file

        Raises:
            AlignmentFixerError: If backup fails
        """
        if not self.project_md_path.exists():
            raise AlignmentFixerError("PROJECT.md does not exist")

        # Create backup directory
        backup_dir = Path.home() / ".autonomous-dev" / "backups" / "project_md"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Ensure secure permissions
        backup_dir.chmod(0o700)

        # Create timestamped backup
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"PROJECT.md.{timestamp}.backup"
        backup_path = backup_dir / backup_name

        try:
            shutil.copy2(self.project_md_path, backup_path)
            backup_path.chmod(0o600)
            self.backup_path = backup_path

            audit_log(
                "project_md_backup_created",
                "success",
                {
                    "source": str(self.project_md_path),
                    "backup": str(backup_path),
                }
            )

            return backup_path

        except (OSError, shutil.Error) as e:
            audit_log(
                "project_md_backup_failed",
                "failure",
                {
                    "source": str(self.project_md_path),
                    "error": str(e),
                }
            )
            raise AlignmentFixerError(f"Failed to create backup: {e}")

    def apply_approved_updates(self) -> Tuple[int, List[str]]:
        """
        Apply all approved updates to PROJECT.md.

        Returns:
            Tuple of (applied_count, list of applied descriptions)

        Raises:
            AlignmentFixerError: If update fails
        """
        approved = [u for u in self.pending_updates if u.approved]

        if not approved:
            return 0, []

        # Create backup first
        self.create_backup()

        # Read current content
        content = self.project_md_path.read_text()
        applied_descriptions = []

        try:
            for update in approved:
                content = self._apply_single_update(content, update)
                applied_descriptions.append(
                    f"{update.action} in {update.section}: {update.proposed_value[:50]}"
                )

            # Atomic write: write to temp file, then rename
            temp_path = self.project_md_path.with_suffix(".tmp")
            temp_path.write_text(content)
            temp_path.replace(self.project_md_path)

            audit_log(
                "project_md_updates_applied",
                "success",
                {
                    "applied_count": len(approved),
                    "backup": str(self.backup_path),
                }
            )

            # Clear applied updates from pending
            self.pending_updates = [u for u in self.pending_updates if not u.approved]

            return len(approved), applied_descriptions

        except Exception as e:
            # Attempt rollback
            if self.backup_path and self.backup_path.exists():
                self._rollback()

            audit_log(
                "project_md_update_failed",
                "failure",
                {
                    "error": str(e),
                    "rollback_attempted": self.backup_path is not None,
                }
            )
            raise AlignmentFixerError(f"Failed to apply updates: {e}")

    def _apply_single_update(self, content: str, update: ProposedUpdate) -> str:
        """
        Apply a single update to PROJECT.md content.

        Args:
            content: Current file content
            update: Update to apply

        Returns:
            Modified content
        """
        if update.section == "SCOPE":
            return self._apply_scope_update(content, update)
        elif update.section == "ARCHITECTURE":
            return self._apply_architecture_update(content, update)
        else:
            raise AlignmentFixerError(f"Unknown section: {update.section}")

    def _apply_scope_update(self, content: str, update: ProposedUpdate) -> str:
        """Apply update to SCOPE section."""
        # Find the "In Scope" section
        in_scope_pattern = r"(\*\*What's IN Scope\*\*.+?)(\n\n\*\*What's OUT)"
        match = re.search(in_scope_pattern, content, re.DOTALL)

        if not match:
            # Try alternate pattern
            in_scope_pattern = r"(## SCOPE.+?IN Scope.+?)(\n\n.*?OUT)"
            match = re.search(in_scope_pattern, content, re.DOTALL)

        if not match:
            raise AlignmentFixerError("Could not find 'In Scope' section in PROJECT.md")

        in_scope_section = match.group(1)

        if update.action == "add":
            # Add new item to end of In Scope section
            new_line = f"- ✅ **{update.proposed_value}**"
            if update.reason:
                new_line += f" - {update.reason}"

            # Find the last bullet point in the section
            bullets = list(re.finditer(r"- ✅ .+", in_scope_section))
            if bullets:
                last_bullet = bullets[-1]
                insert_pos = match.start(1) + last_bullet.end()
                content = content[:insert_pos] + "\n" + new_line + content[insert_pos:]
            else:
                # Just append to section
                content = content[:match.end(1)] + "\n" + new_line + content[match.end(1):]

        return content

    def _apply_architecture_update(self, content: str, update: ProposedUpdate) -> str:
        """Apply update to ARCHITECTURE section."""
        # Handle count updates (e.g., "Commands: 7 → 8")
        if update.subsection and "count" in update.subsection.lower():
            # Pattern like "**Commands**: 7 active"
            pattern = rf"(\*\*{update.subsection}\*\*[:\s]+)(\d+)"

            def replace_count(m):
                return m.group(1) + update.proposed_value

            content = re.sub(pattern, replace_count, content)

        return content

    def _rollback(self) -> None:
        """Rollback to backup if available."""
        if not self.backup_path or not self.backup_path.exists():
            return

        try:
            shutil.copy2(self.backup_path, self.project_md_path)
            audit_log(
                "project_md_rollback",
                "success",
                {
                    "backup": str(self.backup_path),
                    "target": str(self.project_md_path),
                }
            )
        except Exception as e:
            audit_log(
                "project_md_rollback_failed",
                "failure",
                {
                    "backup": str(self.backup_path),
                    "error": str(e),
                }
            )

    def mark_approved(self, indices: List[int]) -> int:
        """
        Mark specific proposals as approved.

        Args:
            indices: 1-based indices of proposals to approve

        Returns:
            Number of proposals marked approved
        """
        count = 0
        for idx in indices:
            if 1 <= idx <= len(self.pending_updates):
                self.pending_updates[idx - 1].approved = True
                count += 1
        return count

    def mark_declined(self, indices: List[int]) -> int:
        """
        Mark specific proposals as declined.

        Args:
            indices: 1-based indices of proposals to decline

        Returns:
            Number of proposals marked declined
        """
        count = 0
        for idx in indices:
            if 1 <= idx <= len(self.pending_updates):
                self.pending_updates[idx - 1].declined = True
                count += 1

        # Log declined proposals
        for idx in indices:
            if 1 <= idx <= len(self.pending_updates):
                update = self.pending_updates[idx - 1]
                audit_log(
                    "project_md_update_declined",
                    "success",
                    {
                        "section": update.section,
                        "proposed_value": update.proposed_value[:100],
                        "reason": update.reason,
                    }
                )

        return count


# Module-level convenience functions

def check_bidirectional_sync_consent(state_file: Path = DEFAULT_STATE_FILE) -> Optional[bool]:
    """
    Check if bidirectional sync consent has been given.

    Returns:
        True if enabled, False if disabled, None if not yet asked
    """
    return get_user_preference(
        BIDIRECTIONAL_SYNC_CONSENT_KEY,
        state_file,
        default=None,
    )


def record_bidirectional_sync_consent(
    enabled: bool,
    state_file: Path = DEFAULT_STATE_FILE
) -> None:
    """
    Record bidirectional sync consent.

    Args:
        enabled: Whether sync is enabled
        state_file: Path to state file
    """
    set_user_preference(
        BIDIRECTIONAL_SYNC_CONSENT_KEY,
        enabled,
        state_file,
    )
    audit_log(
        "bidirectional_sync_consent",
        "success",
        {
            "enabled": enabled,
            "state_file": str(state_file),
        }
    )


def propose_scope_addition(
    project_root: Path,
    feature_name: str,
    reason: str,
) -> ProposedUpdate:
    """
    Convenience function to propose adding a feature to SCOPE.

    Args:
        project_root: Project root directory
        feature_name: Name of feature to add
        reason: Reason for addition

    Returns:
        ProposedUpdate object
    """
    fixer = AlignmentFixer(project_root)
    return fixer.propose_update(
        section="SCOPE",
        subsection="In Scope",
        action="add",
        proposed_value=feature_name,
        reason=reason,
    )


def is_section_protected(section: str, subsection: Optional[str] = None) -> bool:
    """
    Check if a section is protected from auto-updates.

    Args:
        section: Section name
        subsection: Optional subsection name

    Returns:
        True if protected, False if can be proposed
    """
    if section in PROTECTED_SECTIONS:
        return True
    if section == "SCOPE" and subsection in PROTECTED_SCOPE_SUBSECTIONS:
        return True
    return False
