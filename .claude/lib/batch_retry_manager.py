#!/usr/bin/env python3
"""
Batch Retry Manager - Orchestrate retry logic for /batch-implement workflows.

Manages automatic retry logic with max retries, circuit breaker, and global limits.

Features:
1. Per-feature retry tracking (max 3 retries)
2. Circuit breaker (pause after 5 consecutive failures)
3. Global retry limit (prevent resource exhaustion)
4. Retry state persistence (survive crashes)
5. Audit logging for all retry attempts

Retry Decision Logic:
    1. Check circuit breaker (5 consecutive failures → block)
    2. Check global retry limit (max total retries → block)
    3. Check failure type (permanent → block)
    4. Check per-feature retry count (3 retries → block)
    5. If all checks pass → allow retry

Usage:
    from batch_retry_manager import (
        BatchRetryManager,
        should_retry_feature,
        MAX_RETRIES_PER_FEATURE,
    )

    # Create manager
    manager = BatchRetryManager("batch-20251118-123456")

    # Check if should retry
    decision = manager.should_retry_feature(
        feature_index=0,
        failure_type=FailureType.TRANSIENT
    )

    if decision.should_retry:
        # Record attempt
        manager.record_retry_attempt(0, "ConnectionError: Failed")

        # Retry feature...

Security:
- Audit logging for all retry attempts
- Global limits prevent resource exhaustion
- Circuit breaker prevents infinite loops
- State file validation and atomic writes

Date: 2025-11-18
Issue: #89 (Automatic Failure Recovery for /batch-implement)
Agent: implementer
Phase: TDD Green (making tests pass)

See error-handling-patterns skill for exception hierarchy and error handling best practices.
See state-management-patterns skill for state persistence patterns.
"""

import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any

# Import failure classifier and consent checker
try:
    from .failure_classifier import FailureType, sanitize_error_message
    from . import batch_retry_consent
except ImportError:
    lib_dir = Path(__file__).parent.resolve()
    sys.path.insert(0, str(lib_dir))
    from failure_classifier import FailureType, sanitize_error_message
    import batch_retry_consent


# =============================================================================
# Constants
# =============================================================================

# Max retries per feature (3 attempts)
MAX_RETRIES_PER_FEATURE = 3

# Circuit breaker threshold (5 consecutive failures)
CIRCUIT_BREAKER_THRESHOLD = 5

# Global retry limit (prevent resource exhaustion)
MAX_TOTAL_RETRIES = 50


# =============================================================================
# Exceptions
# =============================================================================

