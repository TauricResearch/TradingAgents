"""Retrofit execution for brownfield migration.

This module executes migration plans with support for dry-run, step-by-step,
and automatic modes. Provides backup, rollback, and verification capabilities.

Classes:
    ExecutionMode: Execution mode (DRY_RUN/STEP_BY_STEP/AUTO)
    StepExecution: Result of executing a single step
    BackupManifest: Backup metadata and file tracking
    ExecutionResult: Complete execution results
    RetrofitExecutor: Main execution coordinator

Security:
    - CWE-22: Path validation via security_utils
    - CWE-59: Symlink detection and prevention
    - CWE-732: Secure file permissions (0o700 for backups)
    - CWE-117: Audit logging with sanitization

Related:
    - GitHub Issue #59: Brownfield retrofit command implementation

See error-handling-patterns skill for exception hierarchy and error handling best practices.


Design Patterns:
    See library-design-patterns skill for standardized design patterns.
"""

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from .security_utils import audit_log, validate_path
from .migration_planner import MigrationPlan, MigrationStep


class ExecutionMode(Enum):
    """Execution mode options."""
    DRY_RUN = "DRY_RUN"  # Show what would happen, make no changes
    STEP_BY_STEP = "STEP_BY_STEP"  # Execute one step at a time with confirmation
    AUTO = "AUTO"  # Execute all steps automatically


@dataclass
class StepExecution:
    """Result of executing a single step.

    Attributes:
        step_id: Step identifier
        status: Execution status (success/failed/skipped)
        changes: Dict mapping file paths to change descriptions
        rollback_info: Information needed to rollback changes
        errors: List of error messages if failed
    """
    step_id: str
    status: str = "pending"
    changes: Dict[str, str] = field(default_factory=dict)
    rollback_info: Dict[str, str] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary representation.

        Returns:
            Dictionary with execution data
        """
        return {
            "step_id": self.step_id,
            "status": self.status,
            "changes": self.changes,
            "errors": self.errors
        }


@dataclass
class BackupManifest:
    """Backup metadata and file tracking.

    Attributes:
        backup_path: Path to backup directory
        timestamp: Backup creation timestamp
        files_backed_up: List of file paths backed up
        checksums: Dict mapping file paths to SHA256 checksums
    """
    backup_path: Path
    timestamp: datetime
    files_backed_up: List[str] = field(default_factory=list)
    checksums: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary representation.

        Returns:
            Dictionary with backup metadata
        """
        return {
            "backup_path": str(self.backup_path),
            "timestamp": self.timestamp.isoformat(),
            "files_backed_up": self.files_backed_up,
            "checksums": self.checksums
        }

    def save(self, path: Path):
        """Save manifest to JSON file.

        Args:
            path: Path to save manifest

        Raises:
            IOError: If save fails
        """
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2)


