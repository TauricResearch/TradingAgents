---
name: setup
description: Interactive setup wizard - analyzes tech stack, generates PROJECT.md, configures hooks
argument_hint: "[--project-dir <path>]"
allowed-tools: [Task, Read, Write, Bash, Grep, Glob]
---

# /setup - Project Initialization Wizard

**Purpose**: Initialize autonomous-dev in a project with intelligent PROJECT.md generation.

**Core Value**: Analyzes your codebase and generates comprehensive PROJECT.md (brownfield) or guides you through creation (greenfield).

---

## Quick Start

```bash
/setup
```

**Time**: 2-5 minutes
**Interactive**: Yes (guides you through choices)

---

## Implementation

### Step 1: Install Plugin Files

```bash
# Delegate to sync_dispatcher for reliable file installation
echo "Installing plugin files..."
python3 .claude/lib/sync_dispatcher.py --github

# Fallback if .claude/lib doesn't exist yet (fresh install)
if [ $? -ne 0 ]; then
  # Try from plugins/ directory (dev environment)
  python3 plugins/autonomous-dev/lib/sync_dispatcher.py --github
fi
```

**What this does**:
- Downloads latest files from GitHub
- Copies to `.claude/` directory
- Validates all paths for security
- Non-destructive (preserves existing PROJECT.md, .env)

**If sync fails**: Show error and suggest manual sync with `/sync --github`

---

### Step 1.5: Create .env Configuration

After plugin files are installed, create `.env` from template:

```bash
# Check if .env already exists
if [ ! -f ".env" ]; then
  # Copy from .env.example if it exists (standard convention)
  if [ -f ".env.example" ]; then
    cp .env.example .env
    echo "Created .env from .env.example"
  else
    # Create minimal .env with essential settings
    cat > .env << 'ENVEOF'
# autonomous-dev Environment Configuration
# See: https://github.com/akaszubski/autonomous-dev#environment-setup

# =============================================================================
# API KEYS (REQUIRED - fill these in!)
# =============================================================================
GITHUB_TOKEN=ghp_your_token_here
# ANTHROPIC_API_KEY=sk-ant-your_key_here

# =============================================================================
# GIT AUTOMATION (enabled by default)
# =============================================================================
AUTO_GIT_ENABLED=true
AUTO_GIT_PUSH=true
AUTO_GIT_PR=false

# =============================================================================
# TOOL AUTO-APPROVAL (reduces permission prompts)
# =============================================================================
MCP_AUTO_APPROVE=true

# =============================================================================
# BATCH PROCESSING
# =============================================================================
BATCH_RETRY_ENABLED=true
ENVEOF
    echo "Created .env with default settings"
  fi
fi

# Ensure .env is in .gitignore
if [ -f ".gitignore" ]; then
  if ! grep -q "^\.env$" .gitignore; then
    echo ".env" >> .gitignore
    echo "Added .env to .gitignore"
  fi
else
  echo ".env" > .gitignore
  echo "Created .gitignore with .env"
fi
```

**After creating .env, ALWAYS prompt the user:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  ACTION REQUIRED: Configure your .env file
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

A .env file has been created with default settings. You MUST update the
API keys and tokens for full functionality.

Required (at minimum):
  GITHUB_TOKEN=ghp_your_token_here
    → Create at: https://github.com/settings/tokens
    → Scopes needed: repo, read:org

Optional but recommended:
  ANTHROPIC_API_KEY=sk-ant-your_key_here
    → Get from: https://console.anthropic.com/
    → Enables: GenAI security scanning, test generation, doc fixes

Key settings already enabled:
  AUTO_GIT_ENABLED=true     (auto-commit after /auto-implement)
  AUTO_GIT_PUSH=true        (auto-push commits)
  MCP_AUTO_APPROVE=true     (reduce permission prompts)
  BATCH_RETRY_ENABLED=true  (retry transient failures)

Edit .env now:
  vim .env
  # or
  code .env

See all options: cat .env  (file is fully documented)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Wait for user confirmation before continuing to Step 2.**

---

### Step 2: Detect Project Type

After files installed, invoke the **setup-wizard** agent with this context:

```
CONTEXT FOR SETUP-WIZARD:

Step 1 (file installation) is COMPLETE. Files are in .claude/

Your job now is:
1. Detect if this is a BROWNFIELD (existing code) or GREENFIELD (new project)
2. Generate or help create PROJECT.md
3. Optionally configure hooks
4. Validate the setup

DETECTION RULES:
- BROWNFIELD: Has README.md, src/, package.json, pyproject.toml, or >10 source files
- GREENFIELD: Empty or near-empty project

For BROWNFIELD:
- Analyze: README.md, package.json/pyproject.toml, directory structure, git history
- Generate: Comprehensive PROJECT.md (80-90% complete)
- Mark TODOs: Only for CONSTRAINTS and CURRENT SPRINT (user must define)

For GREENFIELD:
- Ask: Primary goal, architecture type, tech stack
- Generate: PROJECT.md template with user inputs filled in
- Mark TODOs: More sections need user input

Then:
- Offer hook configuration (automatic vs manual workflow)
- Run health check to validate
- Show next steps
```

---

## What Gets Created

### Always Created

**Directory**: `.claude/`
- `agents/` - 20 AI agents
- `commands/` - 7 slash commands
- `hooks/` - 13 core automation hooks
- `lib/` - 35 Python libraries
- `skills/` - 28 skill packages

