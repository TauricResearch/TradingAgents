---
name: state-management-patterns
version: 1.0.0
type: knowledge
description: State persistence patterns for autonomous-dev including JSON persistence, atomic writes, file locking, crash recovery, and state versioning. Use when implementing stateful libraries or features requiring persistent state.
keywords: state, persistence, JSON, atomic, file locking, crash recovery, state versioning, batch state, user state, checkpoint, session tracking
auto_activate: true
allowed-tools: [Read]
---

# State Management Patterns Skill

Standardized state management and persistence patterns for the autonomous-dev plugin ecosystem. Ensures reliable, crash-resistant state persistence across Claude restarts and system failures.

## When This Skill Activates

- Implementing state persistence
- Managing crash recovery
- Handling concurrent state access
- Versioning state schemas
- Tracking batch operations
- Managing user preferences
- Keywords: "state", "persistence", "JSON", "atomic", "crash recovery", "checkpoint"

---

## Core Patterns

### 1. JSON Persistence with Atomic Writes

**Definition**: Store state in JSON files with atomic writes to prevent corruption on crash.

**Pattern**:
```python
import json
from pathlib import Path
from typing import Dict, Any
import tempfile
import os

def save_state_atomic(state: Dict[str, Any], state_file: Path) -> None:
    """Save state with atomic write to prevent corruption.

    Args:
        state: State dictionary to persist
        state_file: Target state file path

    Security:
        - Atomic Write: Prevents partial writes on crash
        - Temp File: Write to temp, then rename (atomic operation)
        - Permissions: Preserves file permissions
    """
    # Write to temporary file first
    temp_fd, temp_path = tempfile.mkstemp(
        dir=state_file.parent,
        prefix=f".{state_file.name}.",
        suffix=".tmp"
    )

    try:
        # Write JSON to temp file
        with os.fdopen(temp_fd, 'w') as f:
            json.dump(state, f, indent=2)

        # Atomic rename (overwrites target)
        os.replace(temp_path, state_file)

    except Exception:
        # Clean up temp file on failure
        if Path(temp_path).exists():
            Path(temp_path).unlink()
        raise
```

**See**: `docs/json-persistence.md`, `examples/batch-state-example.py`

---

### 2. File Locking for Concurrent Access

**Definition**: Use file locks to prevent concurrent modification of state files.

**Pattern**:
```python
import fcntl
import json
from pathlib import Path
from contextlib import contextmanager

@contextmanager
def file_lock(filepath: Path):
    """Acquire exclusive file lock for state file.

    Args:
        filepath: Path to file to lock

    Yields:
        Open file handle with exclusive lock

    Example:
        >>> with file_lock(state_file) as f:
        ...     state = json.load(f)
        ...     state['count'] += 1
        ...     f.seek(0)
        ...     f.truncate()
        ...     json.dump(state, f)
    """
    with filepath.open('r+') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield f
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

**See**: `docs/file-locking.md`, `templates/file-lock-template.py`

---

### 3. Crash Recovery Pattern

**Definition**: Design state to enable recovery after crashes or interruptions.

**Principles**:
- State includes enough context to resume operations
- Progress tracking enables "resume from last checkpoint"
- State validation detects corruption
- Migration paths handle schema changes

**Example**:
```python
@dataclass
class BatchState:
    """Batch processing state with crash recovery support.

    Attributes:
        batch_id: Unique batch identifier
        features: List of all features to process
        current_index: Index of current feature
        completed: List of completed feature names
        failed: List of failed feature names
        created_at: State creation timestamp
        last_updated: Last update timestamp
    """
    batch_id: str
    features: List[str]
    current_index: int = 0
    completed: List[str] = None
    failed: List[str] = None
    created_at: str = None
    last_updated: str = None

    def __post_init__(self):
        if self.completed is None:
            self.completed = []
        if self.failed is None:
            self.failed = []
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        self.last_updated = datetime.now().isoformat()
```

**See**: `docs/crash-recovery.md`, `examples/crash-recovery-example.py`

---

### 4. State Versioning and Migration

**Definition**: Version state schemas to enable graceful upgrades.

**Pattern**:
```python
STATE_VERSION = "2.0.0"

