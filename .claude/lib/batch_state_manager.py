#!/usr/bin/env python3
"""
Batch State Manager - State-based tracking for /batch-implement command.

Manages persistent state for batch feature processing. Enables crash recovery,
resume functionality, and multi-feature batch processing.

DESIGN (v3.34.0): Compaction-resilient - all state is externalized (batch_state.json,
git commits, GitHub issues). Batches survive Claude Code's auto-compaction because
each feature bootstraps fresh from external state, not conversation memory.

NOTE: Context clearing functions (should_clear_context, pause_batch_for_clear,
get_clear_notification_message) are DEPRECATED. Kept for backward compatibility only.

Key Features:
1. Persistent state storage (.claude/batch_state.json)
2. Progress tracking (completed, failed, current feature)
3. Atomic writes with file locking
4. Security validations (CWE-22 path traversal, CWE-59 symlinks)
5. Crash recovery and resume

State Structure:
    {
        "batch_id": "batch-20251116-123456",
        "features_file": "/path/to/features.txt",
        "total_features": 10,
        "features": ["feature 1", "feature 2", ...],
        "current_index": 3,
        "completed_features": [0, 1, 2],
        "failed_features": [
            {"feature_index": 5, "error_message": "Tests failed", "timestamp": "..."}
        ],
        "context_token_estimate": 145000,
        "auto_clear_count": 2,
        "auto_clear_events": [
            {"feature_index": 2, "tokens_before": 155000, "timestamp": "..."},
            {"feature_index": 5, "tokens_before": 152000, "timestamp": "..."}
        ],
        "created_at": "2025-11-16T10:00:00Z",
        "updated_at": "2025-11-16T14:30:00Z",
        "status": "in_progress"  # in_progress, completed, failed
    }

Workflow:
    1. /batch-implement reads features.txt
    2. create_batch_state() creates initial state
    3. For each feature:
       a. Process with /auto-implement
       b. update_batch_progress() increments current_index
       c. should_auto_clear() checks if threshold exceeded
       d. If yes: record_auto_clear_event() → /clear → resume
    4. cleanup_batch_state() removes state file on completion

Usage:
    from batch_state_manager import (
        create_batch_state,
        load_batch_state,
        save_batch_state,
        update_batch_progress,
        record_auto_clear_event,
        should_auto_clear,
        get_next_pending_feature,
        cleanup_batch_state,
    )
    from path_utils import get_batch_state_file

    # Create new batch
    state = create_batch_state("/path/to/features.txt", ["feature 1", "feature 2"])
    save_batch_state(get_batch_state_file(), state)

    # Process features
    while True:
        next_feature = get_next_pending_feature(state)
        if next_feature is None:
            break

        # Process feature...

        # Update progress
        update_batch_progress(get_batch_state_file(), state.current_index, "completed", 10000)

        # Check auto-clear
        state = load_batch_state(get_batch_state_file())
        if should_auto_clear(state):
            record_auto_clear_event(get_batch_state_file(), state.current_index, state.context_token_estimate)
            # /clear command...
            state = load_batch_state(get_batch_state_file())

    # Cleanup
    cleanup_batch_state(get_batch_state_file())

Date: 2025-11-16
Issue: #76 (State-based Auto-Clearing for /batch-implement)
Agent: implementer
Phase: TDD Green (making tests pass)

See error-handling-patterns skill for exception hierarchy and error handling best practices.


Design Patterns:
    See library-design-patterns skill for standardized design patterns.
    See state-management-patterns skill for standardized design patterns.
"""

import json
import os
import tempfile
import threading
import warnings
from functools import wraps
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# Import security utilities for path validation
import sys
sys.path.insert(0, str(Path(__file__).parent))
from security_utils import validate_path, audit_log
from path_utils import get_batch_state_file

# Import sanitization functions
try:
    from failure_classifier import sanitize_feature_name
except ImportError:
    # Fallback for tests
    def sanitize_feature_name(name: str) -> str:
        """Fallback sanitization."""
        return name.replace("\n", " ").replace("\r", " ")

# =============================================================================
# Decorators
# =============================================================================


