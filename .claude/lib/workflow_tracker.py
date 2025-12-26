#!/usr/bin/env python3
"""
Workflow State Tracking for Preference Learning - Issue #155

Tracks quality workflow steps taken/skipped, detects user corrections,
and learns preferences over time to improve Claude's workflow decisions.

Key Features:
- Step tracking: Records which quality steps were taken vs skipped
- Correction detection: Parses user feedback for improvement signals
- Preference learning: Derives preferences from patterns over time
- Privacy-preserving: Local storage only, no cloud sync
- Atomic persistence: Safe concurrent access with file locking

State File Location:
- ~/.autonomous-dev/workflow_state.json (user-level preferences)

Usage:
    from workflow_tracker import WorkflowTracker, detect_correction

    # Track workflow steps
    tracker = WorkflowTracker()
    tracker.start_session()
    tracker.record_step("research", taken=True)
    tracker.record_step("testing", taken=False, reason="quick fix")
    tracker.save()

    # Detect corrections in user feedback
    correction = detect_correction("you should have researched first")
    if correction:
        tracker.record_correction(correction["step"], correction["text"])

    # Get learned preferences
    prefs = tracker.get_preferences()
    recommended = tracker.get_recommended_steps()
"""

import json
import os
import re
import tempfile
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# ============================================================================
# Configuration
# ============================================================================

# Maximum sessions to keep (prevents unbounded growth)
MAX_SESSIONS = 50

# Correction threshold to emphasize a step
CORRECTION_THRESHOLD = 3

# Preference decay period (days)
PREFERENCE_DECAY_DAYS = 30

# Default state file location
DEFAULT_STATE_FILE = Path.home() / ".autonomous-dev" / "workflow_state.json"

# Default state structure
DEFAULT_WORKFLOW_STATE: Dict[str, Any] = {
    "version": "1.0",
    "sessions": [],
    "preferences": {
        "emphasized_steps": {},  # step -> correction_count
        "task_type_preferences": {},  # task_type -> {step -> priority}
    },
    "corrections": [],  # List of correction records
    "metadata": {
        "created_at": None,
        "updated_at": None,
    },
}

# Quality workflow steps
WORKFLOW_STEPS = [
    "alignment",  # PROJECT.md alignment check
    "research",  # Codebase/web research
    "planning",  # Implementation planning
    "testing",  # TDD tests
    "implementation",  # Code implementation
    "review",  # Code review
    "security",  # Security audit
    "documentation",  # Doc updates
]


# ============================================================================
# Correction Detection Patterns
# ============================================================================

# Patterns to detect user corrections
# Each pattern maps to a step extraction function
CORRECTION_PATTERNS = [
    # "you should have X"
    (r"\byou\s+should\s+have\s+(\w+)", "should_have"),
    # "need to X first"
    (r"\bneed\s+to\s+(\w+)", "need_to"),
    # "forgot to X"
    (r"\bforgot\s+to\s+(\w+)", "forgot"),
    # "always should X"
    (r"\bshould\s+always\s+(\w+)", "always_should"),
    # "didn't X"
    (r"\bdidn'?t\s+(\w+)", "didnt"),
    # "should X before"
    (r"\bshould\s+(\w+)\s+(?:first|before)", "should_before"),
]

# Step keyword mapping
STEP_KEYWORDS = {
    "research": ["research", "searched", "looked", "checked", "investigated"],
    "testing": ["test", "tested", "tests", "tdd", "unittest", "write"],  # "write tests"
    "planning": ["plan", "planned", "planning", "design"],
    "review": ["review", "reviewed", "check", "checked"],
    "security": ["security", "secure", "audit", "audited", "vulnerability", "run"],  # "run security"
    "documentation": ["document", "documented", "docs", "readme"],
    "alignment": ["align", "aligned", "project", "goals"],
    "implementation": ["implement", "implemented", "code", "coded"],
}


def _extract_step_from_keyword(keyword: str) -> Optional[str]:
    """Extract workflow step from a keyword."""
    keyword_lower = keyword.lower()
    for step, keywords in STEP_KEYWORDS.items():
        for kw in keywords:
            if kw in keyword_lower or keyword_lower in kw:
                return step
    return None


def detect_correction(user_input: Optional[str]) -> Optional[Dict[str, str]]:
    """
    Detect if user input contains a correction signal.

    Looks for patterns like:
    - "you should have researched first"
    - "need to write tests before implementing"
    - "forgot to check for duplicates"
    - "should always run security checks"

    Args:
        user_input: User's message text

    Returns:
        Dict with 'step' and 'text' if correction detected, None otherwise

    Example:
        >>> detect_correction("you should have researched first")
        {'step': 'research', 'text': 'you should have researched first', 'pattern': 'should_have'}
    """
    if not user_input:
        return None

    text = user_input.lower()

    for pattern, pattern_name in CORRECTION_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            keyword = match.group(1)
            step = _extract_step_from_keyword(keyword)
            if step:
                return {
                    "step": step,
                    "text": user_input,
                    "pattern": pattern_name,
                    "keyword": keyword,
                }

    return None


