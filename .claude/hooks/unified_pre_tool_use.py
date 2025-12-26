#!/usr/bin/env python3
"""
Unified PreToolUse Hook - Chains MCP Security + Auto-Approval

This module provides a single PreToolUse hook that chains two validators:
1. MCP Security Validator - Prevents CWE-22, CWE-78, SSRF for mcp__* tools
2. Auto-Approval Validator - Whitelist/blacklist logic for all tools

Architecture (Chain of Responsibility):
┌─────────────────────────────────────┐
│     on_pre_tool_use() (unified)     │
└─────────────────────────────────────┘
                 │
                 ├─ Step 1: MCP Security Check (mcp__* tools only)
                 │  → DENY if dangerous → exit
                 │  → PASS if safe → continue
                 │
                 └─ Step 2: Auto-Approval Check (all tools)
                    → APPROVE if trusted
                    → DENY if unknown/blacklisted

Benefits:
- No hook collision (single on_pre_tool_use function)
- Clear separation of concerns (each validator independent)
- Proper chaining (security first, then auto-approval)
- Configurable via environment variables
- Graceful degradation (errors default to manual approval)

Configuration:
- MCP_SECURITY_ENABLED (default: true) - Enable MCP security validation
- MCP_AUTO_APPROVE (default: false) - Enable auto-approval
- MCP_AUTO_APPROVE=everywhere|subagent_only|disabled

Usage:
    # Hook is automatically invoked by Claude Code
    # Returns {"approved": True/False, "reason": "..."}

Date: 2025-12-08
Issue: Hook collision between auto_approve_tool.py and mcp_security_enforcer.py
Agent: implementer
Phase: Refactoring (eliminate hook collision)
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# Add lib directory to path for imports
LIB_DIR = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB_DIR))

# Load .env file if available (for environment variable configuration)
def _load_env_file():
    """Load .env file from project root if it exists.

    This enables configuration via .env files (MCP_AUTO_APPROVE, MCP_SECURITY_ENABLED, etc.)
    without requiring python-dotenv as a dependency.
    """
    # Try multiple locations for .env file
    possible_env_files = [
        Path(os.getenv("PROJECT_ROOT", os.getcwd())) / ".env",  # Project root
        Path.cwd() / ".env",                                     # Current directory
        Path.home() / ".env",                                    # User home directory
    ]

    for env_file in possible_env_files:
        if env_file.exists():
            try:
                with open(env_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        # Skip comments and empty lines
                        if not line or line.startswith('#'):
                            continue
                        # Parse KEY=VALUE format
                        if '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip().strip('"').strip("'")  # Remove quotes
                            # Only set if not already in environment
                            if key not in os.environ:
                                os.environ[key] = value
                return  # Stop after first .env file found
            except Exception:
                pass  # Silently skip unreadable .env files

# Load .env file at module import time
_load_env_file()

# Import validators (with graceful degradation)
try:
    from mcp_permission_validator import MCPPermissionValidator, ValidationResult
    MCP_SECURITY_AVAILABLE = True
except ImportError:
    MCPPermissionValidator = None
    ValidationResult = None
    MCP_SECURITY_AVAILABLE = False

try:
    from tool_validator import ToolValidator, load_policy
    from tool_approval_audit import ToolApprovalAuditor
    from auto_approval_consent import check_user_consent, get_auto_approval_mode
    from user_state_manager import DEFAULT_STATE_FILE
    AUTO_APPROVAL_AVAILABLE = True
except ImportError:
    ToolValidator = None
    ToolApprovalAuditor = None
    check_user_consent = None
    get_auto_approval_mode = None
    AUTO_APPROVAL_AVAILABLE = False


# ============================================================================
# Configuration
# ============================================================================

def is_mcp_security_enabled() -> bool:
    """Check if MCP security validation is enabled.

    Returns:
        True if enabled (default), False if disabled
    """
    enabled = os.getenv("MCP_SECURITY_ENABLED", "true").lower()
    return enabled in ["true", "1", "yes", "on", "enable"]


# ============================================================================
# Validator 1: MCP Security (for mcp__* tools only)
# ============================================================================

def validate_mcp_security(
    tool: str,
    parameters: Dict[str, Any],
    project_root: str
) -> Optional[Dict[str, Any]]:
    """Validate MCP tool against security policy.

    This validator only runs for mcp__* tools. Non-MCP tools return None
    (pass through to next validator).

    Args:
        tool: Tool name (e.g., "mcp__filesystem__read")
        parameters: Tool parameters
        project_root: Project root directory

    Returns:
        {"approved": False, "reason": "..."} if denied
        None if passed (continue to next validator)
    """
    # Only validate MCP tools
    if not tool.startswith("mcp__"):
        return None  # Pass through to next validator

    # Check if MCP security is enabled
    if not is_mcp_security_enabled():
        return None  # Security disabled, pass through

    # Check if validator is available
    if not MCP_SECURITY_AVAILABLE or MCPPermissionValidator is None:
        return {
            "approved": False,
            "reason": "MCP security libraries not available (manual approval required)"
        }

    # Parse MCP tool format (mcp__category__operation)
    parts = tool.split("__")
    if len(parts) < 3:
        return {
            "approved": False,
            "reason": f"Invalid MCP tool format: {tool} (expected mcp__category__operation)"
        }

    category = parts[1]  # filesystem, shell, network, env
    operation = parts[2]  # read, write, execute, access

    # Detect policy file
    policy_file = Path(project_root) / ".mcp" / "security_policy.json"
    policy_path = str(policy_file) if policy_file.exists() else None

    # Create validator
    validator = MCPPermissionValidator(policy_path=policy_path)
    validator.project_root = project_root

    # Route to appropriate validation method
    result = None

    if category == "filesystem" or category == "fs":
        path = parameters.get("path")
        if not path:
            return {"approved": False, "reason": "Missing path parameter"}

        if operation == "read":
            result = validator.validate_fs_read(path)
        elif operation == "write":
            result = validator.validate_fs_write(path)
        else:
            return {"approved": False, "reason": f"Unknown filesystem operation: {operation}"}

    elif category == "shell":
        command = parameters.get("command")
        if not command:
            return {"approved": False, "reason": "Missing command parameter"}
        result = validator.validate_shell(command)

    elif category == "network":
        url = parameters.get("url")
        if not url:
            return {"approved": False, "reason": "Missing url parameter"}
        result = validator.validate_network(url)

    elif category == "env":
        var_name = parameters.get("name") or parameters.get("variable")
        if not var_name:
            return {"approved": False, "reason": "Missing variable name parameter"}
        result = validator.validate_env(var_name)

    else:
        return {"approved": False, "reason": f"Unknown MCP category: {category}"}

    # If validation failed, deny
    if result and not result.approved:
        return {"approved": False, "reason": result.reason}

    # Validation passed, continue to next validator
    return None


# ============================================================================
# Validator 2: Auto-Approval (for all tools)
# ============================================================================

def validate_auto_approval(
    tool: str,
    parameters: Dict[str, Any],
    agent_name: Optional[str]
) -> Dict[str, Any]:
    """Validate tool call against auto-approval policy.

    This validator runs for ALL tools (both MCP and non-MCP).

    Args:
        tool: Tool name
        parameters: Tool parameters
        agent_name: Agent name (from CLAUDE_AGENT_NAME env var)

    Returns:
        {"approved": True/False, "reason": "..."}
    """
    # Check if auto-approval is available
    if not AUTO_APPROVAL_AVAILABLE:
        return {
            "approved": False,
            "reason": "Auto-approval libraries not available (manual approval required)"
        }

    # Import the auto-approval logic from shared library
    # (This preserves all the existing logic without duplication)
    try:
        # Import from lib directory (already in sys.path from imports at top)
        from auto_approval_engine import should_auto_approve

        # Run auto-approval validation
        approved, reason = should_auto_approve(tool, parameters, agent_name)

        return {"approved": approved, "reason": reason}

    except ImportError as e:
        # Graceful degradation - library not available
        return {
            "approved": False,
            "reason": f"Auto-approval engine not available: {e}"
        }
    except Exception as e:
        # Graceful degradation - unexpected error
        return {
            "approved": False,
            "reason": f"Auto-approval error (defaulting to manual): {e}"
        }


# ============================================================================
# Format Conversion Helper
# ============================================================================

def _convert_to_claude_format(approved: bool, reason: str) -> Dict[str, Any]:
    """Convert internal format to Claude Code's expected format.

    Internal format: {"approved": bool, "reason": str}
    Claude Code format: {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow" | "deny" | "ask",
            "permissionDecisionReason": str
        }
    }

    Args:
        approved: Whether to approve the tool call
        reason: Human-readable explanation

    Returns:
        Dictionary in Claude Code's expected format
    """
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow" if approved else "deny",
            "permissionDecisionReason": reason
        }
    }


# ============================================================================
# Unified Hook Entry Point
# ============================================================================

def on_pre_tool_use(tool: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Unified PreToolUse lifecycle hook (chains validators).

    This hook chains two validators in order:
    1. MCP Security (for mcp__* tools) - Prevents security vulnerabilities
    2. Auto-Approval (for all tools) - Whitelist/blacklist logic

    Args:
        tool: Tool name (e.g., "Bash", "Read", "mcp__filesystem__read")
        parameters: Tool parameters dictionary

    Returns:
        Dictionary with Claude Code's expected format:
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow" | "deny" | "ask",
                "permissionDecisionReason": "explanation"
            }
        }

    Error Handling:
        - Graceful degradation: Any error results in manual approval
        - Missing dependencies: Returns manual approval
    """
    try:
        # Get project root
        project_root = os.getenv("PROJECT_ROOT", os.getcwd())

        # Get agent name
        agent_name = os.getenv("CLAUDE_AGENT_NAME", "").strip()
        agent_name = agent_name if agent_name else None

        # ========================================
        # Step 1: MCP Security Validation
        # ========================================
        mcp_result = validate_mcp_security(tool, parameters, project_root)

        # If MCP security denied, return immediately
        if mcp_result is not None and not mcp_result.get("approved", False):
            _log_denial(tool, parameters, agent_name, mcp_result["reason"], security_risk=True)
            return _convert_to_claude_format(False, mcp_result["reason"])

        # ========================================
        # Step 2: Auto-Approval Validation
        # ========================================
        approval_result = validate_auto_approval(tool, parameters, agent_name)

        # Log decision
        if approval_result["approved"]:
            _log_approval(tool, parameters, agent_name, approval_result["reason"])
        else:
            _log_denial(
                tool, parameters, agent_name, approval_result["reason"],
                security_risk="blacklist" in approval_result["reason"].lower()
            )

        return _convert_to_claude_format(
            approval_result["approved"],
            approval_result["reason"]
        )

    except Exception as e:
        # Graceful degradation - deny on error
        reason = f"Unified hook error (defaulting to manual): {e}"
        _log_denial(tool, parameters, None, reason, security_risk=False)

        return _convert_to_claude_format(False, reason)


