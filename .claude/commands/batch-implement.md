---
name: batch-implement
description: "Execute multiple features sequentially (--issues <nums> or --resume <id>)"
argument_hint: "<features-file> or --issues <issue-numbers> or --resume <batch-id>"
author: Claude
version: 3.34.0
date: 2025-12-13
allowed-tools: [Task, Read, Write, Bash, Grep, Glob]
---

# /batch-implement - Overnight Feature Queue

Process multiple features fully unattended - queue them up, let it run overnight, wake up to completed work. Survives auto-compaction via externalized state.

## Usage

```bash
# Start new batch from file
/batch-implement features.txt

# Start new batch from GitHub issues (requires gh CLI)
/batch-implement --issues 72 73 74

# Continue after crash
/batch-implement --resume <batch-id>
```

**Prerequisites for --issues flag**:
- gh CLI v2.0+ installed (`brew install gh`, `apt install gh`, or `winget install GitHub.cli`)
- Authentication: `gh auth login` (one-time setup)

**State Management** (v3.1.0+):
- Persistent state file: `.claude/batch_state.json`
- Compaction-resilient: Survives auto-compaction via externalized state
- Crash recovery: Continue with `--resume <batch-id>` flag
- Progress tracking: Completed features, failed features, processing history

## Input Formats

### Option 1: File-Based

Plain text file, one feature per line:

```text
# Authentication
Add user login with JWT
Add password reset flow

# API features
Add rate limiting to endpoints
Add API versioning
```

**Rules**:
- One feature per line
- Lines starting with `#` are comments (skipped)
- Empty lines are skipped
- Keep features under 500 characters each

### Option 2: GitHub Issues (NEW in v3.2.0)

Fetch issue titles directly from GitHub:

```bash
/batch-implement --issues 72 73 74
```

**How it works**:
1. Parse issue numbers from arguments
2. Validate issue numbers (positive integers, max 100 issues)
3. Fetch issue titles via gh CLI: `gh issue view <number> --json title`
4. Format as features: "Issue #72: [title from GitHub]"
5. Create batch state with `issue_numbers` and `source_type='issues'`

**Requirements**:
- gh CLI v2.0+ installed and authenticated
- Valid issue numbers in current repository
- Network connectivity to GitHub

**Graceful Degradation**:
- If issue not found: Skip and continue with remaining issues
- If gh CLI not installed: Error message with installation instructions
- If authentication missing: Error message with `gh auth login` instructions

**Mutually Exclusive**: Cannot use both `<file>` and `--issues` in same command

## How It Works

**State-based workflow** (v3.1.0+):

1. Read features.txt
2. Parse features (skip comments, empty lines, duplicates)
3. **Create batch state** → Save to `.claude/batch_state.json`
4. For each feature:
   - `/auto-implement {feature}`
   - Update batch state (mark feature complete)
   - Next feature
5. Cleanup state file on success

**Compaction-Resilient Design**: All critical state is externalized (batch_state.json, git commits, GitHub issues, codebase). If Claude Code auto-compacts during long batches, processing continues seamlessly - each feature bootstraps fresh from external state, not conversation memory. Use `--resume` only for crash recovery.

**Crash Recovery**: If batch is interrupted:
- State file persists: `.claude/batch_state.json`
- Contains: completed features, current index, failed features, processing history
- Continue: `/batch-implement --resume <batch-id>`
- System automatically skips completed features and continues from current index

**State File Example** (File-based):
```json
{
  "batch_id": "batch-20251116-123456",
  "features_file": "/path/to/features.txt",
  "total_features": 10,
  "current_index": 3,
  "completed_features": [0, 1, 2],
  "failed_features": [],
  "context_token_estimate": 145000,
  "auto_clear_count": 2,
  "auto_clear_events": [
    {"feature_index": 2, "tokens_before": 155000, "timestamp": "2025-11-16T10:30:00Z"}
  ],
  "status": "in_progress",
  "issue_numbers": null,
  "source_type": "file"
}
```

**State File Example** (GitHub Issues):
```json
{
  "batch_id": "batch-20251116-140000",
  "features_file": "",
  "features": [
    "Issue #72: Add logging feature",
    "Issue #73: Fix batch processing bug",
    "Issue #74: Update documentation"
  ],
  "total_features": 3,
  "current_index": 1,
  "completed_features": [0],
  "failed_features": [],
  "context_token_estimate": 85000,
  "auto_clear_count": 0,
  "auto_clear_events": [],
  "status": "in_progress",
  "issue_numbers": [72, 73, 74],
  "source_type": "issues"
}
```

**New Fields** (v3.2.0):
- `issue_numbers`: List of GitHub issue numbers (null for file-based batches)
- `source_type`: Either "file" or "issues" (tracks batch source)

