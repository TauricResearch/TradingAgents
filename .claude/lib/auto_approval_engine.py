#!/usr/bin/env python3
"""
Auto-Approve Tool Hook - PreToolUse Hook for MCP Auto-Approval

This module implements the PreToolUse lifecycle hook that auto-approves
MCP tool calls from trusted subagents. It provides:

1. Subagent context detection (CLAUDE_AGENT_NAME env var)
2. Agent whitelist checking (trusted vs restricted agents)
3. User consent verification (opt-in design)
4. Tool call validation (whitelist/blacklist)
5. Circuit breaker logic (auto-disable after 10 denials)
6. Comprehensive audit logging (every approval/denial)
7. Graceful degradation (errors default to manual approval)

Security Architecture:
- Defense-in-depth: 6 layers of validation
  1. Subagent context check (only auto-approve in subagent)
  2. User consent check (must opt-in)
  3. Agent whitelist check (only trusted agents)
  4. Tool call validation (whitelist/blacklist)
  5. Circuit breaker (auto-disable after repeated denials)
  6. Audit logging (full trail of decisions)

- Conservative defaults: Deny unknown commands/paths
- Graceful degradation: Errors result in manual approval (safe failure)
- Zero trust: Every tool call is validated independently

Usage (Claude Code 2.0+ lifecycle hook):
    # In plugin manifest (pyproject.toml or plugins.json):
    [hooks]
    PreToolUse = "autonomous_dev.hooks.unified_pre_tool_use:on_pre_tool_use"

    # Claude Code will call on_pre_tool_use() before each MCP tool execution
    # Returns: {"approved": true/false, "reason": "explanation"}

Date: 2025-11-15
Issue: #73 (MCP Auto-Approval for Subagent Tool Calls)
Agent: implementer
Phase: TDD Green (making tests pass)

See error-handling-patterns skill for exception hierarchy and error handling best practices.
"""

import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional

# Add lib directory to path for imports
lib_dir = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(lib_dir))

# Import dependencies
from tool_validator import ToolValidator, load_policy
from tool_approval_audit import ToolApprovalAuditor
from auto_approval_consent import check_user_consent, get_auto_approval_mode
from user_state_manager import DEFAULT_STATE_FILE

# Import path_utils for policy file resolution
try:
    from path_utils import get_policy_file
except ImportError:
    # Fallback if path_utils not available
    def get_policy_file(use_cache: bool = True):
        """Fallback policy file resolution."""
        return Path(__file__).parent.parent / "config" / "auto_approve_policy.json"

# Default policy file path
DEFAULT_POLICY_FILE = get_policy_file()

# Circuit breaker threshold (10 denials → auto-disable)
CIRCUIT_BREAKER_THRESHOLD = 10

# Default audit log file
DEFAULT_AUDIT_LOG = Path(__file__).parent.parent.parent.parent / "logs" / "tool_auto_approve_audit.log"


@dataclass
class AutoApprovalState:
    """Thread-safe state for auto-approval logic.

    Tracks:
    - denial_count: Number of consecutive denials (for circuit breaker)
    - circuit_breaker_tripped: Whether circuit breaker has tripped

    Thread-safe: Uses threading.Lock for concurrent access.
    """
    denial_count: int = 0
    circuit_breaker_tripped: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def increment_denial_count(self) -> int:
        """Increment denial count (thread-safe).

        Returns:
            New denial count
        """
        with self._lock:
            self.denial_count += 1
            return self.denial_count

    def reset_denial_count(self) -> None:
        """Reset denial count to zero (thread-safe)."""
        with self._lock:
            self.denial_count = 0

    def trip_circuit_breaker(self) -> None:
        """Trip circuit breaker (thread-safe)."""
        with self._lock:
            self.circuit_breaker_tripped = True

    def reset_circuit_breaker(self) -> None:
        """Reset circuit breaker (thread-safe)."""
        with self._lock:
            self.circuit_breaker_tripped = False
            self.denial_count = 0

    def is_circuit_breaker_tripped(self) -> bool:
        """Check if circuit breaker is tripped (thread-safe).

        Returns:
            True if tripped, False otherwise
        """
        with self._lock:
            return self.circuit_breaker_tripped

    def get_denial_count(self) -> int:
        """Get current denial count (thread-safe).

        Returns:
            Current denial count
        """
        with self._lock:
            return self.denial_count

    def items(self):
        """Return state as items for dict-like interface.

        Returns:
            List of (key, value) tuples
        """
        with self._lock:
            return [
                ("denial_count", self.denial_count),
                ("circuit_breaker_tripped", self.circuit_breaker_tripped),
            ]