class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is triggered."""
    pass


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class RetryDecision:
    """Decision about whether to retry a failed feature."""
    should_retry: bool
    reason: str
    retry_count: int = 0


@dataclass
class RetryState:
    """Persistent retry state for a batch."""
    batch_id: str
    retry_counts: Dict[int, int] = field(default_factory=dict)  # feature_index → count
    global_retry_count: int = 0
    consecutive_failures: int = 0
    circuit_breaker_open: bool = False
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


# =============================================================================
# Audit Logging
# =============================================================================

def log_audit_event(event_type: str, batch_id: str, details: Dict[str, Any]) -> None:
    """
    Log retry attempt to audit file.

    Audit Log Format (JSONL):
        Each line is a JSON object with:
        - timestamp (str): ISO 8601 timestamp (UTC)
        - event_type (str): "retry_attempt" or "circuit_breaker_triggered"
        - batch_id (str): Unique batch identifier
        - Additional fields from details dict

    Example audit entry:
        {
          "timestamp": "2025-11-18T12:34:56.789Z",
          "event_type": "retry_attempt",
          "batch_id": "batch-20251118-123456",
          "feature_index": 0,
          "retry_count": 1,
          "global_retry_count": 1,
          "error_message": "ConnectionError: Failed to connect",
          "feature_name": "Add user authentication"
        }

    Args:
        event_type: Type of event (e.g., "retry_attempt", "circuit_breaker")
        batch_id: Batch ID for tracking
        details: Event details (will be merged into audit entry)
    """
    # Create audit log directory
    audit_dir = Path.cwd() / ".claude" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    # Audit log file
    audit_file = audit_dir / f"{batch_id}_retry_audit.jsonl"

    # Create audit entry
    audit_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event_type": event_type,
        "batch_id": batch_id,
        **details,
    }

    # Append to audit log (JSONL format)
    try:
        with open(audit_file, "a") as f:
            f.write(json.dumps(audit_entry) + "\n")
    except OSError:
        # Non-blocking - log to stderr but don't fail
        print(f"Warning: Failed to write audit log: {audit_file}", file=sys.stderr)


# =============================================================================
# Batch Retry Manager
# =============================================================================

class BatchRetryManager:
    """
    Orchestrate retry logic for /batch-implement workflows.

    Manages:
    - Per-feature retry counts
    - Global retry limits
    - Circuit breaker logic
    - Retry state persistence
    """

    def __init__(self, batch_id: str, state_dir: Optional[Path] = None):
        """
        Initialize retry manager.

        Args:
            batch_id: Unique batch identifier
            state_dir: Directory for state files (default: ./.claude)

        Raises:
            ValueError: If batch_id contains path traversal or directory separators
        """
        # Validate batch_id for path traversal (CWE-22)
        if ".." in batch_id or "/" in batch_id or "\\" in batch_id:
            raise ValueError(
                f"Invalid batch_id: contains path traversal or directory separators. "
                f"batch_id must be a simple identifier without path components. Got: {batch_id}"
            )

        self.batch_id = batch_id
        self.state_dir = state_dir or Path.cwd() / ".claude"
        self.state_file = self.state_dir / f"{batch_id}_retry_state.json"

        # Load existing state or create new
        self.state = self._load_state()

    def _load_state(self) -> RetryState:
        """
        Load retry state from file or create new state.

        Returns:
            RetryState object
        """
        if not self.state_file.exists():
            return RetryState(batch_id=self.batch_id)

        try:
            data = json.loads(self.state_file.read_text())
            return RetryState(
                batch_id=data.get("batch_id", self.batch_id),
                retry_counts={int(k): v for k, v in data.get("retry_counts", {}).items()},
                global_retry_count=data.get("global_retry_count", 0),
                consecutive_failures=data.get("consecutive_failures", 0),
                circuit_breaker_open=data.get("circuit_breaker_open", False),
                created_at=data.get("created_at", datetime.utcnow().isoformat() + "Z"),
                updated_at=data.get("updated_at", datetime.utcnow().isoformat() + "Z"),
            )
        except (json.JSONDecodeError, OSError):
            # Corrupted file - start fresh
            return RetryState(batch_id=self.batch_id)

    def _save_state(self) -> None:
        """
        Save retry state to file (atomic write).
        """
        # Update timestamp
        self.state.updated_at = datetime.utcnow().isoformat() + "Z"

        # Convert to dict
        state_dict = {
            "batch_id": self.state.batch_id,
            "retry_counts": self.state.retry_counts,
            "global_retry_count": self.state.global_retry_count,
            "consecutive_failures": self.state.consecutive_failures,
            "circuit_breaker_open": self.state.circuit_breaker_open,
            "created_at": self.state.created_at,
            "updated_at": self.state.updated_at,
        }

        # Atomic write (temp + rename)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        fd, temp_path = tempfile.mkstemp(
            dir=self.state_dir,
            prefix=".retry_state_",
            suffix=".tmp"
        )

        try:
            os.write(fd, json.dumps(state_dict, indent=2).encode())
            os.close(fd)
            Path(temp_path).replace(self.state_file)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                Path(temp_path).unlink()
            except OSError:
                pass
            raise

    def get_retry_count(self, feature_index: int) -> int:
        """
        Get retry count for a specific feature.

        Args:
            feature_index: Index of feature

        Returns:
            Number of retry attempts (0 if never retried)
        """
        return self.state.retry_counts.get(feature_index, 0)

    def get_global_retry_count(self) -> int:
        """
        Get total retry count across all features.

        Returns:
            Total number of retry attempts
        """
        return self.state.global_retry_count

    def record_retry_attempt(self, feature_index: int, error_message: str, feature_name: str = "") -> None:
        """
        Record a retry attempt.

        Updates:
        - Per-feature retry count
        - Global retry count
        - Consecutive failure count
        - Audit log

        Args:
            feature_index: Index of feature being retried
            error_message: Error message from failed attempt
            feature_name: Name of feature (optional, for audit logging)
        """
        # Increment counters (with global limit enforcement)
        self.state.retry_counts[feature_index] = self.get_retry_count(feature_index) + 1

        # Enforce global retry limit (CWE-400 resource exhaustion prevention)
        if self.state.global_retry_count < MAX_TOTAL_RETRIES:
            self.state.global_retry_count += 1
        # Note: If already at MAX_TOTAL_RETRIES, don't increment further
        # This prevents counter overflow and enforces hard limit

        self.state.consecutive_failures += 1

        # Check circuit breaker
        if self.state.consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
            self.state.circuit_breaker_open = True

            # User-visible notification (CWE-400 protection)
            print(
                f"\n⚠️  Circuit breaker triggered after {self.state.consecutive_failures} "
                f"consecutive failures.\n"
                f"Automatic retries paused for safety.\n"
                f"To resume, fix the underlying issue and run: /batch-implement --resume {self.batch_id}\n",
                file=sys.stderr
            )

            log_audit_event(
                "circuit_breaker_triggered",
                self.batch_id,
                {
                    "consecutive_failures": self.state.consecutive_failures,
                    "threshold": CIRCUIT_BREAKER_THRESHOLD,
                }
            )

        # Save state
        self._save_state()

        # Log audit event with sanitized feature name (CWE-117 log injection prevention)
        log_audit_event(
            "retry_attempt",
            self.batch_id,
            {
                "feature_index": feature_index,
                "retry_count": self.get_retry_count(feature_index),
                "global_retry_count": self.state.global_retry_count,
                "error_message": sanitize_error_message(error_message),
                "feature_name": sanitize_error_message(feature_name) if feature_name else "",
            }
        )

    def record_success(self, feature_index: int) -> None:
        """
        Record a successful feature completion.

        Resets consecutive failure count (circuit breaker).

        Args:
            feature_index: Index of successful feature
        """
        # Reset consecutive failures (circuit breaker)
        self.state.consecutive_failures = 0
        self.state.circuit_breaker_open = False

        # Save state
        self._save_state()

    def check_circuit_breaker(self) -> bool:
        """
        Check if circuit breaker is open.

        Returns:
            True if circuit breaker is open (retries blocked), False otherwise
        """
        return self.state.circuit_breaker_open

    def reset_circuit_breaker(self) -> None:
        """
        Manually reset circuit breaker.

        Use this after manual intervention to resume batch processing.
        """
        self.state.circuit_breaker_open = False
        self.state.consecutive_failures = 0
        self._save_state()

    def should_retry_feature(
        self,
        feature_index: int,
        failure_type: FailureType
    ) -> RetryDecision:
        """
        Decide if a failed feature should be retried.

        Decision Logic:
        0. Check user consent (retry feature disabled → block)
        1. Check global retry limit (max total retries → block)
        2. Check circuit breaker (5 consecutive failures → block)
        3. Check failure type (permanent → block)
        4. Check per-feature retry count (3 retries → block)
        5. If all checks pass → allow retry

        Args:
            feature_index: Index of failed feature
            failure_type: Classification of failure (transient/permanent)

        Returns:
            RetryDecision with should_retry flag and reason

        Examples:
            >>> manager = BatchRetryManager("batch-123")
            >>> decision = manager.should_retry_feature(0, FailureType.TRANSIENT)
            >>> if decision.should_retry:
            ...     # Retry the feature
            ...     pass
        """
        retry_count = self.get_retry_count(feature_index)

        # 0. Check user consent (highest priority - respect user choice)
        if not batch_retry_consent.is_retry_enabled():
            return RetryDecision(
                should_retry=False,
                reason="consent_not_given",
                retry_count=retry_count
            )

        # 1. Check global retry limit (highest priority - hard limit)
        if self.state.global_retry_count >= MAX_TOTAL_RETRIES:
            return RetryDecision(
                should_retry=False,
                reason="global_retry_limit_reached",
                retry_count=retry_count
            )

        # 2. Check circuit breaker
        if self.check_circuit_breaker():
            return RetryDecision(
                should_retry=False,
                reason="circuit_breaker_open",
                retry_count=retry_count
            )

        # 3. Check failure type (permanent errors not retried)
        if failure_type == FailureType.PERMANENT:
            return RetryDecision(
                should_retry=False,
                reason="permanent_failure",
                retry_count=retry_count
            )

        # 4. Check per-feature retry limit
        if retry_count >= MAX_RETRIES_PER_FEATURE:
            return RetryDecision(
                should_retry=False,
                reason="max_retries_reached",
                retry_count=retry_count
            )

        # All checks passed - allow retry
        return RetryDecision(
            should_retry=True,
            reason="under_retry_limit",
            retry_count=retry_count
        )


# =============================================================================
# Convenience Functions
# =============================================================================

def should_retry_feature(
    batch_id: str,
    feature_index: int,
    failure_type: FailureType,
    state_dir: Optional[Path] = None
) -> RetryDecision:
    """
    Convenience function to check if feature should be retried.

    Args:
        batch_id: Unique batch identifier
        feature_index: Index of failed feature
        failure_type: Classification of failure
        state_dir: Directory for state files (default: ./.claude)

    Returns:
        RetryDecision with should_retry flag and reason
    """
    manager = BatchRetryManager(batch_id, state_dir)
    return manager.should_retry_feature(feature_index, failure_type)


def record_retry_attempt(
    batch_id: str,
    feature_index: int,
    error_message: str,
    feature_name: str = "",
    state_dir: Optional[Path] = None
) -> None:
    """
    Convenience function to record retry attempt.

    Args:
        batch_id: Unique batch identifier
        feature_index: Index of feature being retried
        error_message: Error message from failed attempt
        feature_name: Name of feature (optional, for audit logging)
        state_dir: Directory for state files (default: ./.claude)
    """
    manager = BatchRetryManager(batch_id, state_dir)
    manager.record_retry_attempt(feature_index, error_message, feature_name)


def check_circuit_breaker(
    batch_id: str,
    state_dir: Optional[Path] = None
) -> bool:
    """
    Convenience function to check circuit breaker status.

    Args:
        batch_id: Unique batch identifier
        state_dir: Directory for state files (default: ./.claude)

    Returns:
        True if circuit breaker is open, False otherwise
    """
    manager = BatchRetryManager(batch_id, state_dir)
    return manager.check_circuit_breaker()


def get_retry_count(
    batch_id: str,
    feature_index: int,
    state_dir: Optional[Path] = None
) -> int:
    """
    Convenience function to get retry count for feature.

    Args:
        batch_id: Unique batch identifier
        feature_index: Index of feature
        state_dir: Directory for state files (default: ./.claude)

    Returns:
        Number of retry attempts
    """
    manager = BatchRetryManager(batch_id, state_dir)
    return manager.get_retry_count(feature_index)


def reset_circuit_breaker(
    batch_id: str,
    state_dir: Optional[Path] = None
) -> None:
    """
    Convenience function to reset circuit breaker.

    Args:
        batch_id: Unique batch identifier
        state_dir: Directory for state files (default: ./.claude)
    """
    manager = BatchRetryManager(batch_id, state_dir)
    manager.reset_circuit_breaker()


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    "BatchRetryManager",
    "RetryDecision",
    "CircuitBreakerError",
    "should_retry_feature",
    "record_retry_attempt",
    "check_circuit_breaker",
    "get_retry_count",
    "reset_circuit_breaker",
    "MAX_RETRIES_PER_FEATURE",
    "MAX_TOTAL_RETRIES",
    "CIRCUIT_BREAKER_THRESHOLD",
]
