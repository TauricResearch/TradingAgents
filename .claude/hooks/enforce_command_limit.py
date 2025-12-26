#!/usr/bin/env python3
"""Enforce 15-command limit (expanded per GitHub #44).

Blocks commits if more than 15 active commands exist.
Allowed commands:
  Core (8): auto-implement, align-project, align-claude, setup, test, status, health-check, sync-dev, uninstall
  Individual Agents (7): research, plan, test-feature, implement, review, security-scan, update-docs
"""

import sys
from pathlib import Path


ALLOWED_COMMANDS = {
    # Core workflow commands (8)
    "auto-implement",
    "align-project",
    "align-claude",
    "setup",
    "test",
    "status",
    "health-check",
    "sync-dev",
    "uninstall",
    # Individual agent commands (7) - GitHub #44
    "research",
    "plan",
    "test-feature",
    "implement",
    "review",
    "security-scan",
    "update-docs",
}


def main():
    """Check command count."""
    commands_dir = Path("./plugins/autonomous-dev/commands")
    if not commands_dir.exists():
        sys.exit(0)

    # Find all active commands (not in archive)
    active = [
        f.stem
        for f in commands_dir.glob("*.md")
        if not f.parent.name == "archive"
    ]

    if len(active) > 15:
        disallowed = set(active) - ALLOWED_COMMANDS
        print(f"❌ Too many commands: {len(active)} active (limit: 15)", file=sys.stderr)
        print(f"\nAllowed 15 commands:", file=sys.stderr)
        print(f"  Core Workflow (8):", file=sys.stderr)
        for cmd in sorted(["auto-implement", "align-project", "align-claude", "setup", "test", "status", "health-check", "sync-dev", "uninstall"]):
            marker = "✓" if cmd in active else " "
            print(f"    [{marker}] {cmd}", file=sys.stderr)
        print(f"  Individual Agents (7):", file=sys.stderr)
        for cmd in sorted(["research", "plan", "test-feature", "implement", "review", "security-scan", "update-docs"]):
            marker = "✓" if cmd in active else " "
            print(f"    [{marker}] {cmd}", file=sys.stderr)

        if disallowed:
            print(f"\nDisallowed commands (archive these):", file=sys.stderr)
            for cmd in sorted(disallowed):
                print(f"  ❌ {cmd}.md → move to archive/", file=sys.stderr)

        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
