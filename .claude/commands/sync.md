---
name: sync
description: "Sync plugin files (--github default, --env, --marketplace, --plugin-dev, --all, --uninstall)"
argument_hint: "Optional flags: --github (default), --env, --marketplace, --plugin-dev, --all, --uninstall [--force] [--local-only]"
allowed-tools: [Task, Read, Write, Bash, Grep, Glob]
---

## Implementation

```bash
python3 ~/.claude/lib/sync_dispatcher.py "$@"
```

---

# Sync - Unified Synchronization Command

**Smart context-aware sync with automatic mode detection**

The unified `/sync` command replaces `/sync-dev` and `/update-plugin` with intelligent context detection. It automatically detects whether you're syncing your development environment, updating from the marketplace, or working on plugin development.

---

## Quick Start

```bash
# Auto-detect and sync (recommended)
/sync                    # Fetches latest from GitHub (default)

# Force specific mode
/sync --github           # Fetch latest from GitHub (explicit)
/sync --env              # Environment sync only
/sync --marketplace      # Marketplace update only
/sync --plugin-dev       # Plugin dev sync only
/sync --all              # Execute all modes
/sync --uninstall        # Preview uninstallation (safe)
/sync --uninstall --force # Execute uninstallation
```

**Time**: 10-90 seconds (depends on mode)
**Interactive**: Shows detected mode, asks for confirmation
**Smart Detection**: Auto-detects context - developers get plugin-dev, users get GitHub sync
**Post-Sync Validation**: Automatic 4-phase validation with auto-fix

---

## Post-Sync Validation (NEW)

After every successful sync, automatic validation runs to ensure everything is working:

### 4 Validation Phases

1. **Settings Validation**
   - Checks `settings.local.json` exists and is valid JSON
   - Validates hook paths point to existing files
   - Auto-fixes: Removes invalid hook entries

2. **Hook Integrity**
   - Verifies all hooks have valid Python syntax
   - Checks hooks are executable (file permissions)
   - Auto-fixes: `chmod +x` for non-executable hooks

3. **Semantic Scan**
   - Checks agent prompts reference valid skills
   - Detects deprecated patterns
   - Validates version consistency across config files
   - Auto-fixes: Updates deprecated references

4. **Health Check**
   - Verifies expected component counts (agents, hooks, commands)
   - Reports any missing components

### Output Example

```
Post-Sync Validation
========================================

Settings Validation
  ✅ All checks passed

Hooks Validation
  ⚠️  Hook not executable: my_hook.py
      -> Auto-fixed: chmod +x my_hook.py

Semantic Validation
  ✅ No deprecated patterns detected

Health Validation
  ✅ All checks passed

========================================
Summary
========================================
✅ Sync validation PASSED
   Auto-fixed: 1 issue
```

### When Issues Require Manual Fixes

If validation finds issues that can't be auto-fixed, it provides step-by-step guidance:

```
❌ Sync validation FAILED (1 error)

HOW TO FIX
==========

1. Fix hooks/broken_hook.py syntax error:
   Location: .claude/hooks/broken_hook.py:45
   Error: Missing closing parenthesis
   Action: Add ')' at end of line 45
```

---

## Auto-Detection Logic

The command automatically detects the appropriate sync mode:

### Detection Priority (highest to lowest):

1. **Plugin Development** → `--plugin-dev`
   - Detected when: `plugins/autonomous-dev/` directory exists
   - Action: Sync plugin files to local `.claude/` directory
   - Use case: Plugin developers testing changes in the autonomous-dev repo

2. **GitHub Sync** → `--github` (DEFAULT)
   - Detected when: Not in plugin development context
   - Action: Fetch latest files directly from GitHub
   - Use case: Users updating to latest version in any project

**Simplified Logic**: If you're in the autonomous-dev repo, you get plugin-dev mode. Otherwise, you get GitHub sync.

---

## Sync Modes

### GitHub Mode (`--github`) - DEFAULT

Fetches the latest plugin files directly from GitHub:

**What it does**:
- Downloads files directly from `raw.githubusercontent.com/akaszubski/autonomous-dev/master`
- Uses `install_manifest.json` to determine which files to fetch
- Creates/updates `.claude/` directory structure
- No git installation required - works anywhere

**When to use**:
- Updating to latest version (default behavior)
- Getting new features and bug fixes
- Running `/sync` in any project

**Example**:
```bash
/sync                    # Auto-detects and uses GitHub mode
/sync --github           # Explicitly use GitHub mode
```

