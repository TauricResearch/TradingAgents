#!/usr/bin/env python3
"""
Session Tracker CLI - Production Version

Location: plugins/autonomous-dev/scripts/session_tracker.py
Delegates to: plugins/autonomous-dev/lib/session_tracker.py

This is the production CLI wrapper that users invoke via:
    python plugins/autonomous-dev/scripts/session_tracker.py <agent_name> <message>

It delegates to the lib implementation for all functionality.

Usage:
    python plugins/autonomous-dev/scripts/session_tracker.py <agent_name> <message>

Example:
    python plugins/autonomous-dev/scripts/session_tracker.py researcher "Research complete"

Design Patterns:
    See library-design-patterns skill for two-tier CLI design pattern.
"""

import sys
from pathlib import Path

# Add project root to path for plugins import
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from plugins.autonomous_dev.lib.session_tracker import SessionTracker


def main():
    """Main CLI entry point - delegates to library implementation."""
    # Validate argument count
    if len(sys.argv) < 3:
        print("Usage: session_tracker.py <agent_name> <message>")
        print("\nExample:")
        print('  session_tracker.py researcher "Research complete - docs/research/auth.md"')
        sys.exit(1)

    # Parse command-line arguments
    agent_name = sys.argv[1]
    message = " ".join(sys.argv[2:])

    # Delegate to library implementation
    try:
        tracker = SessionTracker()
        tracker.log(agent_name, message)
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