---

## Implementation

Invoke the batch orchestration workflow to process features sequentially with automatic context management.

**You (Claude) orchestrate this workflow** - read features, loop through each one, invoke /auto-implement, next.

ARGUMENTS: {{ARGUMENTS}} (path to features.txt)

**Python Libraries** (use via Bash tool):

```python
# Failure classification
from plugins.autonomous_dev.lib.failure_classifier import (
    classify_failure,        # Classify errors as transient/permanent
    sanitize_error_message,  # Sanitize error messages for safe logging
    sanitize_feature_name,   # Sanitize feature names (CWE-117, CWE-22)
    FailureType,            # Enum: TRANSIENT, PERMANENT
)

# Retry management
from plugins.autonomous_dev.lib.batch_retry_manager import (
    BatchRetryManager,       # Orchestrate retry logic
    should_retry_feature,    # Decide if feature should be retried
    record_retry_attempt,    # Record a retry attempt
    MAX_RETRIES_PER_FEATURE, # Constant: 3
    MAX_TOTAL_RETRIES,       # Constant: 50
)

# Consent management
from plugins.autonomous_dev.lib.batch_retry_consent import (
    check_retry_consent,     # Check/prompt for user consent
    is_retry_enabled,        # Check if retry is enabled
)

# Batch state management (existing)
from plugins.autonomous_dev.lib.batch_state_manager import (
    create_batch_state, save_batch_state, load_batch_state, update_batch_progress
)
```

### STEP 1: Read and Parse Features

**Action**: Use the Read tool to read the features file

Parse the content:
- Skip lines starting with `#` (comments)
- Skip empty lines (just whitespace)
- Skip duplicate features
- Collect unique features into a list

Display to user:
```
Found N features in features.txt:
  1. Feature one
  2. Feature two
  3. Feature three
  ...

Ready to process N features. This will run unattended.
Starting batch processing...
```

---

### STEP 1.5: Analyze Dependencies and Optimize Order (NEW - Issue #157)

**Action**: Analyze feature dependencies and optimize execution order

Import the analyzer:
```python
from plugins.autonomous_dev.lib.feature_dependency_analyzer import (
    analyze_dependencies,
    topological_sort,
    visualize_graph,
    get_execution_order_stats
)
```

Analyze and optimize:
```python
try:
    # Analyze dependencies
    deps = analyze_dependencies(features)

    # Get optimized order
    feature_order = topological_sort(features, deps)

    # Get statistics
    stats = get_execution_order_stats(features, deps, feature_order)

    # Generate visualization
    graph = visualize_graph(features, deps)

    # Update batch state with dependency info
    state.feature_dependencies = deps
    state.feature_order = feature_order
    state.analysis_metadata = {
        "stats": stats,
        "analyzed_at": datetime.utcnow().isoformat(),
        "total_dependencies": sum(len(d) for d in deps.values()),
    }

    # Display dependency graph to user
    print("\nDependency Analysis Complete:")
    print(f"  Total dependencies detected: {stats['total_dependencies']}")
    print(f"  Independent features: {stats['independent_features']}")
    print(f"  Dependent features: {stats['dependent_features']}")
    print(f"\n{graph}")

except Exception as e:
    # Graceful degradation - use original order if analysis fails
    print(f"\nDependency analysis failed: {e}")
    print("Continuing with original order...")
    feature_order = list(range(len(features)))
    state.feature_order = feature_order
    state.feature_dependencies = {i: [] for i in range(len(features))}
    state.analysis_metadata = {"error": str(e), "fallback": "original_order"}
```

**Why this matters**:
- Executes features in dependency order (tests after implementation, dependent features after prerequisites)
- Reduces failures from missing dependencies
- Provides visual feedback on feature relationships
- Gracefully degrades to original order if analysis fails

---

### STEP 2: Create Todo List

**Action**: Use TodoWrite tool to create todo items for tracking

Create one todo per feature:
```
[
  {"content": "Feature 1", "status": "pending", "activeForm": "Processing Feature 1"},
  {"content": "Feature 2", "status": "pending", "activeForm": "Processing Feature 2"},
  ...
]
```

This gives visual progress tracking during batch execution.

---

### STEP 3: Process Each Feature

**Action**: Loop through features in optimized order

**For each feature index in `state.feature_order`** (uses dependency-optimized order from STEP 1.5):

Get the feature: `feature = features[feature_index]`

**For each feature**:

1. **Mark todo as in_progress** using TodoWrite

2. **Display progress**:
   ```
   ========================================
   Batch Progress: Feature M/N
   ========================================
   Feature: {feature description}
   ```

