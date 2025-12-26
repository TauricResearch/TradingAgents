#!/usr/bin/env python3
"""
Unified Session Tracker Hook - Dispatcher for SubagentStop Session Tracking

Consolidates SubagentStop session tracking hooks:
- session_tracker.py (basic session logging)
- log_agent_completion.py (structured pipeline tracking)
- auto_update_project_progress.py (PROJECT.md progress updates)

Hook: SubagentStop (runs when a subagent completes)

Environment Variables (opt-in/opt-out):
    TRACK_SESSIONS=true/false (default: true)
    TRACK_PIPELINE=true/false (default: true)
    AUTO_UPDATE_PROGRESS=true/false (default: false)

Environment Variables (provided by Claude Code):
    CLAUDE_AGENT_NAME - Name of the subagent that completed
    CLAUDE_AGENT_OUTPUT - Output from the subagent
    CLAUDE_AGENT_STATUS - Status: "success" or "error"

Exit codes:
    0: Always (non-blocking hook)

Usage:
    # As SubagentStop hook (automatic)
    CLAUDE_AGENT_NAME=researcher CLAUDE_AGENT_STATUS=success python unified_session_tracker.py
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional


# ============================================================================
# Dynamic Library Discovery
# ============================================================================

def find_lib_dir() -> Optional[Path]:
    """
    Find the lib directory dynamically.

    Searches:
    1. Relative to this file: ../lib
    2. In project root: plugins/autonomous-dev/lib
    3. In global install: ~/.autonomous-dev/lib

    Returns:
        Path to lib directory or None if not found
    """
    candidates = [
        Path(__file__).parent.parent / "lib",  # Relative to hooks/
        Path.cwd() / "plugins" / "autonomous-dev" / "lib",  # Project root
        Path.home() / ".autonomous-dev" / "lib",  # Global install
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


# Add lib to path
LIB_DIR = find_lib_dir()
if LIB_DIR:
    sys.path.insert(0, str(LIB_DIR))

# Optional imports with graceful fallback
try:
    from agent_tracker import AgentTracker
    HAS_AGENT_TRACKER = True
except ImportError:
    HAS_AGENT_TRACKER = False

try:
    from project_md_updater import ProjectMdUpdater
    HAS_PROJECT_UPDATER = True
except ImportError:
    HAS_PROJECT_UPDATER = False


# ============================================================================
# Configuration
# ============================================================================

# Check configuration from environment
TRACK_SESSIONS = os.environ.get("TRACK_SESSIONS", "true").lower() == "true"
TRACK_PIPELINE = os.environ.get("TRACK_PIPELINE", "true").lower() == "true"
AUTO_UPDATE_PROGRESS = os.environ.get("AUTO_UPDATE_PROGRESS", "false").lower() == "true"


# ============================================================================
# Session Logging (Basic)
# ============================================================================

class SessionTracker:
    """Basic session logging to docs/sessions/."""

    def __init__(self):
        """Initialize session tracker."""
        self.session_dir = Path("docs/sessions")
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Find or create session file for today
        today = datetime.now().strftime("%Y%m%d")
        session_files = list(self.session_dir.glob(f"{today}-*.md"))

        if session_files:
            # Use most recent session file from today
            self.session_file = sorted(session_files)[-1]
        else:
            # Create new session file
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            self.session_file = self.session_dir / f"{timestamp}-session.md"

            # Initialize with header
            self.session_file.write_text(
                f"# Session {timestamp}\n\n"
                f"**Started**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"---\n\n"
            )

    def log(self, agent_name: str, message: str) -> None:
        """
        Log agent action to session file.

        Args:
            agent_name: Name of agent
            message: Message to log
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"**{timestamp} - {agent_name}**: {message}\n\n"

        # Append to session file
        with open(self.session_file, "a") as f:
            f.write(entry)


def track_basic_session(agent_name: str, message: str) -> bool:
    """
    Track agent completion in basic session log.

    Args:
        agent_name: Name of agent
        message: Completion message

    Returns:
        True if logged successfully, False otherwise
    """
    if not TRACK_SESSIONS:
        return False

    try:
        tracker = SessionTracker()
        tracker.log(agent_name, message)
        return True
    except Exception:
        return False


# ============================================================================
# Pipeline Tracking (Structured)
# ============================================================================

