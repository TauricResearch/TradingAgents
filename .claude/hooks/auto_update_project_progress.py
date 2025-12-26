#!/usr/bin/env python3
"""
SubagentStop Hook - Auto-Update PROJECT.md Progress After Pipeline

This hook automatically updates PROJECT.md goal progress after the doc-master
agent completes, marking the end of the /auto-implement pipeline.

Hook Type: SubagentStop
Trigger: After doc-master agent completes
Condition: All 7 agents completed successfully

Workflow:
1. Check if doc-master just completed (trigger condition)
2. Verify pipeline is complete (all 7 agents ran)
3. Invoke project-progress-tracker agent to assess progress
4. Parse YAML output from agent
5. Update PROJECT.md atomically with new progress
6. Create backup and handle rollback on failure

Relevant Skills:
- project-alignment-validation: GOALS validation patterns (see alignment-checklist.md)

Environment Variables (provided by Claude Code):
    CLAUDE_AGENT_NAME - Name of the subagent that completed
    CLAUDE_AGENT_OUTPUT - Output from the subagent
    CLAUDE_AGENT_STATUS - Status: "success" or "error"

Output:
    Updates PROJECT.md with goal progress
    Logs actions to session file

Date: 2025-11-04
Feature: PROJECT.md auto-update
Agent: implementer
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Any

# Add project root to path for imports
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root / "scripts"))
sys.path.insert(0, str(project_root / "plugins" / "autonomous-dev" / "lib"))

try:
    from agent_tracker import AgentTracker
    from project_md_updater import ProjectMdUpdater
except ImportError as e:
    print(f"Warning: Required module not found: {e}", file=sys.stderr)
    sys.exit(0)


def should_trigger_update(agent_name: str) -> bool:
    """Check if hook should trigger for this agent.

    Args:
        agent_name: Name of agent that completed

    Returns:
        True if should trigger (doc-master only), False otherwise
    """
    return agent_name == "doc-master"


def check_pipeline_complete(session_file: Path) -> bool:
    """Check if all 7 agents in pipeline completed.

    Args:
        session_file: Path to session JSON file

    Returns:
        True if pipeline complete, False otherwise
    """
    if not session_file.exists():
        return False

    try:
        session_data = json.loads(session_file.read_text())
    except (json.JSONDecodeError, OSError):
        return False

    # Check if all expected agents completed
    expected_agents = [
        "researcher",
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


def invoke_progress_tracker(timeout: int = 30) -> Optional[str]:
    """Invoke project-progress-tracker agent to assess progress.

    Args:
        timeout: Timeout in seconds (default 30)

    Returns:
        Agent output (YAML), or None on timeout/error
    """
    try:
        # Invoke agent via scripts/invoke_agent.py
        invoke_script = project_root / "plugins" / "autonomous-dev" / "scripts" / "invoke_agent.py"

        if not invoke_script.exists():
            # Fallback: direct invocation not available
            print("Warning: invoke_agent.py not found, skipping progress update", file=sys.stderr)
            return None

        result = subprocess.run(
            [sys.executable, str(invoke_script), "project-progress-tracker"],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(project_root)
        )

        if result.returncode == 0:
            return result.stdout
        else:
            print(f"Warning: progress tracker failed: {result.stderr}", file=sys.stderr)
            return None

    except subprocess.TimeoutExpired:
        print(f"Warning: progress tracker timed out after {timeout}s", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Warning: progress tracker error: {e}", file=sys.stderr)
        return None


def parse_agent_output(output: str) -> Optional[Dict[str, Any]]:
    """Parse YAML output from progress tracker agent.

    Args:
        output: YAML string from agent

    Returns:
        Parsed dict, or None on error
    """
    try:
        import yaml
    except ImportError:
        # Fallback to simple parsing if PyYAML not available
        return parse_simple_yaml(output)

    try:
        data = yaml.safe_load(output)
        return data if isinstance(data, dict) else None
    except yaml.YAMLError:
        return parse_simple_yaml(output)


def parse_simple_yaml(output: str) -> Optional[Dict[str, Any]]:
    """Simple YAML parser for basic assessment format.

    Handles format:
        assessment:
          goal_1: 25
          goal_2: 50

    Args:
        output: YAML-like string

    Returns:
        Parsed dict with "assessment" key, or None on error
    """
    try:
        result = {}
        current_section = None
        lines = output.strip().split('\n')

        for line in lines:
            # Skip empty lines
            if not line.strip():
                continue

            # Check for section header
            if ':' in line and not line.startswith(' '):
                section_name = line.split(':')[0].strip()
                current_section = section_name
                result[current_section] = {}
            # Check for key-value under section
            elif ':' in line and line.startswith(' ') and current_section:
                parts = line.strip().split(':', 1)  # Split on first : only
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip()
                    # Try to parse as int
                    try:
                        value = int(value)
                    except ValueError:
                        pass
                    result[current_section][key] = value

        # Return None if no valid assessment data found
        # (invalid YAML with multiple colons creates empty sections)
        if not result or "assessment" not in result or not result.get("assessment"):
            return None

        return result

    except Exception:
        return None


def update_project_with_rollback(
    project_file: Path,
    updates: Dict[str, int]
) -> bool:
    """Update PROJECT.md with rollback on failure.

    Args:
        project_file: Path to PROJECT.md
        updates: Dict mapping goal names to progress percentages

    Returns:
        True if successful, False otherwise
    """
    updater = None
    try:
        updater = ProjectMdUpdater(project_file)

        # Update all goals in a single operation
        updater.update_goal_progress(updates)

        return True

    except ValueError as e:
        # Validation error (merge conflict, invalid percentage, etc.)
        print(f"Warning: Cannot update PROJECT.md: {e}", file=sys.stderr)
        # Try to rollback if we created a backup
        if updater and updater.backup_file:
            try:
                updater.rollback()
                print("Rolled back PROJECT.md to backup", file=sys.stderr)
            except Exception as rollback_error:
                print(f"Warning: Rollback failed: {rollback_error}", file=sys.stderr)
        return False

    except Exception as e:
        # Unexpected error - try to rollback
        print(f"Error updating PROJECT.md: {e}", file=sys.stderr)
        if updater and updater.backup_file:
            try:
                updater.rollback()
                print("Rolled back PROJECT.md to backup", file=sys.stderr)
            except Exception as rollback_error:
                print(f"Warning: Rollback failed: {rollback_error}", file=sys.stderr)
        return False


def run_hook(
    agent_name: str,
    session_file: Path,
    project_file: Path
):
    """Main hook entry point.

    Args:
        agent_name: Name of agent that completed
        session_file: Path to session tracking file
        project_file: Path to PROJECT.md
    """
    # Check if we should trigger
    if not should_trigger_update(agent_name):
        return

    # Check if pipeline is complete
    if not check_pipeline_complete(session_file):
        print("Pipeline not complete, skipping PROJECT.md update", file=sys.stderr)
        return

    # Check if PROJECT.md exists
    if not project_file.exists():
        print(f"Warning: PROJECT.md not found at {project_file}", file=sys.stderr)
        return

    # Invoke progress tracker agent
    print("Invoking project-progress-tracker agent...", file=sys.stderr)
    agent_output = invoke_progress_tracker()

    if not agent_output:
        print("Warning: No output from progress tracker", file=sys.stderr)
        return

    # Parse agent output
    parsed = parse_agent_output(agent_output)
    if not parsed or "assessment" not in parsed:
        print("Warning: Invalid output format from progress tracker", file=sys.stderr)
        return

    # Extract goal updates
    assessment = parsed["assessment"]
    updates = {}

    for key, value in assessment.items():
        # Convert goal_1 -> Goal 1, goal_2 -> Goal 2, etc.
        if key.startswith("goal_"):
            goal_num = key.replace("goal_", "").replace("_", " ").title()
            goal_name = f"Goal {goal_num}"
            if isinstance(value, int):
                updates[goal_name] = value

    if not updates:
        print("No goal updates found in assessment", file=sys.stderr)
        return

    # Update PROJECT.md
    print(f"Updating PROJECT.md with {len(updates)} goal(s)...", file=sys.stderr)
    success = update_project_with_rollback(project_file, updates)

    if success:
        print("✅ PROJECT.md updated successfully", file=sys.stderr)
    else:
        print("❌ PROJECT.md update failed", file=sys.stderr)


def main():
    """Main entry point for SubagentStop hook."""
    # Get agent info from environment
    agent_name = os.environ.get("CLAUDE_AGENT_NAME", "unknown")

    # Find session file
    session_dir = project_root / "docs" / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)

    # Find most recent session file
    json_files = sorted(session_dir.glob("*-pipeline.json"))
    if not json_files:
        print("Warning: No session file found", file=sys.stderr)
        return

    session_file = json_files[-1]

    # Find PROJECT.md
    project_file = project_root / ".claude" / "PROJECT.md"

    # Run hook
    try:
        run_hook(agent_name, session_file, project_file)
    except Exception as e:
        # Don't fail the hook - just log error
        print(f"Warning: PROJECT.md update hook failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Warning: Hook execution failed: {e}", file=sys.stderr)
        sys.exit(0)  # Exit 0 so we don't block workflow