# ============================================================================
# Logging Helpers
# ============================================================================

def _log_approval(
    tool: str,
    parameters: Dict[str, Any],
    agent_name: Optional[str],
    reason: str
) -> None:
    """Log approval decision."""
    if not AUTO_APPROVAL_AVAILABLE or ToolApprovalAuditor is None:
        return

    try:
        auditor = ToolApprovalAuditor()
        auditor.log_approval(
            agent_name=agent_name or "unknown",
            tool=tool,
            parameters=parameters,
            reason=reason
        )
    except Exception:
        pass  # Silent failure


def _log_denial(
    tool: str,
    parameters: Dict[str, Any],
    agent_name: Optional[str],
    reason: str,
    security_risk: bool
) -> None:
    """Log denial decision."""
    if not AUTO_APPROVAL_AVAILABLE or ToolApprovalAuditor is None:
        return

    try:
        auditor = ToolApprovalAuditor()
        auditor.log_denial(
            agent_name=agent_name or "unknown",
            tool=tool,
            parameters=parameters,
            reason=reason,
            security_risk=security_risk
        )
    except Exception:
        pass  # Silent failure


# ============================================================================
# Module Test
# ============================================================================

if __name__ == "__main__":
    # Test cases
    print("Testing unified hook...")

    # Test 1: MCP security validation
    result = on_pre_tool_use(
        "mcp__filesystem__read",
        {"path": "/etc/passwd"}
    )
    print(f"MCP read /etc/passwd: {result}")

    # Test 2: Auto-approval for safe command
    result = on_pre_tool_use(
        "Bash",
        {"command": "pytest tests/"}
    )
    print(f"Bash pytest: {result}")

    # Test 3: Auto-approval for dangerous command
    result = on_pre_tool_use(
        "Bash",
        {"command": "rm -rf /"}
    )
    print(f"Bash rm -rf: {result}")

    print("Done!")