def migrate_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate state from old version to current.

    Args:
        state: State dictionary (any version)

    Returns:
        Migrated state (current version)
    """
    version = state.get("version", "1.0.0")

    if version == "1.0.0":
        # Migrate 1.0.0 → 1.1.0
        state = _migrate_1_0_to_1_1(state)
        version = "1.1.0"

    if version == "1.1.0":
        # Migrate 1.1.0 → 2.0.0
        state = _migrate_1_1_to_2_0(state)
        version = "2.0.0"

    state["version"] = STATE_VERSION
    return state
```

**See**: `docs/state-versioning.md`, `templates/state-manager-template.py`

---

## Real-World Examples

### BatchStateManager Pattern

From `plugins/autonomous-dev/lib/batch_state_manager.py`:

**Features**:
- JSON persistence with atomic writes
- Crash recovery via --resume flag
- Progress tracking (completed/failed features)
- Automatic context clearing at 150K tokens
- State versioning for schema upgrades

**Usage**:
```python
# Create batch state
manager = BatchStateManager.create(["feat1", "feat2", "feat3"])
manager.batch_id  # "batch-20251116-123456"

# Process features
for feature in manager.features:
    if manager.should_clear_context():
        # Clear context at 150K tokens
        manager.record_context_clear()

    try:
        # Process feature
        result = process_feature(feature)
        manager.mark_completed(feature)
    except Exception as e:
        manager.mark_failed(feature, str(e))

    manager.save()  # Atomic write

# Resume after crash
manager = BatchStateManager.load("batch-20251116-123456")
next_feature = manager.get_next_feature()  # Skips completed
```


## Checkpoint Integration (Issue #79)

Agents save checkpoints using the portable pattern:

### Portable Pattern (Works Anywhere)
```python
from pathlib import Path
import sys

# Portable path detection
current = Path.cwd()
while current != current.parent:
    if (current / ".git").exists():
        project_root = current
        break
    current = current.parent

# Add lib to path
lib_path = project_root / "plugins/autonomous-dev/lib"
if lib_path.exists():
    sys.path.insert(0, str(lib_path))
    
    try:
        from agent_tracker import AgentTracker
        success = AgentTracker.save_agent_checkpoint(
            agent_name='my-agent',
            message='Task completed - found 5 patterns',
            tools_used=['Read', 'Grep', 'WebSearch']
        )
        print(f"Checkpoint: {'saved' if success else 'skipped'}")
    except ImportError:
        print("ℹ️ Checkpoint skipped (user project)")
```

### Features
- **Portable**: Works from any directory (user projects, subdirectories, fresh installs)
- **No hardcoded paths**: Uses dynamic project root detection
- **Graceful degradation**: Returns False, doesn't block workflow
- **Security validated**: Path validation (CWE-22), no subprocess (CWE-78)

### Design Patterns
- Progressive Enhancement: Works with or without tracking infrastructure
- Non-blocking: Never raises exceptions
- Two-tier: Library imports instead of subprocess calls

**See**: LIBRARIES.md Section 24 (agent_tracker.py), DEVELOPMENT.md Scenario 2.5, docs/LIBRARIES.md for API

---

## Usage Guidelines

### For Library Authors

When implementing stateful features:

1. **Use JSON persistence** with atomic writes
2. **Add file locking** for concurrent access protection
3. **Design for crash recovery** with resumable state
4. **Version your state** for schema evolution
5. **Validate on load** to detect corruption

### For Claude

When creating or analyzing stateful libraries:

1. **Load this skill** when keywords match ("state", "persistence", etc.)
2. **Follow persistence patterns** for reliability
3. **Implement crash recovery** for long-running operations
4. **Use atomic operations** to prevent corruption
5. **Reference templates** in `templates/` directory

### Token Savings

By centralizing state management patterns in this skill:

- **Before**: ~50 tokens per library for inline state management docs
- **After**: ~10 tokens for skill reference comment
- **Savings**: ~40 tokens per library
- **Total**: ~400 tokens across 10 libraries (4-5% reduction)

---

## Progressive Disclosure

This skill uses Claude Code 2.0+ progressive disclosure architecture:

- **Metadata** (frontmatter): Always loaded (~180 tokens)
- **Full content**: Loaded only when keywords match
- **Result**: Efficient context usage, scales to 100+ skills

When you use terms like "state management", "persistence", "crash recovery", or "atomic writes", Claude Code automatically loads the full skill content.

---

## Templates and Examples

### Templates (reusable code structures)
- `templates/state-manager-template.py`: Complete state manager class
- `templates/atomic-write-template.py`: Atomic write implementation
- `templates/file-lock-template.py`: File locking utilities

### Examples (real implementations)
- `examples/batch-state-example.py`: BatchStateManager pattern
- `examples/user-state-example.py`: UserStateManager pattern
- `examples/crash-recovery-example.py`: Crash recovery demonstration

### Documentation (detailed guides)
- `docs/json-persistence.md`: JSON storage patterns
- `docs/atomic-writes.md`: Atomic write implementation
- `docs/file-locking.md`: Concurrent access protection
- `docs/crash-recovery.md`: Recovery strategies

---

## Cross-References

This skill integrates with other autonomous-dev skills:

- **library-design-patterns**: Two-tier design, progressive enhancement
- **error-handling-patterns**: Exception handling and recovery
- **security-patterns**: File permissions and path validation

**See**: `skills/library-design-patterns/`, `skills/error-handling-patterns/`

---

## Maintenance

This skill should be updated when:

- New state management patterns emerge
- State schema versioning needs change
- Concurrency patterns evolve
- Performance optimizations discovered

**Last Updated**: 2025-11-16 (Phase 8.8 - Initial creation)
**Version**: 1.0.0
