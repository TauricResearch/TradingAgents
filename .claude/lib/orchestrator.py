"""
Orchestrator for autonomous-dev v2.0
Master coordinator for PROJECT.md-aligned autonomous development.

This module has been refactored into smaller, focused modules:
- project_md_parser.py: PROJECT.md parsing
- agent_invoker.py: Agent invocation factory
- workflow_coordinator.py: Main orchestration logic

Validation is now done by specialized agents (alignment-validator, security-auditor)
invoked via the Task tool (Claude Code native - no separate API key needed).

For backward compatibility, we re-export the main classes here.
"""

# Import all classes from new modular structure
from project_md_parser import ProjectMdParser
from agent_invoker import AgentInvoker
from workflow_coordinator import WorkflowCoordinator, Orchestrator

# Re-export for backward compatibility
__all__ = [
    'ProjectMdParser',
    'AgentInvoker',
    'WorkflowCoordinator',
    'Orchestrator'  # Alias for WorkflowCoordinator
]