def deprecated(func):
    """Mark function as deprecated with warning.

    Decorator that emits a DeprecationWarning when the decorated function is called.
    Used for context clearing functions that are no longer needed due to Claude Code's
    automatic context management.

    Args:
        func: Function to deprecate

    Returns:
        Wrapped function that emits deprecation warning
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        warnings.warn(
            f"{func.__name__} is deprecated but still functional. Hybrid pause/resume workflow still uses these functions.",
            DeprecationWarning,
            stacklevel=2
        )
        return func(*args, **kwargs)
    return wrapper


# =============================================================================
# Constants
# =============================================================================

# Default state file location (dynamically resolved from PROJECT_ROOT - Issue #79)
# This fixes hardcoded Path(".claude/batch_state.json") which failed from subdirectories
# WARNING: This evaluates at module import time. For testing with mock project roots,
# use get_default_state_file() function instead (evaluates lazily).
try:
    DEFAULT_STATE_FILE = get_batch_state_file()
except FileNotFoundError:
    # Fallback for edge cases (e.g., running outside a git repo)
    # This maintains backward compatibility
    DEFAULT_STATE_FILE = Path(".claude/batch_state.json")

def get_default_state_file():
    """Get default state file path (lazy evaluation - use in tests).

    This is a function (not a constant) to support testing scenarios where
    the project root might change between test cases.

    For production code, use DEFAULT_STATE_FILE constant for performance.
    For tests, use this function for correct behavior with mock project roots.

    Returns:
        Path to default batch state file (PROJECT_ROOT/.claude/batch_state.json)
    """
    try:
        return get_batch_state_file()
    except FileNotFoundError:
        # Fallback for edge cases (e.g., running outside a git repo)
        # This maintains backward compatibility
        return Path(".claude/batch_state.json")

# Context token threshold (DEPRECATED - v3.34.0)
# No longer used: Compaction-resilient design survives auto-compaction via externalized state.
# Kept for backward compatibility with deprecated should_clear_context() function.
CONTEXT_THRESHOLD = 150000

# File lock timeout (seconds)
LOCK_TIMEOUT = 30

# =============================================================================
# Exceptions
# =============================================================================


class BatchStateError(Exception):
    """Base exception for batch state operations."""
    pass


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class BatchState:
    """Batch processing state.

    Attributes:
        batch_id: Unique batch identifier
        features_file: Path to features file
        total_features: Total number of features in batch
        features: List of feature descriptions
        current_index: Index of current feature being processed
        completed_features: List of completed feature indices
        failed_features: List of failed feature records
        context_token_estimate: Estimated context token count
        auto_clear_count: Number of auto-clear events
        auto_clear_events: List of auto-clear event records
        created_at: ISO 8601 timestamp of batch creation
        updated_at: ISO 8601 timestamp of last update
        status: Batch status (in_progress/running, paused, completed, failed)
        issue_numbers: Optional list of GitHub issue numbers (for --issues flag)
        source_type: Source type ("file" or "issues")
        state_file: Path to state file
        context_tokens_before_clear: Token count before clear (for paused batches, deprecated)
        paused_at_feature_index: Feature index where batch was paused (deprecated)
        retry_attempts: Dict mapping feature index to retry count (Issue #89)
        git_operations: Dict mapping feature index to git operation results (Issue #93)
            Structure: {feature_index: {operation_type: {success, sha, branch, ...}}}
            Example: {0: {"commit": {"success": True, "sha": "abc123", "branch": "feature/test"}}}
    """
    batch_id: str
    features_file: str
    total_features: int
    features: List[str]
    current_index: int = 0
    completed_features: List[int] = field(default_factory=list)
    failed_features: List[Dict[str, Any]] = field(default_factory=list)
    context_token_estimate: int = 0
    auto_clear_count: int = 0
    auto_clear_events: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    status: str = "in_progress"
    issue_numbers: Optional[List[int]] = None
    source_type: str = "file"
    state_file: str = ""
    context_tokens_before_clear: Optional[int] = None
    paused_at_feature_index: Optional[int] = None
    retry_attempts: Dict[int, int] = field(default_factory=dict)  # Issue #89: Track retry counts per feature
    git_operations: Dict[int, Dict[str, Any]] = field(default_factory=dict)  # Issue #93: Track git operations per feature
    feature_order: List[int] = field(default_factory=list)  # Issue #157: Optimized execution order
    feature_dependencies: Dict[int, List[int]] = field(default_factory=dict)  # Issue #157: Dependency graph
    analysis_metadata: Dict[str, Any] = field(default_factory=dict)  # Issue #157: Analysis info (stats, timing, etc.)
    # Compaction-resilience: Workflow methodology survives context summarization
    workflow_mode: str = "auto-implement"  # "auto-implement" or "direct" - tells Claude HOW to process features
    workflow_reminder: str = "Use /auto-implement for each feature. Do NOT implement directly."  # Reinjects methodology after compaction

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


# Thread-safe file lock
_file_locks: Dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def audit_log_security_event(event_type: str, details: Dict[str, Any]) -> None:
    """Log security event to audit log.

    This is a wrapper around security_utils.audit_log for security events.

    Args:
        event_type: Type of security event
        details: Event details
    """
    audit_log(event_type, "security", details)


def _get_file_lock(file_path: Path) -> threading.RLock:
    """Get or create thread-safe reentrant lock for file.

    Args:
        file_path: Path to file

    Returns:
        Threading reentrant lock for file (allows same thread to acquire multiple times)
    """
    file_key = str(file_path.resolve())
    with _locks_lock:
        if file_key not in _file_locks:
            _file_locks[file_key] = threading.RLock()  # Reentrant lock
        return _file_locks[file_key]


# =============================================================================
# State Creation
# =============================================================================


def create_batch_state(
    features_file_or_features: Optional[str | List[str]] = None,
    features_or_none: Optional[List[str]] = None,
    issue_numbers: Optional[List[int]] = None,
    source_type: str = "file",
    state_file: Optional[str] = None,
    *,
    features: Optional[List[str]] = None,  # Keyword-only for new calling style
    features_file: Optional[str] = None,  # Keyword-only for explicit features_file
    batch_id: Optional[str] = None,  # Optional custom batch ID
) -> BatchState:
    """Create new batch state.

    Supports two calling styles for backward compatibility:
    1. Old style (positional): create_batch_state(features_file, features)
    2. New style (keyword): create_batch_state(features=..., state_file=..., issue_numbers=...)

    Args:
        features_file_or_features: Features file path (old style) OR features list (new style detection)
        features_or_none: Features list (old style) or None (new style)
        issue_numbers: Optional list of GitHub issue numbers (for --issues flag)
        source_type: Source type ("file" or "issues")
        state_file: Optional path to state file
        features: Features list (keyword-only, for new calling style)
        batch_id: Optional custom batch ID (keyword-only)

    Returns:
        Newly created BatchState

    Raises:
        BatchStateError: If features list is empty or features_file path is invalid

    Examples:
        Old style (backward compatible):
        >>> state = create_batch_state("/path/to/features.txt", ["feature 1", "feature 2"])
        >>> state.source_type
        'file'

        New style (--issues flag):
        >>> state = create_batch_state(
        ...     features=["Issue #72: Add logging"],
        ...     issue_numbers=[72],
        ...     source_type="issues",
        ...     state_file="/path/to/state.json"
        ... )
        >>> state.issue_numbers
        [72]
    """
    # Detect calling style
    if features is not None:
        # New style: features passed as keyword argument
        features_list = features
        # Use explicit features_file keyword if provided, otherwise empty
        features_file_path = features_file if features_file is not None else ""
    elif features_file_or_features is None and features_or_none is None:
        # Neither positional argument provided - must use keyword 'features'
        raise BatchStateError(
            "Invalid arguments. Use either:\n"
            "  create_batch_state(features_file, features)  # Old style\n"
            "  create_batch_state(features=..., state_file=..., issue_numbers=...)  # New style"
        )
    elif isinstance(features_file_or_features, list):
        # Ambiguous: first arg is a list (could be new style without keyword)
        # Assume new style if features_or_none is None
        if features_or_none is None:
            features_list = features_file_or_features
            features_file_path = ""
        else:
            # Very unlikely case: both are lists?
            raise BatchStateError("Ambiguous arguments: both features_file and features appear to be lists")
    elif isinstance(features_file_or_features, str) and features_or_none is not None:
        # Old style: create_batch_state(features_file, features)
        features_file_path = features_file_or_features
        features_list = features_or_none
    else:
        raise BatchStateError(
            "Invalid arguments. Use either:\n"
            "  create_batch_state(features_file, features)  # Old style\n"
            "  create_batch_state(features=..., state_file=..., issue_numbers=...)  # New style"
        )

    if not features_list:
        raise BatchStateError("Cannot create batch state with no features")

    # Sanitize feature names (CWE-117 log injection, CWE-22 path traversal)
    sanitized_features = [sanitize_feature_name(f) for f in features_list]

    # Validate features_file path (security) - check for obvious path traversal
    # Note: features_file is just metadata, not actively accessed
    if features_file_path and (".." in features_file_path or features_file_path.startswith("/tmp/../../")):
        raise BatchStateError(f"Invalid features file path: path traversal detected")

    # Validate batch_id for path traversal (CWE-22)
    if batch_id and (".." in batch_id or "/" in batch_id or "\\" in batch_id):
        raise BatchStateError(
            f"Invalid batch_id: contains path traversal or directory separators. "
            f"batch_id must be a simple identifier without path components."
        )

    # Generate unique batch ID with timestamp (including microseconds for uniqueness)
    # Use provided batch_id if given, otherwise generate one
    if not batch_id:
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
        batch_id = f"batch-{timestamp}"

    # Create timestamps
    now = datetime.utcnow().isoformat() + "Z"

    return BatchState(
        batch_id=batch_id,
        features_file=features_file_path,
        total_features=len(sanitized_features),
        features=sanitized_features,
        current_index=0,
        completed_features=[],
        failed_features=[],
        context_token_estimate=0,
        auto_clear_count=0,
        auto_clear_events=[],
        created_at=now,
        updated_at=now,
        status="in_progress",
        issue_numbers=issue_numbers,
        source_type=source_type,
        state_file=state_file or "",
        context_tokens_before_clear=None,
        paused_at_feature_index=None,
    )


# =============================================================================
# State Persistence
# =============================================================================


def save_batch_state(state_file: Path | str, state: BatchState) -> None:
    """Save batch state to JSON file (atomic write).

    Uses atomic write pattern (temp file + rename) to prevent corruption.
    File permissions set to 0o600 (owner read/write only).

    Args:
        state_file: Path to state file
        state: Batch state to save

    Raises:
        BatchStateError: If save fails
        ValueError: If path validation fails (CWE-22, CWE-59)

    Security:
        - Validates path with security_utils.validate_path()
        - Rejects symlinks (CWE-59)
        - Prevents path traversal (CWE-22)
        - Atomic write (temp file + rename)
        - File permissions 0o600 (owner only)
        - Audit logging

    Atomic Write Design:
    ====================
    1. CREATE: tempfile.mkstemp() creates .tmp file in same directory
    2. WRITE: JSON data written to .tmp file
    3. RENAME: temp_path.replace(target) atomically renames file

    Failure Scenarios:
    ==================
    - Process crash during write: Temp file left, target unchanged
    - Process crash during rename: Atomic, so target is old or new (not partial)
    - Concurrent writes: Each gets unique temp file (last write wins)

    Example:
        >>> from path_utils import get_batch_state_file
        >>> state = create_batch_state("/path/to/features.txt", ["feature 1"])
        >>> save_batch_state(get_batch_state_file(), state)
    """
    # Convert to Path
    state_file = Path(state_file)

    # Resolve relative paths from PROJECT_ROOT (Issue #79)
    # This ensures "custom/state.json" → PROJECT_ROOT/custom/state.json
    if not state_file.is_absolute():
        from path_utils import get_project_root
        try:
            project_root = get_project_root(use_cache=False)
            state_file = project_root / state_file
        except FileNotFoundError:
            # Fallback: if no project root, use cwd (backward compatibility)
            pass

    # Validate path (security)
    try:
        state_file = validate_path(state_file, "batch state file", allow_missing=True)
    except ValueError as e:
        audit_log("batch_state_save", "error", {
            "error": str(e),
            "path": str(state_file),
        })
        raise BatchStateError(str(e))

    # Update timestamp
    state.updated_at = datetime.utcnow().isoformat() + "Z"

    # Acquire file lock
    lock = _get_file_lock(state_file)
    with lock:
        try:
            # Ensure parent directory exists
            state_file.parent.mkdir(parents=True, exist_ok=True)

            # Atomic write: temp file + rename
            temp_fd, temp_path_str = tempfile.mkstemp(
                dir=state_file.parent,
                prefix=".batch_state_",
                suffix=".tmp"
            )
            temp_path = Path(temp_path_str)

            try:
                # Write JSON to temp file
                json_data = json.dumps(state.to_dict(), indent=2)
                os.write(temp_fd, json_data.encode('utf-8'))
                os.close(temp_fd)

                # Set permissions (owner read/write only)
                temp_path.chmod(0o600)

                # Atomic rename
                temp_path.replace(state_file)

                # Audit log
                audit_log("batch_state_save", "success", {
                    "batch_id": state.batch_id,
                    "path": str(state_file),
                    "features_count": state.total_features,
                })

            except Exception as e:
                # Cleanup temp file on error
                try:
                    os.close(temp_fd)
                except:
                    pass
                try:
                    temp_path.unlink()
                except:
                    pass
                raise

        except OSError as e:
            audit_log("batch_state_save", "error", {
                "error": str(e),
                "path": str(state_file),
            })
            # Provide more specific error messages
            error_msg = str(e).lower()
            if "space" in error_msg or "disk full" in error_msg:
                raise BatchStateError(f"Disk space error while saving batch state: {e}")
            elif "permission" in error_msg:
                raise BatchStateError(f"Permission error while saving batch state: {e}")
            else:
                raise BatchStateError(f"Failed to save batch state: {e}")


def load_batch_state(state_file: Path | str) -> BatchState:
    """Load batch state from JSON file.

    Args:
        state_file: Path to state file

    Returns:
        Loaded BatchState

    Raises:
        BatchStateError: If load fails or file doesn't exist
        ValueError: If path validation fails (CWE-22, CWE-59)

    Security:
        - Validates path with security_utils.validate_path()
        - Rejects symlinks (CWE-59)
        - Prevents path traversal (CWE-22)
        - Graceful degradation on corrupted JSON
        - Audit logging

    Example:
        >>> from path_utils import get_batch_state_file
        >>> state = load_batch_state(get_batch_state_file())
        >>> state.batch_id
        'batch-20251116-123456'
    """
    # Convert to Path
    state_file = Path(state_file)

    # Resolve relative paths from PROJECT_ROOT (Issue #79)
    # This ensures "custom/state.json" → PROJECT_ROOT/custom/state.json
    if not state_file.is_absolute():
        from path_utils import get_project_root
        try:
            project_root = get_project_root(use_cache=False)
            state_file = project_root / state_file
        except FileNotFoundError:
            # Fallback: if no project root, use cwd (backward compatibility)
            pass

    # Validate path (security)
    try:
        state_file = validate_path(state_file, "batch state file", allow_missing=False)
    except ValueError as e:
        audit_log("batch_state_load", "error", {
            "error": str(e),
            "path": str(state_file),
        })
        raise BatchStateError(str(e))

    # Check if file exists
    if not state_file.exists():
        raise BatchStateError(f"Batch state file not found: {state_file}")

    # Acquire file lock
    lock = _get_file_lock(state_file)
    with lock:
        try:
            # Read JSON
            with open(state_file, 'r') as f:
                data = json.load(f)

            # Validate required fields
            required_fields = [
                "batch_id", "features_file", "total_features", "features",
                "current_index", "status"
            ]
            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                raise BatchStateError(f"Missing required fields: {missing_fields}")

            # Backward compatibility: Add default values for new fields (Issue #77, #88)
            # Old state files (pre-v3.23.0) don't have issue_numbers, source_type, state_file
            if 'issue_numbers' not in data:
                data['issue_numbers'] = None
            if 'source_type' not in data:
                data['source_type'] = 'file'
            if 'state_file' not in data:
                data['state_file'] = str(state_file)
            # Issue #88: Deprecated fields (for backward compatibility with old state files)
            if 'context_tokens_before_clear' not in data:
                data['context_tokens_before_clear'] = None
            if 'paused_at_feature_index' not in data:
                data['paused_at_feature_index'] = None
            # Issue #89: Retry tracking (for backward compatibility with old state files)
            if 'retry_attempts' not in data:
                data['retry_attempts'] = {}
            else:
                # JSON converts integer keys to strings, convert back to int
                data['retry_attempts'] = {int(k): v for k, v in data['retry_attempts'].items()}

            # Issue #93: Git operations tracking (for backward compatibility with old state files)
            if 'git_operations' not in data:
                data['git_operations'] = {}
            else:
                # JSON converts integer keys to strings, convert back to int
                data['git_operations'] = {int(k): v for k, v in data['git_operations'].items()}

            # Compaction-resilience: workflow_mode and workflow_reminder (for backward compatibility)
            if 'workflow_mode' not in data:
                data['workflow_mode'] = 'auto-implement'
            if 'workflow_reminder' not in data:
                data['workflow_reminder'] = 'Use /auto-implement for each feature. Do NOT implement directly.'

            # Backward compatibility: Accept both 'running' and 'in_progress' as equivalent
            # (Both are valid active states)

            # Create BatchState from data
            state = BatchState(**data)

            # Audit log
            audit_log("batch_state_load", "success", {
                "batch_id": state.batch_id,
                "path": str(state_file),
            })

            return state

        except json.JSONDecodeError as e:
            audit_log("batch_state_load", "error", {
                "error": f"Corrupted JSON: {e}",
                "path": str(state_file),
            })
            raise BatchStateError(f"Corrupted batch state file: {e}")
        except OSError as e:
            audit_log("batch_state_load", "error", {
                "error": str(e),
                "path": str(state_file),
            })
            # Provide more specific error messages
            error_msg = str(e).lower()
            if "permission" in error_msg:
                raise BatchStateError(f"Permission error while loading batch state: {e}")
            else:
                raise BatchStateError(f"Failed to load batch state: {e}")


# =============================================================================
# State Updates
# =============================================================================


def update_batch_progress(
    state_file: Path | str,
    feature_index: int,
    status: str,
    context_token_delta: int = 0,
    error_message: Optional[str] = None,
    token_delta: Optional[int] = None,  # Backward compatibility alias
) -> None:
    """Update batch progress after processing a feature.

    This function is thread-safe - it uses file locking to serialize concurrent updates.
    Multiple threads can call this function simultaneously with different feature indices.

    Args:
        state_file: Path to state file
        feature_index: Index of processed feature
        status: Feature status ("completed" or "failed")
        context_token_delta: Tokens added during feature processing
        error_message: Error message if status is "failed"
        token_delta: Alias for context_token_delta (backward compatibility)

    Raises:
        BatchStateError: If update fails
        ValueError: If feature_index is invalid

    Example:
        >>> from path_utils import get_batch_state_file
        >>> update_batch_progress(
        ...     state_file=get_batch_state_file(),
        ...     feature_index=0,
        ...     status="completed",
        ...     context_token_delta=5000,
        ... )
    """
    # Backward compatibility: support both parameter names
    if token_delta is not None:
        context_token_delta = token_delta
    # Convert to Path
    state_file_path = Path(state_file)

    # Acquire file lock for atomic read-modify-write
    # Using RLock (reentrant) so we can call load_batch_state/save_batch_state
    # which also acquire the same lock
    lock = _get_file_lock(state_file_path)
    with lock:
        # Load current state (lock is reentrant, so this is safe)
        state = load_batch_state(state_file)

        # Validate feature index
        if feature_index < 0 or feature_index >= state.total_features:
            raise BatchStateError(f"Invalid feature index: {feature_index} (total: {state.total_features})")

        # Update state based on status
        if status == "completed":
            if feature_index not in state.completed_features:
                state.completed_features.append(feature_index)
        elif status == "failed":
            failure_record = {
                "feature_index": feature_index,
                "error_message": error_message or "Unknown error",
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
            state.failed_features.append(failure_record)
        else:
            raise ValueError(f"Invalid status: {status} (must be 'completed' or 'failed')")

        # Update context token estimate
        state.context_token_estimate += context_token_delta

        # Update current_index to max of (current, feature_index + 1)
        # This ensures we track progress even with concurrent updates
        state.current_index = max(state.current_index, feature_index + 1)

        # Update status if all features processed
        if state.current_index >= state.total_features:
            state.status = "completed"

        # Save updated state (lock is reentrant, so this is safe)
        save_batch_state(state_file, state)


def record_auto_clear_event(
    state_file: Path | str,
    feature_index: int,
    context_tokens_before_clear: int,
) -> None:
    """Record auto-clear event in batch state.

    Args:
        state_file: Path to state file
        feature_index: Index of feature that triggered auto-clear
        context_tokens_before_clear: Token count before /clear

    Raises:
        BatchStateError: If record fails

    Example:
        >>> from path_utils import get_batch_state_file
        >>> record_auto_clear_event(
        ...     state_file=get_batch_state_file(),
        ...     feature_index=2,
        ...     context_tokens_before_clear=155000,
        ... )
    """
    # Load current state
    state = load_batch_state(state_file)

    # Create auto-clear event record
    event = {
        "feature_index": feature_index,
        "context_tokens_before_clear": context_tokens_before_clear,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    # Update state
    state.auto_clear_events.append(event)
    state.auto_clear_count += 1

    # Reset context token estimate after clear
    state.context_token_estimate = 0

    # Save updated state
    save_batch_state(state_file, state)

    # Audit log
    audit_log("batch_auto_clear", "success", {
        "batch_id": state.batch_id,
        "feature_index": feature_index,
        "tokens_before": context_tokens_before_clear,
        "clear_count": state.auto_clear_count,
    })


# =============================================================================
# State Queries
# =============================================================================


def should_auto_clear(state: BatchState) -> bool:
    """Check if context should be auto-cleared.

    Args:
        state: Batch state

    Returns:
        True if context token estimate exceeds threshold

    Example:
        >>> from path_utils import get_batch_state_file
        >>> state = load_batch_state(get_batch_state_file())
        >>> if should_auto_clear(state):
        ...     # Trigger /clear
        ...     pass
    """
    return state.context_token_estimate >= CONTEXT_THRESHOLD


@deprecated
def should_clear_context(state: BatchState) -> bool:
    """Check if context should be cleared (DEPRECATED).

    DEPRECATED: Claude Code manages context automatically with its 200K token budget.
    No manual clearing needed. This function is kept for backward compatibility only.

    This is the user-facing function for the hybrid clear approach.
    Returns True when context reaches 150K token threshold.

    Args:
        state: Batch state

    Returns:
        True if context token estimate >= 150K tokens (but clearing is no longer needed)

    Example:
        >>> from path_utils import get_batch_state_file
        >>> state = load_batch_state(get_batch_state_file())
        >>> if should_clear_context(state):  # Will emit DeprecationWarning
        ...     # No action needed - Claude Code handles context automatically
        ...     pass
    """
    return state.context_token_estimate >= CONTEXT_THRESHOLD


def estimate_context_tokens(text: str) -> int:
    """Estimate token count for text (conservative approach).

    Uses a conservative estimate of 1 token ≈ 4 characters.
    This is intentionally conservative to avoid underestimating.

    Args:
        text: Text to estimate tokens for

    Returns:
        Estimated token count (chars / 4)

    Example:
        >>> text = "Hello world! " * 100
        >>> tokens = estimate_context_tokens(text)
        >>> tokens
        325
    """
    if not text:
        return 0

    # Conservative estimate: 1 token ≈ 4 characters
    # This is intentionally conservative to trigger clearing before hitting actual limit
    return len(text) // 4


@deprecated
def get_clear_notification_message(
    batch_id_or_state: str | BatchState,
    feature_index: Optional[int] = None,
    tokens_before_clear: Optional[int] = None,
) -> str:
    """Format user notification message for context clearing (DEPRECATED).

    DEPRECATED: Claude Code manages context automatically with its 200K token budget.
    No manual clearing needed. This function is kept for backward compatibility only.

    Creates a clear, actionable message instructing the user to:
    1. Manually run /clear (NO LONGER NEEDED)
    2. Resume batch with /batch-implement --resume <batch-id> (NO LONGER NEEDED)

    Args:
        batch_id_or_state: Batch ID (str) or BatchState object (backward compatible)
        feature_index: Current feature index (optional, for old API)
        tokens_before_clear: Token count before clear (optional, for old API)

    Returns:
        Formatted notification message (multi-line, readable)

    Example:
        >>> # Old API (batch ID, feature index, tokens)
        >>> message = get_clear_notification_message("batch-123", 5, 160000)

        >>> # New API (BatchState object)
        >>> from path_utils import get_batch_state_file
        >>> state = load_batch_state(get_batch_state_file())
        >>> message = get_clear_notification_message(state)
    """
    # Detect calling style
    if isinstance(batch_id_or_state, str):
        # Old API: get_clear_notification_message(batch_id, feature_index, tokens)
        batch_id = batch_id_or_state
        current_index = feature_index if feature_index is not None else 0
        context_tokens = tokens_before_clear if tokens_before_clear is not None else 0
        total_features = 10  # Default assumption for old API
    else:
        # New API: get_clear_notification_message(state)
        state = batch_id_or_state
        batch_id = state.batch_id
        current_index = state.current_index
        context_tokens = state.context_token_estimate
        total_features = state.total_features

    # Calculate progress
    progress_pct = int((current_index / total_features) * 100) if total_features > 0 else 0

    # Format token count (e.g., "155,000" or "155K")
    tokens_formatted = f"{context_tokens:,}"

    message = f"""========================================
CONTEXT LIMIT REACHED
========================================

Current context: {tokens_formatted} tokens (threshold: {CONTEXT_THRESHOLD:,})
Progress: {current_index}/{total_features} features ({progress_pct}%)
Batch ID: {batch_id}

The batch has been paused to prevent context overflow.

NEXT STEPS:
1. Manually run: /clear
2. Resume batch: /batch-implement --resume {batch_id}

The batch will continue from feature {current_index + 1}/{total_features}.
All completed features are saved and will be skipped on resume.

========================================
"""
    return message


@deprecated
def pause_batch_for_clear(
    state_file: Path | str,
    feature_index_or_state: int | BatchState,
    tokens_before_clear: int,
) -> None:
    """Pause batch and prepare for user-triggered context clear (DEPRECATED).

    DEPRECATED: Claude Code manages context automatically with its 200K token budget.
    No manual clearing needed. This function is kept for backward compatibility only.

    This function:
    1. Sets status to "paused" (NO LONGER NEEDED)
    2. Records pause event in auto_clear_events (NO LONGER NEEDED)
    3. Increments auto_clear_count (NO LONGER NEEDED)
    4. Saves state to disk

    After calling this function, the user must manually:
    1. Run /clear (NO LONGER NEEDED)
    2. Run /batch-implement --resume <batch-id> (NO LONGER NEEDED)

    Args:
        state_file: Path to state file
        feature_index_or_state: Feature index (int) or BatchState object (backward compatible)
        tokens_before_clear: Token count before clear

    Raises:
        BatchStateError: If save fails

    Example:
        >>> # Old API (feature index)
        >>> pause_batch_for_clear(state_file, feature_index=2, tokens_before_clear=160000)

        >>> # New API (BatchState object)
        >>> from path_utils import get_batch_state_file
        >>> state = load_batch_state(get_batch_state_file())
        >>> pause_batch_for_clear(state_file, state, state.context_token_estimate)
    """
    # Detect calling style and load state if needed
    if isinstance(feature_index_or_state, int):
        # Old API: pause_batch_for_clear(state_file, feature_index, tokens)
        feature_index = feature_index_or_state
        state = load_batch_state(state_file)
    else:
        # New API: pause_batch_for_clear(state_file, state, tokens)
        state = feature_index_or_state
        feature_index = state.current_index

    # Update state (in-place modification)
    state.status = "paused"
    state.context_tokens_before_clear = tokens_before_clear
    state.paused_at_feature_index = state.current_index

    # Record pause event
    pause_event = {
        "feature_index": state.current_index,
        "context_tokens_before_clear": tokens_before_clear,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    state.auto_clear_events.append(pause_event)
    state.auto_clear_count += 1

    # Persist to disk
    save_batch_state(state_file, state)

    # Audit log
    audit_log("batch_pause_for_clear", "success", {
        "batch_id": state.batch_id,
        "feature_index": state.current_index,
        "tokens_before": tokens_before_clear,
        "pause_count": state.auto_clear_count,
    })


def get_next_pending_feature(state: BatchState) -> Optional[str]:
    """Get next pending feature to process.

    Args:
        state: Batch state

    Returns:
        Next feature description, or None if all features processed

    Example:
        >>> from path_utils import get_batch_state_file
        >>> state = load_batch_state(get_batch_state_file())
        >>> next_feature = get_next_pending_feature(state)
        >>> if next_feature:
        ...     # Process feature
        ...     pass
    """
    if state.current_index >= state.total_features:
        return None
    return state.features[state.current_index]


# =============================================================================
# State Cleanup
# =============================================================================


def cleanup_batch_state(state_file: Path | str) -> None:
    """Remove batch state file safely.

    Args:
        state_file: Path to state file

    Raises:
        BatchStateError: If cleanup fails

    Example:
        >>> from path_utils import get_batch_state_file
        >>> cleanup_batch_state(get_batch_state_file())
    """
    # Convert to Path
    state_file = Path(state_file)

    # Validate path (security)
    try:
        state_file = validate_path(state_file, "batch state file", allow_missing=True)
    except ValueError as e:
        audit_log("batch_state_cleanup", "error", {
            "error": str(e),
            "path": str(state_file),
        })
        raise BatchStateError(str(e))

    # Acquire file lock
    lock = _get_file_lock(state_file)
    with lock:
        try:
            if state_file.exists():
                state_file.unlink()
                audit_log("batch_state_cleanup", "success", {
                    "path": str(state_file),
                })
        except OSError as e:
            audit_log("batch_state_cleanup", "error", {
                "error": str(e),
                "path": str(state_file),
            })
            raise BatchStateError(f"Failed to cleanup batch state: {e}")


# =============================================================================
# Retry Count Tracking (Issue #89)
# =============================================================================

def get_retry_count(state: BatchState, feature_index: int) -> int:
    """
    Get retry count for a specific feature.

    Args:
        state: Batch state
        feature_index: Index of feature

    Returns:
        Number of retry attempts (0 if never retried)

    Examples:
        >>> state = load_batch_state(state_file)
        >>> retry_count = get_retry_count(state, 0)
        >>> print(f"Feature 0 has been retried {retry_count} times")
    """
    return state.retry_attempts.get(feature_index, 0)


def increment_retry_count(state_file: Path | str, feature_index: int) -> None:
    """
    Increment retry count for a feature.

    Thread-safe update using file locking.

    Args:
        state_file: Path to batch state file
        feature_index: Index of feature to increment

    Examples:
        >>> increment_retry_count(state_file, 0)  # Increment retry count for feature 0
    """
    state_path = Path(state_file)

    with _get_file_lock(state_path):
        # Load current state
        state = load_batch_state(state_path)

        # Increment retry count
        current_count = state.retry_attempts.get(feature_index, 0)
        state.retry_attempts[feature_index] = current_count + 1

        # Update timestamp
        state.updated_at = datetime.utcnow().isoformat() + "Z"

        # Save updated state
        save_batch_state(state_path, state)

        # Audit log
        audit_log("retry_count_incremented", "info", {
            "feature_index": feature_index,
            "new_count": state.retry_attempts[feature_index],
        })


def mark_feature_status(
    state_file: Path | str,
    feature_index: int,
    status: str,
    error_message: Optional[str] = None,
    retry_count: Optional[int] = None,
) -> None:
    """
    Mark feature status (completed or failed) with optional retry tracking.

    Thread-safe update using file locking.

    Args:
        state_file: Path to batch state file
        feature_index: Index of feature to mark
        status: Status ("completed" or "failed")
        error_message: Error message if failed
        retry_count: Optional retry count to record

    Examples:
        >>> mark_feature_status(state_file, 0, "completed")
        >>> mark_feature_status(state_file, 1, "failed", "SyntaxError", retry_count=2)
    """
    state_path = Path(state_file)

    with _get_file_lock(state_path):
        # Load current state
        state = load_batch_state(state_path)

        if status == "completed":
            if feature_index not in state.completed_features:
                state.completed_features.append(feature_index)
            # Remove from failed if it was there (retry succeeded)
            state.failed_features = [
                f for f in state.failed_features
                if f.get("feature_index") != feature_index
            ]

        elif status == "failed":
            # Add to failed list if not already there
            if not any(f.get("feature_index") == feature_index for f in state.failed_features):
                failure_record = {
                    "feature_index": feature_index,
                    "error_message": error_message or "Unknown error",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
                if retry_count is not None:
                    failure_record["retry_count"] = retry_count
                state.failed_features.append(failure_record)

        # Update timestamp
        state.updated_at = datetime.utcnow().isoformat() + "Z"

        # Save updated state
        save_batch_state(state_path, state)

        # Audit log
        audit_log("feature_status_updated", "info", {
            "feature_index": feature_index,
            "status": status,
            "retry_count": retry_count,
        })


# =============================================================================
# Git Operations Tracking (Issue #93)
# =============================================================================

def record_git_operation(
    state: BatchState,
    feature_index: int,
    operation: str,
    success: bool,
    commit_sha: Optional[str] = None,
    branch: Optional[str] = None,
    remote: Optional[str] = None,
    pr_number: Optional[int] = None,
    pr_url: Optional[str] = None,
    error_message: Optional[str] = None,
    **kwargs
) -> BatchState:
    """
    Record git operation result for a feature.

    Updates the state object and returns it (immutable pattern).
    For batch workflow, this tracks commit/push/PR operations per feature.

    Args:
        state: Current batch state
        feature_index: Index of feature being processed
        operation: Operation type ('commit', 'push', 'pr')
        success: Whether operation succeeded
        commit_sha: Commit SHA (for commit operations)
        branch: Branch name
        remote: Remote name (for push operations)
        pr_number: PR number (for pr operations)
        pr_url: PR URL (for pr operations)
        error_message: Error message (for failures)
        **kwargs: Additional metadata

    Returns:
        Updated batch state with git operation recorded

    Examples:
        >>> state = load_batch_state(state_file)
        >>> state = record_git_operation(
        ...     state,
        ...     feature_index=0,
        ...     operation='commit',
        ...     success=True,
        ...     commit_sha='abc123',
        ...     branch='feature/test'
        ... )
        >>> save_batch_state(state_file, state)
    """
    # Validate operation type
    valid_operations = ['commit', 'push', 'pr']
    if operation not in valid_operations:
        raise ValueError(f"Invalid operation: {operation}. Must be one of {valid_operations}")

    # Validate feature_index
    if feature_index < 0 or feature_index >= state.total_features:
        raise ValueError(f"Invalid feature_index: {feature_index} (total: {state.total_features})")

    # Initialize feature git_operations if not exists
    if feature_index not in state.git_operations:
        state.git_operations[feature_index] = {}

    # Build operation record
    operation_record = {
        "success": success,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    # Add operation-specific metadata
    if commit_sha:
        operation_record["sha"] = commit_sha
    if branch:
        operation_record["branch"] = branch
    if remote:
        operation_record["remote"] = remote
    if pr_number is not None:
        operation_record["number"] = pr_number
    if pr_url:
        operation_record["url"] = pr_url
    if error_message:
        operation_record["error"] = error_message

    # Add any additional metadata from kwargs
    for key, value in kwargs.items():
        if key not in operation_record:
            operation_record[key] = value

    # Record operation
    state.git_operations[feature_index][operation] = operation_record

    # Update timestamp
    state.updated_at = datetime.utcnow().isoformat() + "Z"

    # Audit log
    audit_log("git_operation_recorded", "info", {
        "batch_id": state.batch_id,
        "feature_index": feature_index,
        "operation": operation,
        "success": success,
    })

    return state


def get_feature_git_status(
    state: BatchState,
    feature_index: int
) -> Optional[Dict[str, Any]]:
    """
    Get git operation status for a feature.

    Args:
        state: Current batch state
        feature_index: Index of feature

    Returns:
        Dict of git operations for feature, or None if no operations

    Examples:
        >>> state = load_batch_state(state_file)
        >>> status = get_feature_git_status(state, 0)
        >>> if status:
        ...     commit = status.get('commit', {})
        ...     if commit.get('success'):
        ...         print(f"Commit: {commit['sha']}")
    """
    return state.git_operations.get(feature_index)


# =============================================================================
# BatchStateManager Class (Backward Compatibility Wrapper)
# =============================================================================


class BatchStateManager:
    """Object-oriented wrapper for batch state functions.

    Provides backward compatibility for code expecting a class-based interface.
    All methods delegate to the functional API defined above.

    Examples:
        >>> manager = BatchStateManager()
        >>> state = manager.create_batch_state(["feature 1", "feature 2"])
        >>> manager.save_batch_state(state)
        >>> loaded = manager.load_batch_state()
    """

    def __init__(self, state_file: Optional[Path] = None):
        """Initialize manager with optional custom state file path.

        Args:
            state_file: Optional custom path for state file.
                       If None, uses default (.claude/batch_state.json)
                       Path is validated for security (CWE-22, CWE-59)

        Raises:
            ValueError: If state_file contains path traversal or is outside project
        """
        self.state_file = state_file if state_file else get_default_state_file()

        # Validate path if provided (security requirement)
        if state_file:
            from security_utils import validate_path
            self.state_file = validate_path(
                Path(state_file),
                "batch state file",
                allow_missing=True
            )

        # Create parent directory if it doesn't exist
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def create_batch_state(
        self,
        features: List[str],
        batch_id: Optional[str] = None,
        issue_numbers: Optional[List[int]] = None
    ) -> BatchState:
        """Create new batch state (delegates to create_batch_state function).

        Args:
            features: List of feature descriptions
            batch_id: Optional custom batch ID
            issue_numbers: Optional list of GitHub issue numbers

        Returns:
            BatchState object
        """
        return create_batch_state(
            features=features,
            state_file=str(self.state_file),
            batch_id=batch_id,
            issue_numbers=issue_numbers
        )

    def create_batch(
        self,
        features: List[str],
        features_file: Optional[str] = None,
        batch_id: Optional[str] = None,
        issue_numbers: Optional[List[int]] = None
    ) -> BatchState:
        """Create new batch state (alias for create_batch_state).

        Args:
            features: List of feature descriptions
            features_file: Optional path to features file (for validation)
            batch_id: Optional custom batch ID
            issue_numbers: Optional list of GitHub issue numbers

        Returns:
            BatchState object

        Note:
            If features_file is provided, it is validated for security but not used
            (features list is the actual source of truth)
        """
        # Validate features_file if provided (security requirement)
        if features_file:
            from security_utils import validate_path
            validate_path(Path(features_file), "features file", allow_missing=True)

        return create_batch_state(
            features=features,
            state_file=str(self.state_file),
            batch_id=batch_id,
            issue_numbers=issue_numbers
        )

    def load_batch_state(self) -> BatchState:
        """Load batch state from file (delegates to load_batch_state function).

        Returns:
            BatchState object
        """
        return load_batch_state(self.state_file)

    def load_state(self) -> BatchState:
        """Alias for load_batch_state() for backward compatibility with tests.

        Returns:
            BatchState object
        """
        return self.load_batch_state()

    def save_batch_state(self, state: BatchState) -> None:
        """Save batch state to file (delegates to save_batch_state function).

        Args:
            state: BatchState object to save
        """
        save_batch_state(self.state_file, state)

    def save_state(self, state: BatchState) -> None:
        """Alias for save_batch_state() for backward compatibility with tests.

        Args:
            state: BatchState object to save
        """
        self.save_batch_state(state)

    def update_batch_progress(
        self,
        feature_index: int,
        status: str,
        tokens_consumed: int = 0
    ) -> None:
        """Update batch progress (delegates to update_batch_progress function).

        Args:
            feature_index: Index of completed feature
            status: "completed" or "failed"
            tokens_consumed: Estimated tokens consumed by this feature
        """
        update_batch_progress(
            self.state_file,
            feature_index,
            status,
            tokens_consumed
        )

    def record_auto_clear_event(
        self,
        feature_index: int,
        tokens_before_clear: int
    ) -> None:
        """Record auto-clear event (delegates to record_auto_clear_event function).

        Args:
            feature_index: Feature index when auto-clear triggered
            tokens_before_clear: Estimated tokens before clearing
        """
        record_auto_clear_event(
            self.state_file,
            feature_index,
            tokens_before_clear
        )

    def should_auto_clear(self) -> bool:
        """Check if auto-clear should trigger (delegates to should_auto_clear function).

        Returns:
            True if context should be cleared
        """
        state = self.load_batch_state()
        return should_auto_clear(state)

    def get_next_pending_feature(self) -> Optional[str]:
        """Get next pending feature (delegates to get_next_pending_feature function).

        Returns:
            Next feature description or None if all complete
        """
        state = self.load_batch_state()
        return get_next_pending_feature(state)

    def cleanup_batch_state(self) -> None:
        """Cleanup batch state file (delegates to cleanup_batch_state function)."""
        cleanup_batch_state(self.state_file)