# Global state instance
_global_state: Optional[AutoApprovalState] = None
_global_state_lock = threading.Lock()


def _get_global_state() -> AutoApprovalState:
    """Get or create global state instance (thread-safe).

    Returns:
        Global AutoApprovalState instance
    """
    global _global_state, _global_state_lock

    with _global_state_lock:
        if _global_state is None:
            _global_state = AutoApprovalState()
        return _global_state


# Cached policy and validator (loaded once for performance)
_cached_policy: Optional[Dict[str, Any]] = None
_cached_validator: Optional[ToolValidator] = None
_cache_lock = threading.Lock()


def load_and_cache_policy(policy_file: Optional[Path] = None) -> Dict[str, Any]:
    """Load and cache policy file (thread-safe).

    Policy is loaded once and cached in memory for performance.

    Args:
        policy_file: Path to policy file (default: uses cascading lookup via get_policy_file)

    Returns:
        Policy dictionary
    """
    global _cached_policy, _cache_lock

    with _cache_lock:
        if _cached_policy is None:
            # Use cascading lookup if no explicit path provided
            policy_file = policy_file or get_policy_file()
            _cached_policy = load_policy(policy_file)

        return _cached_policy


def _get_cached_validator() -> ToolValidator:
    """Get or create cached validator instance (thread-safe).

    Returns:
        Cached ToolValidator instance
    """
    global _cached_validator, _cache_lock

    with _cache_lock:
        if _cached_validator is None:
            # Use cascading lookup for policy file
            _cached_validator = ToolValidator(policy_file=get_policy_file())

        return _cached_validator


# Subagent context detection

def is_subagent_context() -> bool:
    """Check if running in subagent context.

    Subagent context is detected via CLAUDE_AGENT_NAME environment variable,
    which Claude Code sets when executing tasks via the Task tool.

    Returns:
        True if in subagent context, False otherwise
    """
    agent_name = os.getenv("CLAUDE_AGENT_NAME", "").strip()
    return bool(agent_name)


def get_agent_name() -> Optional[str]:
    """Get agent name from environment variable.

    Sanitizes agent name to prevent injection attacks (removes newlines,
    carriage returns, tabs, and other control characters).

    Returns:
        Sanitized agent name if set, None otherwise
    """
    agent_name = os.getenv("CLAUDE_AGENT_NAME", "").strip()
    if not agent_name:
        return None

    # Sanitize agent name - remove control characters (CWE-117 prevention)
    # Remove all characters from \x00 to \x1f (control chars)
    sanitized = ''.join(c for c in agent_name if ord(c) >= 0x20)

    return sanitized if sanitized else None


# Agent whitelist checking

def is_trusted_agent(agent_name: Optional[str]) -> bool:
    """Check if agent is in trusted whitelist.

    Args:
        agent_name: Agent name to check

    Returns:
        True if trusted, False otherwise
    """
    if not agent_name:
        return False

    # Load policy
    policy = load_and_cache_policy()

    # Get trusted agents list
    trusted_agents = policy.get("agents", {}).get("trusted", [])

    # Case-insensitive check
    agent_name_lower = agent_name.lower()
    trusted_agents_lower = [a.lower() for a in trusted_agents]

    return agent_name_lower in trusted_agents_lower


# User consent checking

def check_user_consent_cached(state_file: Path = DEFAULT_STATE_FILE) -> bool:
    """Check user consent with caching.

    This is a wrapper around auto_approval_consent.check_user_consent()
    that's exposed for testing.

    Args:
        state_file: Path to user state file

    Returns:
        True if user consented, False otherwise
    """
    return check_user_consent(state_file)


# Circuit breaker logic

def increment_denial_count(state: Optional[AutoApprovalState] = None) -> int:
    """Increment denial count (convenience function).

    Args:
        state: AutoApprovalState instance (default: global state)

    Returns:
        New denial count
    """
    if state is None:
        state = _get_global_state()

    return state.increment_denial_count()


def should_trip_circuit_breaker(state: Optional[AutoApprovalState] = None) -> bool:
    """Check if circuit breaker should trip.

    Circuit breaker trips after CIRCUIT_BREAKER_THRESHOLD denials.

    Args:
        state: AutoApprovalState instance (default: global state)

    Returns:
        True if should trip, False otherwise
    """
    if state is None:
        state = _get_global_state()

    return state.get_denial_count() >= CIRCUIT_BREAKER_THRESHOLD


def reset_circuit_breaker(state: Optional[AutoApprovalState] = None) -> None:
    """Reset circuit breaker (convenience function).

    Args:
        state: AutoApprovalState instance (default: global state)
    """
    if state is None:
        state = _get_global_state()

    state.reset_circuit_breaker()


# Main auto-approval logic

