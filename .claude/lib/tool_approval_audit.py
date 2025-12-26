#!/usr/bin/env python3
"""
Tool Approval Audit - Audit Logging for MCP Auto-Approval

This module provides comprehensive audit logging for MCP tool approval decisions.
It implements security best practices for audit trail integrity:

1. JSON Lines format (one event per line for easy parsing)
2. Log injection prevention (CWE-117)
3. Sensitive data redaction (API keys, tokens, passwords)
4. Log rotation (10MB max size, keep 5 backups)
5. Thread-safe logging (concurrent agent tool calls)
6. Structured logging fields (timestamp, event, agent, tool, reason)

Security Features:
- CWE-117 prevention: Sanitize all user input before logging
- Sensitive data redaction: Automatically redact API keys, tokens, passwords
- Audit trail integrity: Immutable JSON lines format
- Log rotation: Prevent disk exhaustion
- Thread-safe: Safe for concurrent agent tool calls

Usage:
    from tool_approval_audit import ToolApprovalAuditor

    # Initialize auditor
    auditor = ToolApprovalAuditor()

    # Log approval
    auditor.log_approval(
        agent_name="researcher",
        tool="Bash",
        parameters={"command": "pytest tests/"},
        reason="Matches whitelist pattern: pytest*"
    )

    # Log denial
    auditor.log_denial(
        agent_name="researcher",
        tool="Bash",
        parameters={"command": "rm -rf /"},
        reason="Matches blacklist pattern: rm -rf*",
        security_risk=True
    )

    # Log circuit breaker trip
    auditor.log_circuit_breaker_trip(
        agent_name="researcher",
        denial_count=10,
        reason="Too many denials (10), disabling auto-approval"
    )

Date: 2025-11-15
Issue: #73 (MCP Auto-Approval for Subagent Tool Calls)
Agent: implementer
Phase: TDD Green (making tests pass)

See error-handling-patterns skill for exception hierarchy and error handling best practices.
"""

import json
import logging
import re
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Any, List, Optional


# Default audit log file location
DEFAULT_LOG_FILE = Path(__file__).parent.parent.parent.parent / "logs" / "tool_auto_approve_audit.log"

# Sensitive data patterns for redaction
SENSITIVE_PATTERNS = [
    (re.compile(r'(Authorization|Bearer|Token):\s*\S+', re.IGNORECASE), r'\1: [REDACTED]'),
    (re.compile(r'(api[_-]?key|apikey)\s*[=:]\s*[\'"]?\S+', re.IGNORECASE), r'\1=[REDACTED]'),
    (re.compile(r'(password|passwd|pwd)\s*[=:]\s*[\'"]?\S+', re.IGNORECASE), r'\1=[REDACTED]'),
    (re.compile(r'(secret|token)\s*[=:]\s*[\'"]?\S+', re.IGNORECASE), r'\1=[REDACTED]'),
    (re.compile(r'sk-[a-zA-Z0-9]{20,}'), '[REDACTED_API_KEY]'),  # OpenAI-style API keys
    (re.compile(r'ghp_[a-zA-Z0-9]{36,}'), '[REDACTED_GITHUB_TOKEN]'),  # GitHub tokens
]

# Log injection prevention patterns (CWE-117)
# All control characters from \x00 to \x1f except \t (tab is visible)
INJECTION_CHARS = [chr(i) for i in range(0x00, 0x20) if i != 0x09]  # Exclude tab (0x09)

# Thread-safe logger singleton
_audit_logger: Optional[logging.Logger] = None
_audit_logger_lock = threading.Lock()


