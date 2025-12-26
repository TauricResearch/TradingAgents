#!/usr/bin/env python3
"""
Agent Invocation Helper - Programmatic agent execution

This script allows programmatic invocation of autonomous-dev agents
for use in hooks and automation scripts.

Usage:
    python invoke_agent.py project-progress-tracker

Output:
    Agent's stdout (typically YAML or JSON)

Date: 2025-11-04
Feature: PROJECT.md auto-update
Agent: implementer
"""

import sys
from pathlib import Path

# Project root
project_root = Path(__file__).resolve().parents[3]


def invoke_agent(agent_name: str) -> str:
    """Invoke an agent and return its output.

    Args:
        agent_name: Name of agent to invoke (e.g., "project-progress-tracker")

    Returns:
        Agent output as string

    Raises:
        subprocess.CalledProcessError: If agent invocation fails
    """
    # Agent file path
    agent_file = project_root / "plugins" / "autonomous-dev" / "agents" / f"{agent_name}.md"

    if not agent_file.exists():
        raise FileNotFoundError(f"Agent not found: {agent_name}")

    # Use Claude Code Task tool via agent_invoker library
    lib_dir = project_root / "plugins" / "autonomous-dev" / "lib"
    sys.path.insert(0, str(lib_dir))

    try:
        from agent_invoker import AgentInvoker

        invoker = AgentInvoker()
        result = invoker.invoke_agent(agent_name)

        return result.get("output", "")

    except ImportError:
        # Fallback: direct Task tool not available
        # This is expected in hooks - just return empty
        return ""


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: invoke_agent.py <agent-name>", file=sys.stderr)
        sys.exit(1)

    agent_name = sys.argv[1]

    try:
        output = invoke_agent(agent_name)
        print(output)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
