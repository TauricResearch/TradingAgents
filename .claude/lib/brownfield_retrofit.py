#!/usr/bin/env python3
"""
Brownfield Retrofit - Core state management and phase coordination

This module provides the main coordinator for brownfield project adoption:
- 5-phase retrofit workflow (Analyze → Assess → Plan → Execute → Verify)
- State persistence and recovery
- Phase prerequisite validation
- Secure state file management (0o600 permissions)
- Backup and rollback support

Phases:
1. ANALYZE: Tech stack detection, file organization analysis
2. ASSESS: PROJECT.md generation, 12-Factor scoring, gap identification
3. PLAN: Migration step generation, effort estimation
4. EXECUTE: Safe file modifications with backup/rollback
5. VERIFY: Compliance validation, test suite execution

Security:
- State file permissions: 0o600 (user-only)
- All paths validated via security_utils.validate_path()
- Audit logging for all operations

Relevant Skills:
- project-alignment-validation: Alignment checklist for retrofit validation

Usage:
    from brownfield_retrofit import BrownfieldRetrofit, RetrofitPhase

    # Initialize
    retrofit = BrownfieldRetrofit(project_root="/path/to/project")

    # Check status
    status = retrofit.get_phase_status()

    # Execute phase
    retrofit.execute_phase(RetrofitPhase.ANALYZE)

Date: 2025-11-11
Feature: /align-project-retrofit command
Agent: implementer


Design Patterns:
    See library-design-patterns skill for standardized design patterns.
    See api-integration-patterns skill for standardized design patterns.
"""

import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from plugins.autonomous_dev.lib import security_utils


# Exception hierarchy pattern from error-handling-patterns skill:
# BaseException -> Exception -> AutonomousDevError -> DomainError(BaseException) -> SpecificError
class StateError(Exception):
    """

    See error-handling-patterns skill for exception hierarchy and error handling best practices.

    Exception raised for state management errors."""
    pass


class RetrofitPhase(Enum):
    """Retrofit workflow phases."""
    NOT_STARTED = "NOT_STARTED"
    ANALYZE = "ANALYZE"
    ASSESS = "ASSESS"
    PLAN = "PLAN"
    EXECUTE = "EXECUTE"
    VERIFY = "VERIFY"
    COMPLETE = "COMPLETE"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "RetrofitPhase":
        """Convert string to RetrofitPhase enum."""
        try:
            return cls[value]
        except KeyError:
            raise ValueError(f"Invalid phase: {value}")


# Phase dependency chain
PHASE_ORDER = [
    RetrofitPhase.NOT_STARTED,
    RetrofitPhase.ANALYZE,
    RetrofitPhase.ASSESS,
    RetrofitPhase.PLAN,
    RetrofitPhase.EXECUTE,
    RetrofitPhase.VERIFY,
    RetrofitPhase.COMPLETE,
]

# Phase prerequisites
PHASE_PREREQUISITES: Dict[RetrofitPhase, List[RetrofitPhase]] = {
    RetrofitPhase.NOT_STARTED: [],
    RetrofitPhase.ANALYZE: [],
    RetrofitPhase.ASSESS: [RetrofitPhase.ANALYZE],
    RetrofitPhase.PLAN: [RetrofitPhase.ANALYZE, RetrofitPhase.ASSESS],
    RetrofitPhase.EXECUTE: [RetrofitPhase.ANALYZE, RetrofitPhase.ASSESS, RetrofitPhase.PLAN],
    RetrofitPhase.VERIFY: [
        RetrofitPhase.ANALYZE,
        RetrofitPhase.ASSESS,
        RetrofitPhase.PLAN,
        RetrofitPhase.EXECUTE,
    ],
    RetrofitPhase.COMPLETE: [
        RetrofitPhase.ANALYZE,
        RetrofitPhase.ASSESS,
        RetrofitPhase.PLAN,
        RetrofitPhase.EXECUTE,
        RetrofitPhase.VERIFY,
    ],
}