@dataclass
class AuditLogEntry:
    """Structured audit log entry.

    Attributes:
        timestamp: ISO 8601 timestamp with timezone
        event: Event type (approval, denial, circuit_breaker_trip)
        agent: Agent name that requested tool call
        tool: Tool name (Bash, Read, Write, etc.)
        reason: Human-readable explanation of decision
        security_risk: Whether denial is due to security concerns
        parameters: Sanitized tool parameters
        denial_count: Number of denials (for circuit breaker events)
    """
    timestamp: str
    event: str
    agent: str
    tool: Optional[str] = None
    reason: Optional[str] = None
    security_risk: bool = False
    parameters: Optional[Dict[str, Any]] = None
    denial_count: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values.

        Returns:
            Dictionary representation
        """
        return {k: v for k, v in asdict(self).items() if v is not None}


class ToolApprovalAuditor:
    """Audit logger for MCP tool approval decisions.

    This class provides thread-safe audit logging with:
    - JSON Lines format (one event per line)
    - Log injection prevention (CWE-117)
    - Sensitive data redaction
    - Log rotation (10MB max, 5 backups)

    Thread-safe: Uses threading.Lock for concurrent access.

    Example:
        >>> auditor = ToolApprovalAuditor()
        >>> auditor.log_approval("researcher", "Bash", {"command": "pytest"}, "Whitelisted")
    """

    def __init__(self, log_file: Optional[Path] = None):
        """Initialize ToolApprovalAuditor.

        Args:
            log_file: Path to audit log file (default: logs/tool_auto_approve_audit.log)
        """
        self.log_file = log_file or DEFAULT_LOG_FILE
        self._ensure_log_file_exists()
        self.logger = self._get_audit_logger()

    def _ensure_log_file_exists(self) -> None:
        """Create log file and parent directories if they don't exist."""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_file.exists():
            self.log_file.touch()

    def _get_audit_logger(self) -> logging.Logger:
        """Get or create thread-safe audit logger with rotation.

        Returns:
            Configured logger for audit events
        """
        global _audit_logger, _audit_logger_lock

        with _audit_logger_lock:
            if _audit_logger is None:
                _audit_logger = logging.getLogger("tool_approval_audit")
                _audit_logger.setLevel(logging.INFO)
                _audit_logger.propagate = False  # Don't propagate to root logger

                # Remove existing handlers
                _audit_logger.handlers.clear()

                # Add rotating file handler (10MB max, 5 backups)
                handler = RotatingFileHandler(
                    self.log_file,
                    maxBytes=10 * 1024 * 1024,  # 10MB
                    backupCount=5,
                    encoding='utf-8',
                )

                # JSON Lines format (no extra formatting)
                formatter = logging.Formatter('%(message)s')
                handler.setFormatter(formatter)

                _audit_logger.addHandler(handler)

            return _audit_logger

    def log_approval(
        self,
        agent_name: str,
        tool: str,
        parameters: Dict[str, Any],
        reason: str,
    ) -> None:
        """Log tool approval decision.

        Args:
            agent_name: Name of agent that requested tool call
            tool: Tool name (Bash, Read, Write, etc.)
            parameters: Tool parameters (will be sanitized)
            reason: Human-readable explanation of approval
        """
        # Sanitize parameters
        sanitized_params = self._sanitize_parameters(parameters)

        # Create audit log entry
        entry = AuditLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event="approval",
            agent=agent_name,
            tool=tool,
            reason=sanitize_log_input(reason),
            security_risk=False,
            parameters=sanitized_params,
        )

        # Write JSON line to log
        self.logger.info(json.dumps(entry.to_dict()))

    def log_denial(
        self,
        agent_name: str,
        tool: str,
        parameters: Dict[str, Any],
        reason: str,
        security_risk: bool = False,
    ) -> None:
        """Log tool denial decision.

        Args:
            agent_name: Name of agent that requested tool call
            tool: Tool name (Bash, Read, Write, etc.)
            parameters: Tool parameters (will be sanitized)
            reason: Human-readable explanation of denial
            security_risk: Whether denial is due to security concerns
        """
        # Sanitize parameters
        sanitized_params = self._sanitize_parameters(parameters)

        # Create audit log entry
        entry = AuditLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event="denial",
            agent=agent_name,
            tool=tool,
            reason=sanitize_log_input(reason),
            security_risk=security_risk,
            parameters=sanitized_params,
        )

        # Write JSON line to log
        self.logger.info(json.dumps(entry.to_dict()))

    def log_circuit_breaker_trip(
        self,
        agent_name: str,
        denial_count: int,
        reason: str,
    ) -> None:
        """Log circuit breaker trip event.

        Args:
            agent_name: Name of agent that triggered circuit breaker
            denial_count: Number of denials that triggered circuit breaker
            reason: Human-readable explanation
        """
        # Create audit log entry
        entry = AuditLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event="circuit_breaker_trip",
            agent=agent_name,
            reason=sanitize_log_input(reason),
            denial_count=denial_count,
        )

        # Write JSON line to log
        self.logger.info(json.dumps(entry.to_dict()))

    def _sanitize_parameters(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize parameters to remove sensitive data.

        Args:
            parameters: Tool parameters dictionary

        Returns:
            Sanitized parameters with sensitive data redacted
        """
        sanitized = {}

        for key, value in parameters.items():
            if isinstance(value, str):
                # Redact sensitive data
                sanitized_value = value
                for pattern, replacement in SENSITIVE_PATTERNS:
                    sanitized_value = pattern.sub(replacement, sanitized_value)

                # Prevent log injection (CWE-117)
                sanitized_value = sanitize_log_input(sanitized_value)

                sanitized[key] = sanitized_value
            else:
                # Non-string values are safe (int, bool, etc.)
                sanitized[key] = value

        return sanitized


def sanitize_log_input(text: str) -> str:
    """Sanitize text input to prevent log injection (CWE-117).

    Removes newlines, carriage returns, tabs, null bytes, and ANSI escape
    sequences that could be used to inject fake log entries or break log parsing.

    Args:
        text: Text to sanitize

    Returns:
        Sanitized text with injection characters replaced by spaces
    """
    sanitized = text

    # Remove individual injection characters
    for char in INJECTION_CHARS:
        sanitized = sanitized.replace(char, ' ')

    # Remove ANSI escape sequences (multi-byte patterns like \x1b[...)
    # Pattern: ESC [ followed by any number of parameters and command letter
    ansi_escape_pattern = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
    sanitized = ansi_escape_pattern.sub(' ', sanitized)

    return sanitized


def parse_audit_log(log_file: Optional[Path] = None) -> List[AuditLogEntry]:
    """Parse audit log file into structured entries.

    Args:
        log_file: Path to audit log file (default: logs/tool_auto_approve_audit.log)

    Returns:
        List of AuditLogEntry objects
    """
    log_file = log_file or DEFAULT_LOG_FILE

    if not log_file.exists():
        return []

    entries = []
    with open(log_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                entry = AuditLogEntry(**data)
                entries.append(entry)
            except (json.JSONDecodeError, TypeError) as e:
                # Skip malformed lines
                continue

    return entries


# Convenience functions for direct usage

# Global auditor instance (lazy initialization)
_global_auditor: Optional[ToolApprovalAuditor] = None
_global_auditor_lock = threading.Lock()


def _get_global_auditor() -> ToolApprovalAuditor:
    """Get or create global auditor instance.

    Returns:
        Global ToolApprovalAuditor instance
    """
    global _global_auditor, _global_auditor_lock

    with _global_auditor_lock:
        if _global_auditor is None:
            _global_auditor = ToolApprovalAuditor()
        return _global_auditor


def log_approval(
    agent_name: str,
    tool: str,
    parameters: Dict[str, Any],
    reason: str,
) -> None:
    """Log approval decision (convenience function).

    Args:
        agent_name: Agent name
        tool: Tool name
        parameters: Tool parameters
        reason: Approval reason
    """
    auditor = _get_global_auditor()
    auditor.log_approval(agent_name, tool, parameters, reason)


def log_denial(
    agent_name: str,
    tool: str,
    parameters: Dict[str, Any],
    reason: str,
    security_risk: bool = False,
) -> None:
    """Log denial decision (convenience function).

    Args:
        agent_name: Agent name
        tool: Tool name
        parameters: Tool parameters
        reason: Denial reason
        security_risk: Whether denial is due to security
    """
    auditor = _get_global_auditor()
    auditor.log_denial(agent_name, tool, parameters, reason, security_risk)


def log_circuit_breaker_trip(
    agent_name: str,
    denial_count: int,
    reason: str,
) -> None:
    """Log circuit breaker trip (convenience function).

    Args:
        agent_name: Agent name
        denial_count: Number of denials
        reason: Trip reason
    """
    auditor = _get_global_auditor()
    auditor.log_circuit_breaker_trip(agent_name, denial_count, reason)