**Output**:
```
Fetching latest from GitHub (akaszubski/autonomous-dev)...
Downloading install_manifest.json...
Syncing 47 files...
✓ GitHub sync completed: 47 files updated from akaszubski/autonomous-dev
```

**Requirements**:
- Internet connection
- No GitHub account needed (public repo)

---

### Environment Mode (`--env`)

Synchronizes your development environment using the sync-validator agent:

**What it does**:
- Detects dependency conflicts (package.json, requirements.txt, etc.)
- Validates environment variables (.env files)
- Checks for pending database migrations
- Removes stale build artifacts
- Ensures configuration consistency

**When to use**:
- Daily development workflow
- After pulling upstream changes
- When dependencies seem out of sync
- Before starting new feature work

**Example**:
```bash
/sync --env
```

**Output**:
```
Detecting sync mode... Environment sync detected
Invoking sync-validator agent...
✓ Environment sync complete: 3 files updated, 0 conflicts
```

---

### Marketplace Mode (`--marketplace`)

Updates plugin files from the Claude marketplace installation with intelligent version detection and orphan cleanup:

**What it does**:
- **Version Detection** (NEW in v3.7.1): Checks marketplace vs project version and informs about available updates
- **Smart Copy**: Copies latest commands from `~/.claude/plugins/marketplaces/autonomous-dev/`
- **Security Updates**: Syncs hooks with latest security fixes
- **Agent Sync**: Updates agent definitions
- **Orphan Cleanup** (NEW in v3.7.1): Detects and removes files no longer in plugin (safe dry-run by default)
- **Local Preservation**: Preserves local customizations in `.claude/local/`

**When to use**:
- After installing plugin updates via `/plugin update`
- When commands aren't showing expected behavior
- To reset to marketplace defaults
- To clean up old/deprecated plugin files

**Example**:
```bash
/sync --marketplace
```

**Output**:
```
Detecting sync mode... Marketplace update detected

Checking version...
  Project version: 3.7.0
  Marketplace version: 3.7.1
  ⬆ Update available: 3.7.0 → 3.7.1

Copying files from installed plugin...
✓ Marketplace sync complete: 47 files updated
  - Commands: 18 updated
  - Hooks: 12 updated
  - Agents: 17 updated

Checking for orphaned files...
  Found 2 orphaned files (marked for cleanup):
    - .claude/commands/deprecated-sync-dev.md (no longer in v3.7.1)
    - .claude/hooks/old-validation.py (consolidated into newer hook)

  Dry-run mode: No files deleted (use --cleanup to remove)

✓ All marketplace sync operations complete
```

