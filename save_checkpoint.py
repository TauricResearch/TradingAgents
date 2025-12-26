#!/usr/bin/env python3
"""Save checkpoint for test-master agent completion."""

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

    from agent_tracker import AgentTracker
    AgentTracker.save_agent_checkpoint(
        'test-master',
        'Tests complete - 79 tests created for Issue #3 (16 model tests, 26 API key tests, 34 validator tests, 3 fixtures)'
    )
    print("Checkpoint saved")
