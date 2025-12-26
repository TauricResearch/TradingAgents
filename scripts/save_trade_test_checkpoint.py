#!/usr/bin/env python3
"""Save checkpoint after creating Trade model tests (Issue #6: DB-5)."""

from pathlib import Path
import sys

# Portable path detection (works from any directory)
current = Path.cwd()
while current != current.parent:
    if (current / ".git").exists() or (current / ".claude").exists():
        project_root = current
        break
    current = current.parent
else:
    project_root = Path.cwd()

# Add lib to path for imports
lib_path = project_root / "plugins/autonomous-dev/lib"
if lib_path.exists():
    sys.path.insert(0, str(lib_path))

    try:
        from agent_tracker import AgentTracker
        AgentTracker.save_agent_checkpoint(
            'test-master',
            'Trade model tests complete - 87 tests created (65 unit + 22 integration)'
        )
        print("✅ Checkpoint saved")
    except ImportError:
        print("ℹ️ Checkpoint skipped (user project)")
else:
    print("ℹ️ Checkpoint library not found")
