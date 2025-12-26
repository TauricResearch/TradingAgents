#!/usr/bin/env python3
"""
Agent Tracker CLI Wrapper - Delegates to lib/agent_tracker.py

DEPRECATION NOTICE:
This is a CLI wrapper that delegates to the library implementation.
For programmatic usage, import from lib/agent_tracker.py instead:

    from plugins.autonomous_dev.lib.agent_tracker import AgentTracker

This wrapper exists for backward compatibility with installed plugins.

Usage:
    python plugins/autonomous-dev/scripts/agent_tracker.py start <agent_name> <message>
    python plugins/autonomous-dev/scripts/agent_tracker.py complete <agent_name> <message> [--tools tool1,tool2]
    python plugins/autonomous-dev/scripts/agent_tracker.py fail <agent_name> <message>
    python plugins/autonomous-dev/scripts/agent_tracker.py status

Date: 2025-11-19
Issue: GitHub #79 (Tracking infrastructure portability)
Agent: implementer
Phase: CLI wrapper creation

Design Patterns:
    See library-design-patterns skill for two-tier CLI design pattern.
"""

import sys
from pathlib import Path

# Add project root to path for plugins import
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import library implementation - use full path to avoid circular imports
from plugins.autonomous_dev.lib.agent_tracker import AgentTracker


def main():
    """CLI interface for agent tracker - delegates to library implementation."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  agent_tracker.py start <agent_name> <message>")
        print("  agent_tracker.py complete <agent_name> <message> [--tools tool1,tool2]")
        print("  agent_tracker.py fail <agent_name> <message>")
        print("  agent_tracker.py status")
        print("\nExamples:")
        print('  agent_tracker.py start researcher "Researching JWT patterns"')
        print('  agent_tracker.py complete researcher "Found 3 patterns" --tools WebSearch,Grep')
        print('  agent_tracker.py fail researcher "No patterns found"')
        print('  agent_tracker.py status')
        sys.exit(1)

    command = sys.argv[1]

    try:
        tracker = AgentTracker()

        if command == "start":
            if len(sys.argv) < 4:
                print("Error: start requires <agent_name> <message>")
                sys.exit(1)
            agent_name = sys.argv[2]
            message = " ".join(sys.argv[3:])
            tracker.start_agent(agent_name, message)

        elif command == "complete":
            if len(sys.argv) < 4:
                print("Error: complete requires <agent_name> <message>")
                sys.exit(1)

            agent_name = sys.argv[2]

            # Parse --tools flag if present
            tools = None
            message_parts = []
            i = 3
            while i < len(sys.argv):
                if sys.argv[i] == "--tools":
                    if i + 1 < len(sys.argv):
                        tools = sys.argv[i + 1].split(",")
                        i += 2
                    else:
                        print("Error: --tools requires argument")
                        sys.exit(1)
                else:
                    message_parts.append(sys.argv[i])
                    i += 1

            message = " ".join(message_parts)
            tracker.complete_agent(agent_name, message, tools=tools)

        elif command == "fail":
            if len(sys.argv) < 4:
                print("Error: fail requires <agent_name> <message>")
                sys.exit(1)
            agent_name = sys.argv[2]
            message = " ".join(sys.argv[3:])
            tracker.fail_agent(agent_name, message)

        elif command == "status":
            tracker.show_status()

        else:
            print(f"Error: Unknown command '{command}'")
            print("Valid commands: start, complete, fail, status")
            sys.exit(1)

        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