### PROJECT.md Generation

**Brownfield** (existing project):
```markdown
# Auto-generated sections (from codebase analysis):
- Project Vision (from README.md)
- Goals (from README roadmap/features)
- Architecture (detected from structure)
- Tech Stack (detected from package files)
- File Organization (detected patterns)
- Testing Strategy (detected from tests/)
- Documentation Map (detected from docs/)

# TODO sections (user must fill):
- CONSTRAINTS (performance, scale limits)
- CURRENT SPRINT (active work)
```

**Greenfield** (new project):
```markdown
# Generated from user responses:
- Project Vision
- Goals (based on primary goal selection)
- Architecture (based on architecture choice)

# TODO sections (more user input needed):
- SCOPE (in/out of scope)
- CONSTRAINTS
- CURRENT SPRINT
- File Organization
```

### Optional: Hook Configuration

**Manual Mode** (default):
- No additional config needed
- User runs formatting and testing tools manually

**Automatic Hooks Mode**:
- Hooks are configured automatically in settings.local.json
- Post-edit formatting via unified_post_tool.py
- Pre-tool-use validation via unified_pre_tool.py
- See `.claude/settings.local.json` for full hook configuration

---

## Example Flow

### Brownfield Project (existing code)

```
/setup

Step 1: Installing plugin files...
✓ Synced 47 files from GitHub

Step 2: Detecting project type...
✓ BROWNFIELD detected (Python project with 213 commits)

Analyzing codebase...
✓ Found README.md (extracting vision)
✓ Found pyproject.toml (Python 3.11, FastAPI)
✓ Analyzing src/ (47 files, layered architecture)
✓ Analyzing tests/ (unit + integration)
✓ Analyzing git history (TDD workflow detected)

Generating PROJECT.md...
✓ Created PROJECT.md at root (412 lines, 95% complete)

Sections auto-generated:
  ✓ Project Vision
  ✓ Goals (from README)
  ✓ Architecture (Layered API pattern)
  ✓ Tech Stack (Python, FastAPI, PostgreSQL)
  ✓ File Organization
  ✓ Testing Strategy

Sections needing your input:
  📝 CONSTRAINTS - Define performance/scale limits
  📝 CURRENT SPRINT - Define active work

Step 3: Hook configuration
How would you like to run quality checks?
[1] Slash Commands (manual control - recommended for beginners)
[2] Automatic Hooks (auto-format, auto-test)
> 1

✓ Slash commands mode selected (no additional config)

Step 4: Validation
Running health check...
✓ 20/20 agents loaded
✓ 13/13 hooks executable
✓ 7/7 commands present
✓ PROJECT.md exists

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ Setup Complete!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Next steps:
1. Review PROJECT.md and fill in TODO sections
2. Try: /auto-implement "add a simple feature"
3. When done: /clear (reset context for next feature)
```

### Greenfield Project (new/empty)

```
/setup

Step 1: Installing plugin files...
✓ Synced 47 files from GitHub

Step 2: Detecting project type...
✓ GREENFIELD detected (minimal/empty project)

Let's create your PROJECT.md:

What is your project's primary goal?
[1] Production application (full-featured app)
[2] Library/SDK (reusable code for developers)
[3] Internal tool (company/team utility)
[4] Learning project (experimental)
> 1

What architecture pattern?
[1] Monolith (single codebase)
[2] Microservices (distributed)
[3] API + Frontend (layered)
[4] CLI tool
> 3

Primary language?
[1] Python
[2] TypeScript/JavaScript
[3] Go
[4] Other
> 1

Generating PROJECT.md...
✓ Created PROJECT.md at root (287 lines)

Fill in these sections:
  📝 GOALS - What success looks like
  📝 SCOPE - What's in/out of scope
  📝 CONSTRAINTS - Technical limits
  📝 CURRENT SPRINT - First sprint goals

Step 3: Hook configuration...
[Same as brownfield]

Step 4: Validation...
[Same as brownfield]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ Setup Complete!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Troubleshooting

### "Sync failed: Network error"

```bash
# Check internet connection
curl -I https://raw.githubusercontent.com

# Manual sync
/sync --github
```

### "PROJECT.md generation incomplete"

This is expected for greenfield projects. Fill in TODO sections manually:

```bash
# Open and edit
vim PROJECT.md

# Then validate
/align --project
```

### "Hooks not running"

Full restart required after setup:
```bash
# Quit Claude Code completely (Cmd+Q / Ctrl+Q)
# Wait 5 seconds
# Restart Claude Code
```

---

## Related Commands

- `/sync` - Sync/update plugin files
- `/align --project` - Validate PROJECT.md alignment
- `/health-check` - Validate plugin integrity

---

## Architecture

```
/setup
   │
   ├── Step 1: sync_dispatcher.py --github
   │   └── Reliable file installation (Python library)
   │
   ├── Step 2: setup-wizard agent (GenAI)
   │   ├── Detect brownfield/greenfield
   │   ├── Analyze codebase (if brownfield)
   │   └── Generate PROJECT.md
   │
   ├── Step 3: Hook configuration
   │   └── Optional settings.local.json creation
   │
   └── Step 4: health_check.py
       └── Validate installation
```

**Key Design**: Delegates file installation to `sync_dispatcher.py` (reliable), focuses GenAI on PROJECT.md generation (what it's good at).

---

**Last Updated**: 2025-12-13