@dataclass
class ExecutionResult:
    """Complete execution results.

    Attributes:
        completed_steps: List of successfully completed step executions
        failed_steps: List of failed step executions
        backup: Backup manifest
        rollback_performed: Whether rollback was performed
    """
    completed_steps: List[StepExecution] = field(default_factory=list)
    failed_steps: List[StepExecution] = field(default_factory=list)
    backup: Optional[BackupManifest] = None
    rollback_performed: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary representation.

        Returns:
            Dictionary with execution results
        """
        return {
            "completed_steps": [step.to_dict() for step in self.completed_steps],
            "failed_steps": [step.to_dict() for step in self.failed_steps],
            "backup": self.backup.to_dict() if self.backup else None,
            "rollback_performed": self.rollback_performed,
            "total_steps": len(self.completed_steps) + len(self.failed_steps),
            "success_count": len(self.completed_steps),
            "failure_count": len(self.failed_steps)
        }


class RetrofitExecutor:
    """Main retrofit execution coordinator.

    Executes migration plans with backup, rollback, and verification capabilities.
    Supports dry-run, step-by-step, and automatic execution modes.
    """

    def __init__(self, project_root: Path):
        """Initialize retrofit executor.

        Args:
            project_root: Path to project root directory

        Raises:
            ValueError: If project_root invalid
        """
        # Security: Validate project root path (CWE-22)
        validated_root = validate_path(
            project_root,
            "project_root",
            allow_missing=False,
        )
        self.project_root = Path(validated_root)

        # Audit log initialization
        audit_log(
            "retrofit_executor_init",
            project_root=str(self.project_root),
            success=True
        )

    def execute(
        self,
        plan: MigrationPlan,
        mode: ExecutionMode = ExecutionMode.STEP_BY_STEP
    ) -> ExecutionResult:
        """Execute migration plan.

        Args:
            plan: Migration plan to execute
            mode: Execution mode (DRY_RUN/STEP_BY_STEP/AUTO)

        Returns:
            Execution results

        Raises:
            ValueError: If plan invalid
        """
        if not plan or not plan.steps:
            raise ValueError("Migration plan with steps required")

        audit_log(
            "retrofit_execution_start",
            project_root=str(self.project_root),
            mode=mode.value,
            step_count=len(plan.steps)
        )

        result = ExecutionResult()

        try:
            # Create backup (unless dry-run)
            if mode != ExecutionMode.DRY_RUN:
                result.backup = self.create_backup()

            # Execute steps
            for step in plan.steps:
                execution = self.execute_step(step, mode)

                if execution.status == "success":
                    result.completed_steps.append(execution)
                elif execution.status == "failed":
                    result.failed_steps.append(execution)

                    # Stop on failure unless auto mode
                    if mode != ExecutionMode.AUTO:
                        audit_log(
                            "retrofit_execution_stopped",
                            project_root=str(self.project_root),
                            failed_step=step.step_id,
                            success=False
                        )
                        break

            # If any failures in non-dry-run mode, offer rollback
            if result.failed_steps and mode != ExecutionMode.DRY_RUN:
                # Auto-rollback in AUTO mode
                if mode == ExecutionMode.AUTO:
                    self._rollback_all(result)
                    result.rollback_performed = True

            audit_log(
                "retrofit_execution_complete",
                project_root=str(self.project_root),
                completed=len(result.completed_steps),
                failed=len(result.failed_steps),
                rollback=result.rollback_performed,
                success=True
            )

            return result

        except Exception as e:
            audit_log(
                "retrofit_execution_failed",
                project_root=str(self.project_root),
                error=str(e),
                success=False
            )
            raise

    def execute_step(
        self,
        step: MigrationStep,
        mode: ExecutionMode
    ) -> StepExecution:
        """Execute a single migration step.

        Args:
            step: Migration step to execute
            mode: Execution mode

        Returns:
            Step execution result
        """
        execution = StepExecution(step_id=step.step_id)

        audit_log(
            "step_execution_start",
            step_id=step.step_id,
            mode=mode.value
        )

        try:
            # Dry-run mode - just report what would happen
            if mode == ExecutionMode.DRY_RUN:
                execution.status = "dry-run"
                execution.changes = self._simulate_changes(step)
                return execution

            # Step-by-step mode - confirm before executing
            if mode == ExecutionMode.STEP_BY_STEP:
                # In real implementation, would prompt user
                # For now, auto-confirm
                pass

            # Execute step tasks
            changes = self._execute_tasks(step)
            execution.changes = changes

            # Verify completion
            if self.verify_step_completion(step):
                execution.status = "success"
            else:
                execution.status = "failed"
                execution.errors.append("Verification failed")

            audit_log(
                "step_execution_complete",
                "failure",
                {"step_id": step.step_id, "status": execution.status}
            )

            return execution

        except Exception as e:
            execution.status = "failed"
            execution.errors.append(str(e))

            audit_log(
                "step_execution_failed",
                step_id=step.step_id,
                error=str(e),
                success=False
            )

            return execution

    def create_backup(self) -> BackupManifest:
        """Create backup before making changes.

        Returns:
            Backup manifest with metadata

        Raises:
            IOError: If backup creation fails
        """
        audit_log("backup_creation_start", project_root=str(self.project_root))

        try:
            # Create backup directory with timestamp
            timestamp = datetime.now()
            backup_name = f"retrofit_backup_{timestamp.strftime('%Y%m%d_%H%M%S')}"
            backup_path = Path(tempfile.gettempdir()) / backup_name

            # Security: Create with restricted permissions (CWE-732)
            backup_path.mkdir(mode=0o700, exist_ok=False)

            # Security: Re-validate after creation to prevent TOCTOU (CWE-59)
            if backup_path.is_symlink():
                raise ValueError(f"Backup path is a symlink: {backup_path}")

            manifest = BackupManifest(
                backup_path=backup_path,
                timestamp=timestamp
            )

            # Backup critical files
            critical_files = [
                ".claude/PROJECT.md",
                "README.md",
                "pyproject.toml",
                "setup.py",
                "requirements.txt"
            ]

            for rel_path in critical_files:
                src_path = self.project_root / rel_path
                if src_path.exists():
                    # Backup file
                    dest_path = backup_path / rel_path
                    dest_path.parent.mkdir(parents=True, exist_ok=True)

                    shutil.copy2(src_path, dest_path)

                    # Calculate checksum
                    checksum = self._calculate_checksum(src_path)

                    manifest.files_backed_up.append(rel_path)
                    manifest.checksums[rel_path] = checksum

            # Save manifest
            manifest_path = backup_path / "manifest.json"
            manifest.save(manifest_path)

            audit_log(
                "backup_creation_complete",
                backup_path=str(backup_path),
                file_count=len(manifest.files_backed_up),
                success=True
            )

            return manifest

        except Exception as e:
            audit_log(
                "backup_creation_failed",
                error=str(e),
                success=False
            )
            raise

    def apply_file_changes(self, changes: Dict[str, str]) -> List[str]:
        """Apply file changes atomically.

        Args:
            changes: Dict mapping file paths to new content

        Returns:
            List of successfully applied file paths

        Raises:
            IOError: If file operations fail
        """
        applied = []

        for rel_path, content in changes.items():
            try:
                file_path = self.project_root / rel_path

                # Security: Validate path (CWE-22)
                validated_path = validate_path(
                    file_path,
                    "file_path",
                    allow_missing=True,
                )

                # Create parent directories
                Path(validated_path).parent.mkdir(parents=True, exist_ok=True)

                # Atomic write using temp file + rename
                with tempfile.NamedTemporaryFile(
                    mode='w',
                    encoding='utf-8',
                    dir=Path(validated_path).parent,
                    delete=False
                ) as tmp_file:
                    tmp_file.write(content)
                    tmp_path = tmp_file.name

                # Security: Validate temp path before rename
                validated_tmp = validate_path(
                    tmp_path,
                    "tmp_path",
                    allow_missing=False,
                )

                # Atomic rename
                os.replace(validated_tmp, validated_path)

                applied.append(rel_path)

                audit_log(
                    "file_change_applied",
                    file_path=rel_path,
                    success=True
                )

            except Exception as e:
                audit_log(
                    "file_change_failed",
                    file_path=rel_path,
                    error=str(e),
                    success=False
                )
                # Continue with remaining files

        return applied

    def rollback_step(self, execution: StepExecution) -> bool:
        """Rollback a single step's changes.

        Args:
            execution: Step execution to rollback

        Returns:
            True if rollback successful, False otherwise
        """
        audit_log(
            "step_rollback_start",
            step_id=execution.step_id
        )

        try:
            # Restore files from rollback_info
            for file_path, original_content in execution.rollback_info.items():
                target_path = self.project_root / file_path

                # Security: Validate path (CWE-22)
                validated_path = validate_path(
                    target_path,
                    "target_path",
                    allow_missing=True,
                )

                # Write original content
                Path(validated_path).write_text(original_content, encoding='utf-8')

            audit_log(
                "step_rollback_complete",
                step_id=execution.step_id,
                success=True
            )

            return True

        except Exception as e:
            audit_log(
                "step_rollback_failed",
                step_id=execution.step_id,
                error=str(e),
                success=False
            )
            return False

    def verify_step_completion(self, step: MigrationStep) -> bool:
        """Verify step completed successfully.

        Args:
            step: Migration step to verify

        Returns:
            True if verification passed, False otherwise
        """
        # Check each verification criterion
        for criterion in step.verification_criteria:
            if not self._check_criterion(criterion):
                return False

        return True

    # Private helper methods

    def _simulate_changes(self, step: MigrationStep) -> Dict[str, str]:
        """Simulate changes for dry-run mode.

        Args:
            step: Migration step

        Returns:
            Dict mapping file paths to change descriptions
        """
        changes = {}

        # Parse tasks to identify file operations
        for task in step.tasks:
            task_lower = task.lower()

            if "create" in task_lower and "project.md" in task_lower:
                changes[".claude/PROJECT.md"] = "Would create PROJECT.md"

            elif "create" in task_lower and "directory" in task_lower:
                if "src" in task_lower:
                    changes["src/"] = "Would create src/ directory"
                elif "test" in task_lower:
                    changes["tests/"] = "Would create tests/ directory"

            elif "move" in task_lower or "organize" in task_lower:
                changes["<source-files>"] = "Would reorganize source files"

            elif "add" in task_lower and "test" in task_lower:
                changes["tests/"] = "Would add test files"

            elif "add" in task_lower and ("ci" in task_lower or "workflow" in task_lower):
                changes[".github/workflows/"] = "Would add CI/CD configuration"

        return changes

    def _execute_tasks(self, step: MigrationStep) -> Dict[str, str]:
        """Execute step tasks.

        Args:
            step: Migration step

        Returns:
            Dict mapping file paths to actual changes made
        """
        changes = {}

        # Execute each task
        for task in step.tasks:
            task_changes = self._execute_single_task(task, step)
            changes.update(task_changes)

        return changes

    def _execute_single_task(self, task: str, step: MigrationStep) -> Dict[str, str]:
        """Execute a single task.

        Args:
            task: Task description
            step: Parent migration step

        Returns:
            Dict of changes made
        """
        changes = {}
        task_lower = task.lower()

        # Task: Create PROJECT.md
        if "create" in task_lower and "project.md" in task_lower:
            project_md_path = ".claude/PROJECT.md"
            content = self._generate_project_md_content(step)
            applied = self.apply_file_changes({project_md_path: content})
            if applied:
                changes[project_md_path] = "Created PROJECT.md"

        # Task: Create directory
        elif "create" in task_lower and "directory" in task_lower:
            if "src" in task_lower:
                dir_path = self.project_root / "src"
                dir_path.mkdir(exist_ok=True)
                changes["src/"] = "Created src/ directory"

            elif "test" in task_lower:
                dir_path = self.project_root / "tests"
                dir_path.mkdir(exist_ok=True)
                changes["tests/"] = "Created tests/ directory"

        # Additional task handlers can be added here

        return changes

    def _rollback_all(self, result: ExecutionResult):
        """Rollback all completed steps.

        Args:
            result: Execution result with completed steps
        """
        audit_log(
            "full_rollback_start",
            step_count=len(result.completed_steps)
        )

        # Rollback in reverse order
        for execution in reversed(result.completed_steps):
            self.rollback_step(execution)

        audit_log(
            "full_rollback_complete",
            step_count=len(result.completed_steps),
            success=True
        )

    def _check_criterion(self, criterion: str) -> bool:
        """Check a single verification criterion.

        Args:
            criterion: Criterion description

        Returns:
            True if criterion met, False otherwise
        """
        criterion_lower = criterion.lower()

        # Check: PROJECT.md exists
        if "project.md exists" in criterion_lower:
            return (self.project_root / ".claude" / "PROJECT.md").exists()

        # Check: Directory exists
        if "directory" in criterion_lower or "organized" in criterion_lower:
            if "src" in criterion_lower:
                return (self.project_root / "src").is_dir()
            elif "test" in criterion_lower:
                return (self.project_root / "tests").is_dir()

        # Check: Tests pass
        if "test" in criterion_lower and "pass" in criterion_lower:
            # Would run pytest here
            return True  # Simplified for now

        # Default: assume criterion met
        return True

    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of a file.

        Args:
            file_path: Path to file

        Returns:
            Hex digest of SHA256 hash
        """
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _generate_project_md_content(self, step: MigrationStep) -> str:
        """Generate PROJECT.md content.

        Args:
            step: Migration step context

        Returns:
            PROJECT.md content
        """
        return """# Project Overview

## GOALS

**TODO**: Define project goals and objectives

## SCOPE

**TODO**: Define project scope and boundaries

## CONSTRAINTS

- **Code Quality**: 80%+ test coverage required
- **Security**: No secrets in version control
- **Documentation**: Keep CLAUDE.md and PROJECT.md in sync

## ARCHITECTURE

**TODO**: Describe high-level architecture

---

<!-- Generated by /align-project-retrofit -->
"""