**Version Detection** (NEW in v3.7.1 - GitHub #50):
- **How it works**: Parses `MAJOR.MINOR.PATCH[-PRERELEASE]` from both marketplace and project `plugin.json`
- **Comparison**: Detects upgrade available, downgrade risk, or up-to-date status
- **Shows available upgrades**: 3.7.0 → 3.7.1 (tells you what's new)
- **Warns about downgrade risk**: If project is newer than marketplace (edge case)
- **Prevents silent stale issues**: You always know if updates are available
- **Implementation**: `lib/version_detector.py` (531 lines, 20 unit tests)
  - `Version` class: Semantic version object with comparison operators
  - `VersionComparison` dataclass: Result with `is_upgrade`, `is_downgrade`, `status`, `message`
  - `detect_version_mismatch()` function: High-level API for version comparison
  - **Security**: Path validation, audit logging (CWE-22, CWE-59 protection)
  - **Error handling**: Clear messages with expected format and troubleshooting hints
  - **Pre-release handling**: Correctly handles `3.7.0`, `3.8.0-beta.1`, `3.8.0-rc.2` patterns

**Orphan Cleanup** (NEW in v3.7.1 - GitHub #50):
- **What is an orphan?**: Files in `.claude/` that aren't in the current plugin version
- **Why cleanup matters**: Old/deprecated files can cause confusion or silent behavior changes
- **Detection**: Scans `.claude/commands/`, `.claude/hooks/`, `.claude/agents/` against plugin.json manifest
- **Reports orphans in dry-run mode**: Safe default - shows what would be deleted
- **Optional cleanup with `--cleanup` flag**: Removes old files (requires confirmation unless `-y` flag)
- **Atomic cleanup with rollback**: If deletion fails, changes automatically rolled back
- **Implementation**: `lib/orphan_file_cleaner.py` (514 lines, 22 unit tests)
  - `OrphanFile` dataclass: Represents orphaned file with path and reason
  - `CleanupResult` dataclass: Result with `orphans_detected`, `orphans_deleted`, `success`, `summary`
  - `OrphanFileCleaner` class: Low-level API for fine-grained control
  - `detect_orphans()`: Detection without cleanup
  - `cleanup_orphans()`: Cleanup with mode control (dry-run, confirm, auto)
  - **Security**: Path validation, audit logging to `logs/orphan_cleanup_audit.log` (JSON format)
  - **Error handling**: Graceful per-file failures (one orphan deletion failure doesn't block others)

**Implementation Integration** (GitHub #51):
- Both version detection and orphan cleanup are integrated into `sync_dispatcher.py`
- Enhancement doesn't block core sync - non-blocking error handling
- See `lib/sync_dispatcher.py` for complete integration details

See `lib/version_detector.py` and `lib/orphan_file_cleaner.py` for implementation details.

---

### Plugin Development Mode (`--plugin-dev`)

Syncs plugin development files to local `.claude/` directory:

**What it does**:
- Copies `plugins/autonomous-dev/commands/` → `.claude/commands/`
- Copies `plugins/autonomous-dev/hooks/` → `.claude/hooks/`
- Copies `plugins/autonomous-dev/agents/` → `.claude/agents/`
- Enables testing plugin changes without reinstalling

**When to use**:
- Developing new plugin features
- Testing command modifications
- Debugging agent behavior
- Contributing to plugin development

**Example**:
```bash
/sync --plugin-dev
```

**Output**:
```
Detecting sync mode... Plugin development detected
Syncing plugin files to .claude/...
✓ Plugin dev sync complete: 52 files updated
  - Commands: 18 synced
  - Hooks: 29 synced
  - Agents: 18 synced
```

---

### All Mode (`--all`)

Executes all sync modes in sequence:

**Execution order**:
1. Environment sync (most critical)
2. Marketplace update (get latest releases)
3. Plugin dev sync (apply local changes)

**When to use**:
- Fresh project setup
- Major version updates
- Comprehensive synchronization
- Troubleshooting sync issues

**Example**:
```bash
/sync --all
```

**Output**:
```
Executing all sync modes...

[1/3] Environment sync...
✓ Environment: 3 files updated

[2/3] Marketplace sync...
✓ Marketplace: 47 files updated

[3/3] Plugin dev sync...
✓ Plugin dev: 52 files updated

✓ All sync modes complete: 102 total files updated
```

**Rollback support**: If any mode fails, changes are rolled back automatically.

---

### Uninstall Mode (`--uninstall`)

Completely removes the autonomous-dev plugin from your project:

**What it does**:
- Shows preview of files to be removed (default behavior)
- Creates timestamped backup before deletion (when using `--force`)
- Removes all plugin files from `.claude/` directory
- Preserves protected files (PROJECT.md, .env, settings.local.json)
- Supports rollback from backup if needed

**Modes**:
- **Preview** (default): Shows what will be removed without deleting
- **Execute**: Requires `--force` flag for actual deletion
- **Local-only**: Use `--local-only` to skip global `~/.claude/` files

**When to use**:
- Removing plugin from a project
- Clean uninstall before reinstalling
- Testing plugin installation/uninstallation

**Examples**:
```bash
# Preview what will be removed (safe, no deletion)
/sync --uninstall

# Execute actual uninstallation
/sync --uninstall --force

# Uninstall from project only (preserve global files)
/sync --uninstall --force --local-only
```

**Preview output**:
```
Uninstall Preview
========================================
Files to remove: 47
Total size: 1.2 MB
Backup will be created before deletion

Files:
  .claude/commands/auto-implement.md
  .claude/commands/sync.md
  .claude/agents/planner.md
  ...

Protected files (will NOT be removed):
  .claude/PROJECT.md
  .claude/config/settings.local.json
  .env

Run with --force to execute uninstallation
```

**Execute output**:
```bash
/sync --uninstall --force
```
```
Uninstalling autonomous-dev plugin...
Creating backup: .autonomous-dev/uninstall_backup_20251214_120000.tar.gz
Removing 47 files...
✓ Uninstall complete: 47 files removed (1.2 MB)
✓ Backup: .autonomous-dev/uninstall_backup_20251214_120000.tar.gz

To rollback:
  python3 ~/.claude/lib/uninstall_orchestrator.py <project_root> --rollback .autonomous-dev/uninstall_backup_20251214_120000.tar.gz
```

**Rollback**:
If you need to restore files after uninstallation:
```python
from pathlib import Path
from uninstall_orchestrator import UninstallOrchestrator

orchestrator = UninstallOrchestrator(project_root=Path.cwd())
result = orchestrator.rollback(backup_path=Path(".autonomous-dev/uninstall_backup_20251214_120000.tar.gz"))
print(f"Restored {result.files_restored} files")
```

**Security**:
- Path traversal prevention (CWE-22)
- Symlink attack prevention (CWE-59)
- TOCTOU detection (CWE-367)
- Whitelist enforcement (only operates within `.claude/` and `.autonomous-dev/`)
- Protected file preservation
- Audit logging for all operations

**Protected files** (never removed):
- `.claude/PROJECT.md` (project goals and scope)
- `.claude/config/settings.local.json` (user settings)
- `.env` (environment variables and secrets)
- Any user-modified plugin files

---

## Migration from Old Commands

### `/sync-dev` → `/sync --env`

Old command:
```bash
/sync-dev
```

New equivalent:
```bash
/sync --env
```

**Note**: `/sync-dev` still works but shows deprecation warning. Update your workflows to use `/sync --env`.

---

### `/update-plugin` → `/sync --marketplace`

Old command:
```bash
/update-plugin
```

New equivalent:
```bash
/sync --marketplace
```

**Note**: `/update-plugin` still works but shows deprecation warning. Update your workflows to use `/sync --marketplace`.

---

## Security

All sync operations include comprehensive security validation:

- **Path Validation**: CWE-22 (path traversal) protection via `security_utils`
- **Symlink Detection**: CWE-59 (symlink resolution) protection
- **Audit Logging**: All operations logged to `logs/security_audit.log`
- **Backup Support**: Automatic backup before sync (rollback on failure)
- **Whitelist Validation**: Only allow writes to approved directories

**Security requirements**:
- All paths validated through 4-layer security checks
- Symlinks resolved before validation
- Log injection prevention (CWE-117)
- User permissions only (no privilege escalation)

See `docs/SECURITY.md` for comprehensive security documentation.

---

## Troubleshooting

### "Failed to fetch manifest from GitHub"

**Cause**: Network error or GitHub unavailable
**Fix**: Check internet connection and try again

```bash
# Verify internet connection
curl -I https://raw.githubusercontent.com

# If working, try sync again
/sync --github
```

---

### "Sync failed: Project path does not exist"

**Cause**: Invalid project path
**Fix**: Ensure you're running `/sync` from a valid project directory

```bash
cd /path/to/project
/sync
```

---

### "Plugin directory not found" (plugin-dev mode)

**Cause**: Not in a plugin development environment
**Fix**: Only use `--plugin-dev` when working on the plugin itself

```bash
# Check if plugin directory exists
ls plugins/autonomous-dev/

# If not present, you probably want environment sync instead
/sync --env
```

---

### "Conflicting sync flags"

**Cause**: Multiple incompatible flags specified
**Fix**: Use only one flag (or `--all`)

```bash
# ❌ Wrong
/sync --env --marketplace

# ✓ Correct
/sync --env

# ✓ Or use --all
/sync --all
```

---

### "Cannot use --all with specific flags"

**Cause**: Mixing `--all` with specific mode flags
**Fix**: Choose either `--all` OR specific flags

```bash
# ❌ Wrong
/sync --all --env

# ✓ Correct
/sync --all

# ✓ Or specific mode
/sync --env
```

---

### "Update available" notification during marketplace sync

**What it means**: Your project plugin is older than the marketplace version
**Example**: Project v3.7.0, Marketplace v3.7.1

**What to do**:
1. Review changelog for new features/fixes
2. Run `/sync --marketplace` to apply updates
3. Full restart Claude Code (Cmd+Q or Ctrl+Q) to reload commands
4. Test updated commands to verify

**Note**: This is just informational. Your current version still works fine, but updates may include security fixes, performance improvements, or bug fixes.

---

### "Orphaned files detected" warning during marketplace sync

**What it means**: Files exist in your project that aren't in the current plugin version
**Examples**:
- Old commands from previous version (e.g., `sync-dev.md` if upgrading from v3.6 to v3.7)
- Deprecated hooks that were consolidated into newer versions
- Agent files that were renamed

**What to do**:

**Option 1: Review before cleanup** (RECOMMENDED)
```bash
/sync --marketplace     # Shows orphans in dry-run mode
# Review the list of orphaned files

/sync --marketplace --cleanup  # Prompts for each file
# Confirm deletion: y/n for each orphan
```

**Option 2: Auto-cleanup** (Non-interactive)
```bash
/sync --marketplace --cleanup -y
# Automatically deletes all orphans without prompting
```

**Option 3: Keep files** (Conservative)
```bash
# Just ignore the warning - old files won't hurt anything
# They'll still be there but won't interfere
```

**When to be cautious**:
- If you made custom modifications to plugin files
- If you have local extensions relying on old files
- If you're not sure what files do

**Safe choice**: Use `--cleanup` (with confirmation) - it's the best practice to keep your `.claude/` directory clean and in sync with the current plugin version.

---

### "Orphan cleanup failed" during marketplace sync

**Cause**: Permission denied or file locked
**Fix**: Ensure the file isn't in use

```bash
# Close Claude Code completely
# (Press Cmd+Q on Mac or Ctrl+Q on Linux/Windows)

# Wait 5 seconds for process to exit

# Restart Claude Code

# Try sync again
/sync --marketplace --cleanup -y
```

**If still fails**:
```bash
# Check file permissions
ls -la .claude/commands/problematic-file.md

# Fix permissions if needed
chmod 644 .claude/commands/problematic-file.md

# Try cleanup again
/sync --marketplace --cleanup -y
```

---

## Examples

### Daily Development Workflow

```bash
# Morning: Sync environment before starting work
/sync

# Auto-detects environment mode
# Validates dependencies, config, migrations
```

---

### Plugin Update Workflow

```bash
# Step 1: Update plugin via marketplace
/plugin update autonomous-dev

# Step 2: FULL RESTART REQUIRED
# CRITICAL: /exit is NOT enough! Claude Code caches commands in memory.
# Press Cmd+Q (Mac) or Ctrl+Q (Windows/Linux) to fully quit
# Verify: ps aux | grep claude | grep -v grep (should return nothing)
# Wait 5 seconds, then restart Claude Code

# Step 3: Sync marketplace updates to project
/sync --marketplace

# Step 4: FULL RESTART AGAIN
# Commands won't reload until you fully restart Claude Code
# Press Cmd+Q again, wait 5 seconds, restart
```

---

### Plugin Development Workflow

```bash
# Step 1: Make changes to plugin files
vim plugins/autonomous-dev/commands/new-feature.md

# Step 2: Sync to .claude/ for testing
/sync --plugin-dev

# Step 3: FULL RESTART REQUIRED
# CRITICAL: /exit is NOT enough! You must fully quit Claude Code.
# Press Cmd+Q (Mac) or Ctrl+Q (Windows/Linux)
# Verify: ps aux | grep claude | grep -v grep (should return nothing)
# Wait 5 seconds, then restart Claude Code

# Step 4: Test the command
/new-feature

# Step 5: Repeat as needed (restart required each time!)
```

---

### Fresh Project Setup

```bash
# Sync everything
/sync --all

# Ensures:
# - Environment is configured
# - Marketplace updates applied
# - Plugin dev files synced (if applicable)
```

---

## Technical Details

### Architecture

The unified `/sync` command uses two core libraries:

1. **sync_mode_detector.py**: Intelligent context detection
   - Analyzes project structure
   - Parses command-line flags
   - Validates all paths for security

2. **sync_dispatcher.py**: Mode-specific sync operations
   - Delegates to sync-validator agent (environment mode)
   - Copies files from marketplace (marketplace mode)
   - Syncs plugin dev files (plugin-dev mode)
   - Executes all modes in sequence (all mode)

---

### Performance

**Environment mode**: 30-60 seconds
- Dominated by sync-validator agent analysis
- Depends on project size and changes

**Marketplace mode**: 5-10 seconds
- Fast file copy operations
- Depends on plugin size (~50 files)

**Plugin dev mode**: 5-10 seconds
- Fast local file sync
- Depends on number of files changed

**All mode**: 40-80 seconds
- Sum of all individual modes
- Progress reported for each phase

---

### Backup and Rollback

All sync operations create automatic backups:

- **Backup location**: `$(mktemp -d)/claude_sync_backup_*/`
- **Backup contents**: Complete `.claude/` directory
- **Rollback trigger**: Any sync failure
- **Cleanup**: Automatic after successful sync

**Manual rollback** (if needed):
```bash
# Find backup
ls -la /tmp/claude_sync_backup_*

# Restore manually
cp -r /tmp/claude_sync_backup_*/`.claude/` .claude/
```

---

## See Also

- **Environment Sync**: See archived `/sync-dev` command for detailed workflow
- **Marketplace Updates**: See archived `/update-plugin` command for update process
- **Security**: See `docs/SECURITY.md` for comprehensive security documentation
- **Development**: See `docs/DEVELOPMENT.md` for plugin development guide

---

**Last Updated**: 2025-12-13
**Issue**: GitHub #44 - Unified /sync command, GitHub #124 - Default to GitHub sync
**Replaces**: `/sync-dev`, `/update-plugin`
**Default Mode**: GitHub sync (fetches latest from repository)
