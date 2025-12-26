#!/usr/bin/env python3
"""
Shim for deprecated auto_git_workflow.py - redirects to unified_git_automation.py

This file exists for backward compatibility with cached settings or configurations
that still reference the old hook name after consolidation (Issue #144).

The actual implementation is in unified_git_automation.py.
"""
import subprocess
import sys
from pathlib import Path

# Get the directory where this script lives
hook_dir = Path(__file__).parent

# Call the unified hook with the same arguments
unified_hook = hook_dir / "unified_git_automation.py"

if unified_hook.exists():
    result = subprocess.run(
        [sys.executable, str(unified_hook)] + sys.argv[1:],
        capture_output=False,
    )
    sys.exit(result.returncode)
else:
    print(f"WARNING: unified_git_automation.py not found at {unified_hook}", file=sys.stderr)
    sys.exit(0)  # Non-blocking - don't fail the workflow