3. **Invoke /auto-implement** using SlashCommand tool:
   ```
   SlashCommand(command="/auto-implement {feature}")
   ```

   Wait for completion (this runs the full autonomous workflow):
   - Alignment check
   - Research
   - Planning
   - TDD tests
   - Implementation
   - Review + Security + Docs (parallel)
   - Git automation (if enabled)

4. **Check for failure and retry if needed** (Issue #89, v3.33.0+):

   If /auto-implement failed:

   a. **Classify failure type** using `failure_classifier.classify_failure()`:
      - Check error message against patterns
      - Return `FailureType.TRANSIENT` or `FailureType.PERMANENT`

   b. **Check retry consent** using `batch_retry_consent.is_retry_enabled()`:
      - First-run: Prompt user for consent (save to ~/.autonomous-dev/user_state.json)
      - Subsequent runs: Use saved consent state
      - Environment override: Check BATCH_RETRY_ENABLED env var

   c. **Decide whether to retry** using `batch_retry_manager.should_retry_feature()`:
      - Check user consent (highest priority)
      - Check global retry limit (max 50 total retries)
      - Check circuit breaker (5 consecutive failures → pause)
      - Check failure type (permanent → don't retry)
      - Check per-feature retry limit (max 3 retries per feature)

   d. **If should retry**:
      - Record retry attempt using `batch_retry_manager.record_retry_attempt()`
      - Display retry message: "⚠️  Transient failure detected. Retrying ({retry_count}/{MAX_RETRIES_PER_FEATURE})..."
      - Invoke `/auto-implement {feature}` again
      - Loop back to step 4 (check for failure again)

   e. **If should NOT retry**:
      - Record failure in batch state
      - Log to audit file (.claude/audit/{batch_id}_retry_audit.jsonl)
      - Display failure message with reason
      - Continue to next feature

   **Transient Failures** (automatically retried):
   - ConnectionError, TimeoutError, HTTPError
   - API rate limits (429 Too Many Requests)
   - Temporary network issues

   **Permanent Failures** (never retried):
   - SyntaxError, ImportError, AttributeError, TypeError
   - Test failures (AssertionError)
   - Validation errors

   **Safety Limits**:
   - Max 3 retries per feature
   - Max 50 total retries across batch
   - Circuit breaker after 5 consecutive failures

5. **Mark todo as completed** using TodoWrite (if feature succeeded)

6. **Continue to next feature**

---

### STEP 4: Summary Report

**Action**: After all features processed, display summary

```
========================================
BATCH COMPLETE
========================================

Total features: N
Completed successfully: M
Failed: (N - M)

Time: {estimate based on typical /auto-implement duration}

All features have been processed.
Check git commits for individual feature implementations.
========================================
```

---

## Prerequisites for Unattended Operation

**Required environment variables** (set in `.env` file):

```bash
# Auto-approve tool calls (no permission prompts)
MCP_AUTO_APPROVE=true

# Auto git operations (commit, push, PR)
AUTO_GIT_ENABLED=true
AUTO_GIT_PUSH=true
AUTO_GIT_PR=false  # Optional - set true if you want auto PRs

# Automatic retry for transient failures (NEW in v3.33.0)
# First-run: Interactive prompt (saved to ~/.autonomous-dev/user_state.json)
# Override: Set BATCH_RETRY_ENABLED=true to skip prompt
BATCH_RETRY_ENABLED=true  # Optional - enable automatic retry
```

Without these, permission prompts will interrupt the workflow.

**Automatic Retry** (v3.33.0+):
- **First Run**: You'll be prompted to enable automatic retry
- **Consent Storage**: Your choice is saved to `~/.autonomous-dev/user_state.json`
- **Environment Override**: Set `BATCH_RETRY_ENABLED=true` in `.env` to skip prompt
- **Safety**: Max 3 retries per feature, max 50 total retries, circuit breaker after 5 consecutive failures
- **Audit**: All retry attempts logged to `.claude/audit/{batch_id}_retry_audit.jsonl`

---

## Example

**features.txt**:
```text
# Bug fixes
Fix login timeout issue
Fix memory leak in background jobs

# New features
Add email notifications
Add export to CSV
Add dark mode toggle
```

**Command**:
```bash
/batch-implement features.txt
```

**Output**:
```
Found 5 features in features.txt:
  1. Fix login timeout issue
  2. Fix memory leak in background jobs
  3. Add email notifications
  4. Add export to CSV
  5. Add dark mode toggle

Starting batch processing...

========================================
Batch Progress: Feature 1/5
========================================
Feature: Fix login timeout issue

[/auto-implement runs full workflow...]
[Context cleared]

========================================
Batch Progress: Feature 2/5
========================================
Feature: Fix memory leak in background jobs

[/auto-implement runs full workflow...]
[Context cleared]

...

========================================
BATCH COMPLETE
========================================

Total features: 5
Completed successfully: 5
Failed: 0

All features have been processed.
========================================
```

---

## Timing

**Per feature**: ~20-30 minutes (same as single `/auto-implement`)

**Batch of 10 features**: ~3-5 hours
**Batch of 20 features**: ~6-10 hours (perfect for overnight)

**Recommendation**: Queue 10-20 features max per batch.

---

## Error Handling

**If a feature fails**:
- Mark todo as failed (not completed)
- Continue to next feature (don't abort entire batch)
- Report failures in summary

**Continue-on-failure is default** - one bad feature won't stop the batch.

**GitHub Issues --issues flag errors**:

1. **gh CLI not installed**:
   ```
   ERROR: gh CLI not found.
   
   Install gh CLI:
     macOS: brew install gh
     Ubuntu: apt install gh
     Windows: winget install GitHub.cli
   ```

2. **Not authenticated**:
   ```
   ERROR: gh CLI not authenticated.
   
   Run: gh auth login
   ```

3. **Issue not found**:
   ```
   WARNING: Issue #999 not found, skipping...
   Continuing with remaining issues: #72, #73, #74
   ```

4. **Invalid issue numbers**:
   ```
   ERROR: Invalid issue number: -5
   Issue numbers must be positive integers
   ```

5. **Too many issues**:
   ```
   ERROR: Too many issues (150 provided, max 100)
   Please split into multiple batches
   ```

6. **Mutually exclusive arguments**:
   ```
   ERROR: Cannot use both <file> and --issues
   Usage: /batch-implement <file> OR /batch-implement --issues <numbers>
   ```

---

## Context Management Strategy

Batch processing uses a compaction-resilient design that survives Claude Code's automatic context summarization.

### How It Works

1. **Fully unattended**: All features run without manual intervention
2. **Externalized state**: Progress tracked in `batch_state.json`, not conversation memory
3. **Auto-compaction safe**: When Claude Code summarizes context, processing continues
4. **Each feature bootstraps fresh**: Reads issue from GitHub, reads codebase, implements
5. **Git commits preserve work**: Every completed feature is committed before moving on
6. **SessionStart hook**: Re-injects workflow methodology after compaction (NEW)

### Why This Works

Each `/auto-implement` is self-contained:
- Fetches requirements from GitHub issue (not memory)
- Reads current codebase state (not memory)
- Implements based on what it reads
- Commits to git (permanent)
- Updates batch_state.json (permanent)

The conversation context is just a working buffer - all real state is externalized.

### Compaction Recovery (SessionStart Hook)

When Claude Code auto-compacts context (at 64-75% capacity), it may lose the instruction to use `/auto-implement` for each feature. The **SessionStart hook with `"compact"` matcher** automatically re-injects the workflow methodology:

```bash
# Hook file: plugins/autonomous-dev/hooks/SessionStart-batch-recovery.sh
# Fires AFTER compaction completes
# Re-injects: "Use /auto-implement for each feature"
```

**What survives compaction**:
- ✅ Completed git commits
- ✅ batch_state.json (externalized)
- ✅ File changes
- ✅ Workflow methodology (via SessionStart hook)

**What would be lost without the hook**:
- ❌ "Use /auto-implement" instruction
- ❌ Procedural context
- ❌ Pipeline requirements

The hook reads `batch_state.json` and displays:
```
**BATCH PROCESSING RESUMED AFTER COMPACTION**

Batch ID: batch-20251223-...
Progress: Feature 42 of 81

CRITICAL WORKFLOW REQUIREMENT:
- Use /auto-implement for EACH remaining feature
- NEVER implement directly
```

### Benefits

- **Truly unattended**: No manual `/clear` + resume cycles needed
- **Unlimited batch sizes**: 50+ features run continuously
- **Methodology preserved**: SessionStart hook survives compaction
- **Crash recovery**: `--resume` only needed for actual crashes, not context limits
- **Production tested**: Externalized state proven reliable

---

## Tips

1. **Start small**: Test with 2-3 features first to verify setup
2. **Check .env**: Ensure MCP_AUTO_APPROVE=true and AUTO_GIT_ENABLED=true
3. **Feature order**: Put critical features first (in case batch interrupted)
4. **Feature size**: Keep features small and focused (easier to debug failures)
5. **Large batches**: 50+ features run fully unattended (compaction-resilient design)
6. **Crash recovery**: Use `--resume <batch-id>` only if Claude Code crashes/exits

---

**Version**: 3.0.0 (Simple orchestration - no Python libraries)
**Issue**: #75 (Batch implementation)
**Changed**: Removed complex Python libraries, pure Claude orchestration