# ============================================================================
# Session Management
# ============================================================================

def create_session() -> Dict[str, Any]:
    """
    Create a new workflow session record.

    Returns:
        Dict with session_id, started_at timestamp, and empty steps list

    Example:
        >>> session = create_session()
        >>> session["session_id"]
        'abc123-def456-...'
    """
    return {
        "session_id": str(uuid.uuid4()),
        "started_at": datetime.utcnow().isoformat() + "Z",
        "ended_at": None,
        "steps": [],
        "task_type": None,  # feature, bugfix, docs, etc.
    }


# ============================================================================
# Workflow Tracker Class
# ============================================================================

class WorkflowTracker:
    """
    Tracks workflow steps, corrections, and learned preferences.

    Thread-safe with file locking for concurrent access.
    Uses atomic writes to prevent state corruption.

    Attributes:
        state_file: Path to workflow state JSON file
        _state: In-memory state dict
        _current_session: Current active session dict
        _lock: Thread lock for concurrent access
    """

    def __init__(self, state_file: Optional[Path] = None):
        """
        Initialize workflow tracker.

        Args:
            state_file: Optional custom state file path (default: ~/.autonomous-dev/workflow_state.json)
        """
        self.state_file = state_file or DEFAULT_STATE_FILE
        self._lock = threading.RLock()
        self._state = self._load_state()
        self._current_session: Optional[Dict[str, Any]] = None

    def _load_state(self) -> Dict[str, Any]:
        """Load state from file or return defaults."""
        try:
            if self.state_file.exists():
                content = self.state_file.read_text()
                state = json.loads(content)
                # Ensure all required keys exist
                for key in DEFAULT_WORKFLOW_STATE:
                    if key not in state:
                        state[key] = DEFAULT_WORKFLOW_STATE[key]
                return state
        except (json.JSONDecodeError, OSError) as e:
            # Corrupted or unreadable - use defaults
            pass

        # Return copy of defaults
        state = json.loads(json.dumps(DEFAULT_WORKFLOW_STATE))
        state["metadata"]["created_at"] = datetime.utcnow().isoformat() + "Z"
        return state

    def save(self) -> bool:
        """
        Save state to file using atomic write.

        Returns:
            True if save succeeded, False otherwise
        """
        with self._lock:
            try:
                # Ensure directory exists
                self.state_file.parent.mkdir(parents=True, exist_ok=True)

                # Update timestamp
                self._state["metadata"]["updated_at"] = datetime.utcnow().isoformat() + "Z"

                # Atomic write
                fd, temp_path = tempfile.mkstemp(
                    dir=self.state_file.parent,
                    suffix=".tmp",
                )
                try:
                    with os.fdopen(fd, "w") as f:
                        json.dump(self._state, f, indent=2)
                    os.replace(temp_path, self.state_file)
                    return True
                except Exception:
                    # Clean up temp file on error
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass
                    raise
            except OSError as e:
                return False

    # ========================================================================
    # Session Management
    # ========================================================================

    def start_session(self, task_type: Optional[str] = None) -> str:
        """
        Start a new workflow session.

        Args:
            task_type: Optional task type (feature, bugfix, docs, etc.)

        Returns:
            Session ID
        """
        with self._lock:
            self._current_session = create_session()
            self._current_session["task_type"] = task_type
            return self._current_session["session_id"]

    def end_session(self) -> None:
        """End current session and add to history."""
        with self._lock:
            if self._current_session:
                self._current_session["ended_at"] = datetime.utcnow().isoformat() + "Z"
                self._state["sessions"].append(self._current_session)

                # Trim to max sessions
                if len(self._state["sessions"]) > MAX_SESSIONS:
                    self._state["sessions"] = self._state["sessions"][-MAX_SESSIONS:]

                self._current_session = None
                self.save()

    def get_sessions(self) -> List[Dict[str, Any]]:
        """Get all recorded sessions."""
        return self._state.get("sessions", [])

    def get_current_session_steps(self) -> List[Dict[str, Any]]:
        """Get steps from current session."""
        if self._current_session:
            return self._current_session.get("steps", [])
        return []

    # ========================================================================
    # Step Tracking
    # ========================================================================

    def record_step(
        self,
        step: str,
        taken: bool,
        reason: Optional[str] = None,
    ) -> None:
        """
        Record a workflow step.

        Args:
            step: Step name (research, testing, etc.)
            taken: True if step was taken, False if skipped
            reason: Optional reason for skipping
        """
        with self._lock:
            if not self._current_session:
                self.start_session()

            step_record = {
                "step": step,
                "taken": taken,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
            if reason:
                step_record["reason"] = reason

            self._current_session["steps"].append(step_record)

    # ========================================================================
    # Correction Tracking
    # ========================================================================

    def record_correction(
        self,
        step: str,
        text: str,
        task_type: Optional[str] = None,
    ) -> None:
        """
        Record a user correction.

        Args:
            step: Step that was corrected (research, testing, etc.)
            text: Original user text
            task_type: Optional task type for context
        """
        with self._lock:
            correction = {
                "step": step,
                "text": text,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "task_type": task_type,
            }
            self._state["corrections"].append(correction)

            # Update emphasized steps
            emphasized = self._state["preferences"].get("emphasized_steps", {})
            emphasized[step] = emphasized.get(step, 0) + 1
            self._state["preferences"]["emphasized_steps"] = emphasized

            # Update task-type preferences if provided
            if task_type:
                task_prefs = self._state["preferences"].get("task_type_preferences", {})
                if task_type not in task_prefs:
                    task_prefs[task_type] = {}
                task_prefs[task_type][step] = task_prefs[task_type].get(step, 0) + 1
                self._state["preferences"]["task_type_preferences"] = task_prefs

            self.save()

    def get_corrections(self) -> List[Dict[str, Any]]:
        """Get all recorded corrections."""
        return self._state.get("corrections", [])

    # ========================================================================
    # Preference Learning
    # ========================================================================

    def get_preferences(self) -> Dict[str, Any]:
        """Get learned preferences."""
        return self._state.get("preferences", {})

    def get_recommended_steps(self, task_type: Optional[str] = None) -> List[str]:
        """
        Get recommended workflow steps based on preferences.

        Steps with corrections above threshold are emphasized.

        Args:
            task_type: Optional task type for context-specific recommendations

        Returns:
            List of recommended step names in priority order
        """
        emphasized = self._state["preferences"].get("emphasized_steps", {})

        # Get steps above correction threshold
        high_priority = [
            step for step, count in emphasized.items()
            if count >= CORRECTION_THRESHOLD
        ]

        # Add task-type specific steps if available
        if task_type:
            task_prefs = self._state["preferences"].get("task_type_preferences", {})
            task_steps = task_prefs.get(task_type, {})
            for step, count in task_steps.items():
                if count >= CORRECTION_THRESHOLD and step not in high_priority:
                    high_priority.append(step)

        # Return in priority order (most corrections first)
        return sorted(
            high_priority,
            key=lambda s: emphasized.get(s, 0),
            reverse=True,
        )

    def apply_preference_decay(self) -> None:
        """
        Apply time-based decay to preferences.

        Reduces correction counts for old corrections to allow
        preferences to evolve over time.
        """
        with self._lock:
            cutoff = datetime.utcnow() - timedelta(days=PREFERENCE_DECAY_DAYS)
            cutoff_str = cutoff.isoformat() + "Z"

            # Filter recent corrections
            recent = [
                c for c in self._state.get("corrections", [])
                if c.get("timestamp", "") >= cutoff_str
            ]

            # Rebuild emphasized steps from recent corrections only
            emphasized = {}
            for correction in recent:
                step = correction.get("step")
                if step:
                    emphasized[step] = emphasized.get(step, 0) + 1

            self._state["preferences"]["emphasized_steps"] = emphasized
            self._state["corrections"] = recent

            self.save()


# ============================================================================
# CLI Entry Point
# ============================================================================

def main():
    """CLI entry point for testing."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python workflow_tracker.py <command> [args]")
        print("Commands:")
        print("  detect <text>     - Detect correction in text")
        print("  preferences       - Show learned preferences")
        print("  sessions          - Show session count")
        sys.exit(1)

    command = sys.argv[1]

    if command == "detect":
        text = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        result = detect_correction(text)
        if result:
            print(f"Correction detected:")
            print(f"  Step: {result['step']}")
            print(f"  Pattern: {result['pattern']}")
        else:
            print("No correction detected")

    elif command == "preferences":
        tracker = WorkflowTracker()
        prefs = tracker.get_preferences()
        print("Learned preferences:")
        print(json.dumps(prefs, indent=2))

    elif command == "sessions":
        tracker = WorkflowTracker()
        sessions = tracker.get_sessions()
        print(f"Sessions recorded: {len(sessions)}")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