@dataclass
class RetrofitState:
    """State container for retrofit workflow.

    Attributes:
        current_phase: Current workflow phase
        completed_phases: List of completed phases
        analysis_report: Phase 1 analysis results
        assessment_report: Phase 2 assessment results
        migration_plan: Phase 3 migration plan
        execution_results: Phase 4 execution results
        verification_report: Phase 5 verification results
        backup_path: Path to backup directory (if created)
        metadata: Additional metadata (timestamps, etc.)
    """

    current_phase: RetrofitPhase = RetrofitPhase.NOT_STARTED
    completed_phases: List[RetrofitPhase] = field(default_factory=list)
    analysis_report: Optional[Dict[str, Any]] = None
    assessment_report: Optional[Dict[str, Any]] = None
    migration_plan: Optional[Dict[str, Any]] = None
    execution_results: Optional[Dict[str, Any]] = None
    verification_report: Optional[Dict[str, Any]] = None
    backup_path: Optional[Path] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize metadata with timestamps."""
        if "created_at" not in self.metadata:
            self.metadata["created_at"] = datetime.now().isoformat()
        self.metadata["updated_at"] = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state to dictionary.

        Returns:
            Dictionary representation of state
        """
        return {
            "current_phase": self.current_phase.value,
            "completed_phases": [phase.value for phase in self.completed_phases],
            "analysis_report": self.analysis_report,
            "assessment_report": self.assessment_report,
            "migration_plan": self.migration_plan,
            "execution_results": self.execution_results,
            "verification_report": self.verification_report,
            "backup_path": str(self.backup_path) if self.backup_path else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RetrofitState":
        """Deserialize state from dictionary.

        Args:
            data: Dictionary representation of state

        Returns:
            RetrofitState instance
        """
        return cls(
            current_phase=RetrofitPhase.from_string(data["current_phase"]),
            completed_phases=[
                RetrofitPhase.from_string(phase) for phase in data.get("completed_phases", [])
            ],
            analysis_report=data.get("analysis_report"),
            assessment_report=data.get("assessment_report"),
            migration_plan=data.get("migration_plan"),
            execution_results=data.get("execution_results"),
            verification_report=data.get("verification_report"),
            backup_path=Path(data["backup_path"]) if data.get("backup_path") else None,
            metadata=data.get("metadata", {}),
        )

    def mark_phase_complete(self, phase: RetrofitPhase) -> None:
        """Mark phase as complete and advance to next phase.

        Args:
            phase: Phase to mark as complete
        """
        if phase not in self.completed_phases:
            self.completed_phases.append(phase)

        # Advance to next phase (use phase parameter, not current_phase)
        phase_index = PHASE_ORDER.index(phase)
        if phase_index < len(PHASE_ORDER) - 1:
            self.current_phase = PHASE_ORDER[phase_index + 1]

        self.metadata["updated_at"] = datetime.now().isoformat()

    def can_execute_phase(self, phase: RetrofitPhase) -> bool:
        """Check if phase can be executed (prerequisites met).

        Args:
            phase: Phase to check

        Returns:
            True if prerequisites met, False otherwise
        """
        prerequisites = PHASE_PREREQUISITES.get(phase, [])
        return all(prereq in self.completed_phases for prereq in prerequisites)


class BrownfieldRetrofit:
    """Main coordinator for brownfield project retrofit workflow.

    This class manages the 5-phase retrofit workflow:
    1. ANALYZE: Tech stack detection and metrics
    2. ASSESS: PROJECT.md generation and gap analysis
    3. PLAN: Migration step generation and estimation
    4. EXECUTE: Safe file modifications with backup
    5. VERIFY: Compliance validation and testing

    Attributes:
        project_root: Path to project root directory
        state: Current workflow state
        state_dir: Path to .retrofit directory
        state_file: Path to state.json file
    """

    STATE_DIR = ".retrofit"
    STATE_FILE = "state.json"
    STATE_PERMISSIONS = 0o600  # User read/write only

    def __init__(self, project_root: Path):
        """Initialize retrofit coordinator.

        Args:
            project_root: Path to project root directory

        Raises:
            ValueError: If project_root validation fails
        """
        # Validate project root
        security_utils.validate_path(
            str(project_root),
            purpose="brownfield retrofit project root",
            allow_missing=False,
        )
        self.project_root = Path(project_root).resolve()

        # Initialize state directory
        self.state_dir = self.project_root / self.STATE_DIR
        self.state_file = self.state_dir / self.STATE_FILE

        # Create state directory if missing
        self._ensure_state_directory()

        # Initialize state
        self.state = self.load_state()

        # Audit log
        security_utils.audit_log(
            "brownfield_retrofit_init",
            "success",
            {
                "project_root": str(self.project_root),
                "state_dir": str(self.state_dir),
            },
        )

    def _ensure_state_directory(self) -> None:
        """Create state directory if it doesn't exist.

        Raises:
            StateError: If directory creation fails
        """
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            raise StateError(f"Permission denied: Cannot create state directory: {e}")
        except Exception as e:
            raise StateError(f"Failed to create state directory: {e}")

    def load_state(self) -> RetrofitState:
        """Load state from state file or create new state.

        Returns:
            RetrofitState instance

        Raises:
            StateError: If state loading fails
        """
        if not self.state_file.exists():
            # Create new state
            return RetrofitState()

        try:
            # Read state file
            state_data = json.loads(self.state_file.read_text())
            state = RetrofitState.from_dict(state_data)

            security_utils.audit_log(
                "brownfield_state_loaded",
                "success",
                {
                    "state_file": str(self.state_file),
                    "current_phase": state.current_phase.value,
                },
            )

            return state

        except json.JSONDecodeError as e:
            # Corrupted state file - create backup and return new state
            backup_file = self.state_file.with_suffix(".json.backup")
            shutil.copy2(self.state_file, backup_file)

            security_utils.audit_log(
                "brownfield_state_corrupted",
                "warning",
                {
                    "state_file": str(self.state_file),
                    "backup_file": str(backup_file),
                    "error": str(e),
                },
            )

            return RetrofitState()

        except Exception as e:
            raise StateError(f"Failed to load state: {e}")

    def save_state(self) -> None:
        """Save current state to state file.

        Raises:
            StateError: If state saving fails
        """
        try:
            # Update timestamp
            self.state.metadata["updated_at"] = datetime.now().isoformat()

            # Serialize state
            state_data = self.state.to_dict()
            state_json = json.dumps(state_data, indent=2)

            # Write to state file
            self.state_file.write_text(state_json)

            # Set secure permissions
            self.state_file.chmod(self.STATE_PERMISSIONS)

            security_utils.audit_log(
                "brownfield_state_saved",
                "success",
                {
                    "state_file": str(self.state_file),
                    "current_phase": self.state.current_phase.value,
                },
            )

        except PermissionError as e:
            raise StateError(f"Permission denied: Cannot save state file: {e}")
        except Exception as e:
            raise StateError(f"Failed to save state: {e}")

    def update_state(self, **kwargs) -> None:
        """Update state attributes and save automatically.

        Args:
            **kwargs: State attributes to update

        Raises:
            StateError: If state update fails
        """
        for key, value in kwargs.items():
            if hasattr(self.state, key):
                # Handle phase enum conversion
                if key == "current_phase" and isinstance(value, str):
                    value = RetrofitPhase.from_string(value)
                elif key == "completed_phases" and value and isinstance(value[0], str):
                    value = [RetrofitPhase.from_string(p) for p in value]

                setattr(self.state, key, value)

        self.save_state()

    def get_phase_status(self) -> Dict[str, Any]:
        """Get current phase status.

        Returns:
            Dictionary with phase status information
        """
        completed_phase_values = [phase.value for phase in self.state.completed_phases]
        current_index = PHASE_ORDER.index(self.state.current_phase)
        # Remaining phases excludes NOT_STARTED and COMPLETE
        remaining_phases = [
            phase.value
            for phase in PHASE_ORDER[current_index + 1 :]
            if phase not in (RetrofitPhase.NOT_STARTED, RetrofitPhase.COMPLETE)
        ]

        return {
            "current_phase": self.state.current_phase.value,
            "completed_phases": completed_phase_values,
            "remaining_phases": remaining_phases,
            "total_phases": len(PHASE_ORDER) - 2,  # Exclude NOT_STARTED and COMPLETE
            "progress_percent": len(completed_phase_values) / (len(PHASE_ORDER) - 2) * 100,
        }

    def execute_phase(self, phase: RetrofitPhase) -> None:
        """Execute a specific phase.

        Args:
            phase: Phase to execute

        Raises:
            StateError: If prerequisites not met
        """
        if not self.state.can_execute_phase(phase):
            raise StateError(
                f"Prerequisites not met for phase {phase.value}. "
                f"Required phases: {[p.value for p in PHASE_PREREQUISITES[phase]]}"
            )

        security_utils.audit_log(
            "brownfield_phase_execute",
            "success",
            {
                "phase": phase.value,
                "project_root": str(self.project_root),
            },
        )

    def complete_phase(self, phase: RetrofitPhase) -> None:
        """Mark phase as complete and advance workflow.

        Args:
            phase: Phase to mark as complete
        """
        self.state.mark_phase_complete(phase)
        self.save_state()

        security_utils.audit_log(
            "brownfield_phase_complete",
            "success",
            {
                "phase": phase.value,
                "next_phase": self.state.current_phase.value,
            },
        )

    def reset(self) -> None:
        """Reset workflow to initial state.

        This clears all state and starts from scratch.
        """
        self.state = RetrofitState()
        self.save_state()

        security_utils.audit_log(
            "brownfield_workflow_reset",
            "success",
            {"project_root": str(self.project_root)},
        )


# Convenience function for external use
def create_retrofit_instance(project_root: Path) -> BrownfieldRetrofit:
    """Create a BrownfieldRetrofit instance.

    Args:
        project_root: Path to project root directory

    Returns:
        BrownfieldRetrofit instance
    """
    return BrownfieldRetrofit(project_root=project_root)