def should_auto_approve(
    tool: str,
    parameters: Dict[str, Any],
    agent_name: Optional[str] = None,
) -> tuple[bool, str]:
    """Determine if tool call should be auto-approved.

    Decision logic:
    1. Check circuit breaker (deny if tripped)
    2. Get auto-approval mode (everywhere/subagent_only/disabled)
    3. Check context requirements based on mode
    4. Validate tool call (use ToolValidator)
    5. Update circuit breaker state based on result

    Args:
        tool: Tool name (Bash, Read, Write, etc.)
        parameters: Tool parameters
        agent_name: Agent name (from CLAUDE_AGENT_NAME env var)

    Returns:
        Tuple of (approved: bool, reason: str)
    """
    state = _get_global_state()

    # 1. Check circuit breaker
    if state.is_circuit_breaker_tripped():
        return False, "Circuit breaker tripped (too many denials)"

    # 2. Get auto-approval mode
    mode = get_auto_approval_mode()

    # 3. Check if auto-approval is disabled
    if mode == "disabled":
        return False, "Auto-approval disabled (MCP_AUTO_APPROVE not enabled)"

    # 4. Check context requirements based on mode
    in_subagent = is_subagent_context()

    if mode == "subagent_only" and not in_subagent:
        return False, "Mode is 'subagent_only' but not in subagent context"

    # 5. Agent whitelist check (only in subagent context, only in subagent_only mode)
    # In "everywhere" mode, skip whitelist check (trust all agents)
    if mode == "subagent_only" and in_subagent and not is_trusted_agent(agent_name):
        return False, f"Agent '{agent_name}' is not in trusted whitelist (subagent_only mode)"

    # 6. Validate tool call
    validator = _get_cached_validator()
    result = validator.validate_tool_call(tool, parameters, agent_name)

    # 7. Update circuit breaker state
    if not result.approved:
        # Increment denial count
        denial_count = increment_denial_count(state)

        # Check if should trip
        if should_trip_circuit_breaker(state):
            state.trip_circuit_breaker()

            # Log circuit breaker trip
            auditor = ToolApprovalAuditor()
            auditor.log_circuit_breaker_trip(
                agent_name=agent_name or "unknown",
                denial_count=denial_count,
                reason=f"Circuit breaker tripped after {denial_count} denials"
            )

            return False, f"Circuit breaker tripped after {denial_count} denials"

    else:
        # Approval - reset denial count
        state.reset_denial_count()

    return result.approved, result.reason


# PreToolUse hook entry point

def on_pre_tool_use(tool: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """PreToolUse lifecycle hook for MCP auto-approval.

    This hook is called by Claude Code before each MCP tool execution.
    It decides whether to auto-approve the tool call or require manual approval.

    Args:
        tool: Tool name (Bash, Read, Write, Edit, Grep, etc.)
        parameters: Tool parameters dictionary

    Returns:
        Dictionary with:
        - approved: bool (True = auto-approve, False = manual approval)
        - reason: str (human-readable explanation)

    Error Handling:
        - Graceful degradation: Any error results in manual approval
        - Audit logging: All errors are logged for debugging
    """
    try:
        # Get agent name from environment
        agent_name = get_agent_name()

        # Determine if should auto-approve
        approved, reason = should_auto_approve(tool, parameters, agent_name)

        # Log decision
        auditor = ToolApprovalAuditor()
        if approved:
            auditor.log_approval(
                agent_name=agent_name or "unknown",
                tool=tool,
                parameters=parameters,
                reason=reason
            )
        else:
            auditor.log_denial(
                agent_name=agent_name or "unknown",
                tool=tool,
                parameters=parameters,
                reason=reason,
                security_risk="blacklist" in reason.lower() or "injection" in reason.lower()
            )

        return {
            "approved": approved,
            "reason": reason
        }

    except Exception as e:
        # Graceful degradation - deny on error
        auditor = ToolApprovalAuditor()
        agent_name = get_agent_name()

        auditor.log_denial(
            agent_name=agent_name or "unknown",
            tool=tool,
            parameters=parameters,
            reason=f"Error in auto-approval logic: {e}",
            security_risk=False
        )

        return {
            "approved": False,
            "reason": f"Auto-approval error (defaulting to manual): {e}"
        }


# Exported convenience function for testing
def prompt_user_for_consent(state_file: Path = DEFAULT_STATE_FILE) -> bool:
    """Wrapper for auto_approval_consent.prompt_user_for_consent (for testing).

    Args:
        state_file: Path to user state file

    Returns:
        True if user consented, False otherwise
    """
    from auto_approval_consent import prompt_user_for_consent as _prompt
    return _prompt(state_file)