def extract_tools_from_output(output: str) -> Optional[List[str]]:
    """
    Best-effort extraction of tools used from agent output.

    Args:
        output: Agent output text

    Returns:
        List of tool names or None if no tools detected
    """
    tools = []

    # Common tool mentions in output
    if "Read tool" in output or "reading file" in output.lower():
        tools.append("Read")
    if "Write tool" in output or "writing file" in output.lower():
        tools.append("Write")
    if "Edit tool" in output or "editing file" in output.lower():
        tools.append("Edit")
    if "Bash tool" in output or "running command" in output.lower():
        tools.append("Bash")
    if "Grep tool" in output or "searching" in output.lower():
        tools.append("Grep")
    if "WebSearch" in output or "web search" in output.lower():
        tools.append("WebSearch")
    if "WebFetch" in output or "fetching URL" in output.lower():
        tools.append("WebFetch")
    if "Task tool" in output or "invoking agent" in output.lower():
        tools.append("Task")

    return tools if tools else None


def track_pipeline_completion(agent_name: str, agent_output: str, agent_status: str) -> bool:
    """
    Track agent completion in structured pipeline.

    Args:
        agent_name: Name of agent
        agent_output: Agent output text
        agent_status: "success" or "error"

    Returns:
        True if tracked successfully, False otherwise
    """
    if not TRACK_PIPELINE or not HAS_AGENT_TRACKER:
        return False

    try:
        tracker = AgentTracker()

        if agent_status == "success":
            # Extract tools used
            tools = extract_tools_from_output(agent_output)

            # Create summary (first 100 chars)
            summary = agent_output[:100].replace("\n", " ") if agent_output else "Completed"

            # Auto-track agent first (idempotent)
            tracker.auto_track_from_environment(message=summary)

            # Complete the agent
            tracker.complete_agent(agent_name, summary, tools)
        else:
            # Extract error message
            error_msg = agent_output[:100].replace("\n", " ") if agent_output else "Failed"

            # Auto-track even for failures
            tracker.auto_track_from_environment(message=error_msg)

            # Fail the agent
            tracker.fail_agent(agent_name, error_msg)

        return True
    except Exception:
        return False


# ============================================================================
# PROJECT.md Progress Updates
# ============================================================================

def should_trigger_progress_update(agent_name: str) -> bool:
    """
    Check if PROJECT.md progress update should trigger.

    Only triggers for doc-master (last agent in pipeline).

    Args:
        agent_name: Name of agent that completed

    Returns:
        True if should trigger, False otherwise
    """
    return agent_name == "doc-master"


def check_pipeline_complete() -> bool:
    """
    Check if all 7 agents in pipeline completed.

    Returns:
        True if pipeline complete, False otherwise
    """
    if not HAS_AGENT_TRACKER:
        return False

    try:
        # Check latest session file
        session_dir = Path("docs/sessions")
        session_files = list(session_dir.glob("*-pipeline.json"))

        if not session_files:
            return False

        # Read latest session
        latest_session = sorted(session_files)[-1]
        session_data = json.loads(latest_session.read_text())

        # Check if all expected agents completed
        # Issue #147: Consolidated to only active agents in /auto-implement pipeline
        expected_agents = [
            "researcher-local",
            "planner",
            "test-master",
            "implementer",
            "reviewer",
            "security-auditor",
            "doc-master"
        ]

        completed_agents = {
            entry["agent"] for entry in session_data.get("agents", [])
            if entry.get("status") == "completed"
        }

        return set(expected_agents).issubset(completed_agents)
    except Exception:
        return False


def update_project_progress() -> bool:
    """
    Update PROJECT.md with goal progress.

    Returns:
        True if updated successfully, False otherwise
    """
    if not AUTO_UPDATE_PROGRESS or not HAS_PROJECT_UPDATER:
        return False

    try:
        # Note: Progress tracking feature deprioritized (Issue #147: Agent consolidation)
        # Would update PROJECT.md via ProjectMdUpdater if implemented.
        return False
    except Exception:
        return False


# ============================================================================
# Main Hook Entry Point
# ============================================================================

def main() -> int:
    """
    Main hook entry point.

    Reads agent info from environment, dispatches tracking.

    Returns:
        Always 0 (non-blocking hook)
    """
    # Get agent info from environment (provided by Claude Code)
    agent_name = os.environ.get("CLAUDE_AGENT_NAME", "unknown")
    agent_output = os.environ.get("CLAUDE_AGENT_OUTPUT", "")
    agent_status = os.environ.get("CLAUDE_AGENT_STATUS", "success")

    # Create summary message
    summary = agent_output[:100].replace("\n", " ") if agent_output else "Completed"

    # Dispatch tracking (all are non-blocking)
    try:
        # Basic session logging
        track_basic_session(agent_name, summary)

        # Structured pipeline tracking
        track_pipeline_completion(agent_name, agent_output, agent_status)

        # PROJECT.md progress updates (only for doc-master)
        if should_trigger_progress_update(agent_name) and check_pipeline_complete():
            update_project_progress()
    except Exception:
        # Graceful degradation - never block workflow
        pass

    # Always succeed (non-blocking hook)
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SubagentStop"
        }
    }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
