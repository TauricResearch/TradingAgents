#!/usr/bin/env python3
"""
SubagentStop Hook - Log Agent Completions to Structured Session File

This hook is invoked automatically when a subagent completes execution.
It logs the agent's completion to the structured pipeline JSON file.

Hook Type: SubagentStop
Trigger: After any subagent completes (researcher, planner, etc.)

Usage:
    Configured in .claude/settings.local.json:
    {
      "hooks": {
        "SubagentStop": [
          {
            "hooks": [{
              "type": "command",
              "command": "python .claude/hooks/log_agent_completion.py"
            }]
          }
        ]
      }
    }

Environment Variables (provided by Claude Code):
    CLAUDE_AGENT_NAME - Name of the subagent that completed
    CLAUDE_AGENT_OUTPUT - Output from the subagent (truncated)
    CLAUDE_AGENT_STATUS - Status: "success" or "error"

Output:
    Logs completion to docs/sessions/{date}-{time}-pipeline.json
"""

import os
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).resolve().parents[3]  # Go up from plugins/autonomous-dev/hooks/
sys.path.insert(0, str(project_root / "scripts"))

try:
    from agent_tracker import AgentTracker
except ImportError:
    # Fallback if script not found - just log to stderr
    print("Warning: agent_tracker.py not found, skipping structured logging", file=sys.stderr)
    sys.exit(0)


def main():
    """Log subagent completion to structured pipeline file"""
    # Get agent info from environment (provided by Claude Code)
    agent_name = os.environ.get("CLAUDE_AGENT_NAME", "unknown")
    agent_output = os.environ.get("CLAUDE_AGENT_OUTPUT", "")
    agent_status = os.environ.get("CLAUDE_AGENT_STATUS", "success")

    # Initialize tracker
    tracker = AgentTracker()

    # Issue #104: Auto-detect and track Task tool agents before completion
    # This ensures agents invoked via Task tool are properly tracked with start entries
    # before being marked as completed. The auto_track_from_environment() method is
    # idempotent - it returns False if agent is already tracked, preventing duplicates.
    #
    # Why this matters:
    # - Task tool sets CLAUDE_AGENT_NAME when invoking agents
    # - Without this call, complete_agent() may create incomplete entries
    # - With this call, agents get proper start + completion tracking
    # - /pipeline-status now shows accurate "7 of 7" instead of "4 of 7"
    if agent_status == "success":
        # Extract tools used from output (if available)
        # This is best-effort parsing - Claude Code doesn't provide this directly
        tools = extract_tools_from_output(agent_output)

        # Create summary message (first 100 chars of output)
        summary = agent_output[:100].replace("\n", " ") if agent_output else "Completed"

        # Auto-track agent first (idempotent - won't duplicate if already tracked)
        tracker.auto_track_from_environment(message=summary)

        # Then complete the agent (safe because auto_track was called)
        tracker.complete_agent(agent_name, summary, tools)
    else:
        # Extract error message
        error_msg = agent_output[:100].replace("\n", " ") if agent_output else "Failed"

        # Auto-track even for failures (ensures proper start entry)
        tracker.auto_track_from_environment(message=error_msg)

        # Then fail the agent
        tracker.fail_agent(agent_name, error_msg)


def extract_tools_from_output(output: str) -> list:
    """
    Best-effort extraction of tools used from agent output.

    Claude Code doesn't provide this directly, so we parse the output.
    This is heuristic-based and may not catch everything.
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


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Don't fail the hook - just log error and continue
        print(f"Warning: Agent completion logging failed: {e}", file=sys.stderr)
        sys.exit(0)  # Exit 0 so we don't block workflow
