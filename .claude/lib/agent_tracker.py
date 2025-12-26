#!/usr/bin/env python3
"""
Agent Pipeline Tracker Library - Backward-compatible shim

This file maintains backward compatibility after refactoring agent_tracker.py
into a package structure. All functionality is now organized in submodules:

- agent_tracker.models: Constants and metadata
- agent_tracker.state: Session state management
- agent_tracker.metrics: Progress calculation
- agent_tracker.verification: Parallel execution verification
- agent_tracker.display: Status display
- agent_tracker.tracker: Main AgentTracker class
- agent_tracker.cli: Command-line interface

This shim re-exports all public symbols so existing code continues to work:

    from agent_tracker import AgentTracker  # Still works
    tracker = AgentTracker()                # Still works
    tracker.start_agent(...)                # Still works

Date: 2025-12-25
Issue: GitHub #165 - Refactor agent_tracker.py into package
"""

# Re-export all public symbols from the package
from agent_tracker import (
    AgentTracker,
    AGENT_METADATA,
    EXPECTED_AGENTS,
    get_project_root,
    find_project_root,
    main,
)

# Maintain backward-compatible __all__
__all__ = [
    "AgentTracker",
    "AGENT_METADATA",
    "EXPECTED_AGENTS",
    "get_project_root",
    "find_project_root",
    "main",
]


# Support direct execution (backward compatibility)
if __name__ == "__main__":
    main()
