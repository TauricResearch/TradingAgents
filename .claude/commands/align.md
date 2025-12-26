---
name: align
description: "Unified alignment command (--project, --docs, --retrofit)"
argument_hint: "Mode flags: --project (PROJECT.md conflicts), --docs (doc drift), --retrofit (brownfield) [--dry-run] [--auto]"
version: 3.1.0
category: core
tools: [Bash, Read, Write, Grep, Edit, Task]
allowed-tools: [Task, Read, Write, Edit, Grep, Glob]
---

# /align - Unified Alignment Command

**Purpose**: Validate and fix alignment between PROJECT.md, documentation, and codebase.

**Default**: `/align` runs full alignment check (docs + code + hooks review)

**Modes**:
- `/align` - Full alignment (PROJECT.md + CLAUDE.md + README vs code + hooks review)
- `/align --docs` - Documentation only (ensure all docs consistent with PROJECT.md)
- `/align --retrofit` - Brownfield retrofit (5-phase project transformation)

---

## Quick Usage

```bash
# Default: Full alignment check
/align

# Documentation consistency only
/align --docs

# Brownfield project retrofit
/align --retrofit
/align --retrofit --dry-run
/align --retrofit --auto
```

---

## Mode 1: Full Alignment (Default)

**Purpose**: Comprehensive check that PROJECT.md, CLAUDE.md, README, and codebase are all aligned.

**Time**: 10-30 minutes

**What it does**:

### Phase 1: Quick Scan (GenAI or Regex)
Run manifest alignment validation:

```bash
# With OpenRouter (recommended - cheap GenAI validation)
OPENROUTER_API_KEY=sk-or-... python plugins/autonomous-dev/lib/genai_validate.py manifest-alignment

# Without API key (regex fallback)
python plugins/autonomous-dev/lib/validate_manifest_doc_alignment.py
```

**Validates**:
- Count mismatches (agents, commands, hooks, skills) vs install_manifest.json
- Version consistency (CLAUDE.md, PROJECT.md, manifest)
- Semantic alignment (GenAI mode only)

**Options**:
- **OpenRouter** (recommended): ~$0.001 per validation, uses Gemini Flash
- **Claude Code**: Semantic analysis in conversation (uses Max subscription)
- **Regex only**: Fast, free, catches count mismatches

### Phase 2: Semantic Validation (GenAI)
Run `alignment-analyzer` agent to check:

**PROJECT.md vs Code**:
- Do GOALS match what's implemented?
- Is SCOPE (in/out) respected in code?
- Are CONSTRAINTS followed?
- Does ARCHITECTURE match directory structure?

**CLAUDE.md vs Reality**:
- Do workflow descriptions match actual behavior?
- Do agent descriptions match capabilities?
- Do command descriptions match what they do?
- Are documented features actually implemented?

**README vs Reality**:
- Do feature claims match implementation?
- Are installation instructions accurate?
- Do examples actually work?

### Phase 3: Hooks/Rules Review
Check for inflation in validation hooks:
- Are hooks still necessary?
- Do hook rules match current standards?
- Any redundant or conflicting hooks?

### Phase 4: Interactive Resolution (Bidirectional)
For each conflict found, determine which source is correct:

**Documentation vs Reality conflicts:**
```
CONFLICT: CLAUDE.md says "10 active commands"
Reality: 7 commands exist (example - already fixed)

What should we do?
A) Update CLAUDE.md to say "7 commands"
B) This is correct (explain why)

Your choice [A/B]:
```

**Code vs PROJECT.md conflicts (Bidirectional):**
```
CONFLICT: /create-issue exists in code/docs but not in PROJECT.md SCOPE

Which is correct?
A) Code/docs are right → Update PROJECT.md to include /create-issue
B) PROJECT.md is right → This shouldn't have been built (flag for removal)

Your choice [A/B]:
```

If A: Propose PROJECT.md update (requires approval)
If B: Log conflict for manual resolution

### Example Output

```
/align

Phase 1: Quick Scan
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ Scanning file system for truth...
  Agents: 20, Commands: 7, Hooks: 45, Skills: 28

Found 5 count mismatches, 3 dead refs
→ Will address in Phase 4

Phase 2: Semantic Validation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Checking PROJECT.md alignment...
✓ GOALS: 4/4 implemented
✓ SCOPE: No out-of-scope code found
⚠ ARCHITECTURE: docs/ structure doesn't match documented pattern

Checking CLAUDE.md alignment...
✓ Workflow descriptions accurate
⚠ Agent count outdated (says 18, actual 20)
⚠ Command list missing /create-issue

Checking README alignment...
✓ Installation instructions work
✓ Examples are accurate

Phase 3: Hooks Review
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Reviewing 45 hooks for inflation...
⚠ validate_claude_alignment.py duplicates alignment_fixer.py logic
⚠ 3 hooks reference archived commands

Phase 4: Resolution
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Found 8 issues to resolve...
[Interactive fixing begins]
```

---

## Mode 2: Documentation Alignment (`--docs`)

**Purpose**: Ensure all documentation is internally consistent and matches PROJECT.md (source of truth).

**Time**: 5-15 minutes

**What it does**:

### Checks Performed

1. **PROJECT.md as Source of Truth**
   - All other docs reference PROJECT.md correctly
   - No contradictions between docs and PROJECT.md
   - Version/date consistency

2. **Internal Doc Consistency**
   - CLAUDE.md matches README claims
   - Agent docs match AGENTS.md
   - Command docs match COMMANDS.md
   - No orphaned documentation

3. **Architecture Documentation**
   - Documented file structure matches reality
   - API documentation matches actual endpoints
   - Database schema docs match migrations

4. **Count/Reference Accuracy**
   - All counts (agents, commands, hooks) correct
   - No dead links or references
   - Examples use correct syntax

### What It Doesn't Do
- Doesn't check if code implements what docs say (use default `/align` for that)
- Doesn't modify code, only documentation
- Doesn't retrofit project structure

### Example Output

```
/align --docs

Validating documentation consistency...

Source of Truth: PROJECT.md
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ Last updated: 2025-12-13
✓ Version: v3.40.0

Cross-Reference Check
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ CLAUDE.md references PROJECT.md correctly
✓ README.md and PROJECT.md both say 7 commands
✓ docs/AGENTS.md matches agents/ directory

Architecture Docs
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ File structure documented correctly
⚠ docs/LIBRARIES.md missing 5 new libraries

Count Validation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Running alignment_fixer.py...
Found 3 count mismatches in documentation

Summary: 3 issues found
Fix with: /align --docs --fix
```

---

## Mode 3: Brownfield Retrofit (`--retrofit`)

**Purpose**: Transform existing projects to autonomous-dev standards for `/auto-implement` compatibility.

**Time**: 30-90 minutes

**Workflow**: 5-phase process with backup/rollback safety

### Phases

#### Phase 1: Analyze Codebase
- **Tool**: `codebase_analyzer.py`
- **Detects**: Language, framework, package manager, test framework, file organization
- **Output**: Comprehensive codebase analysis report

#### Phase 2: Assess Alignment
- **Tool**: `alignment_assessor.py`
- **Calculates**: Alignment score, gaps, PROJECT.md draft
- **Output**: Assessment with prioritized remediation steps

#### Phase 3: Generate Migration Plan
- **Tool**: `migration_planner.py`
- **Creates**: Step-by-step plan with effort/impact estimates
- **Output**: Optimized migration plan with dependencies

#### Phase 4: Execute Migration
- **Tool**: `retrofit_executor.py`
- **Modes**: `--dry-run` (preview), default (step-by-step), `--auto` (all at once)
- **Safety**: Automatic backup, rollback on failure

#### Phase 5: Verify Results
- **Tool**: `retrofit_verifier.py`
- **Checks**: PROJECT.md, file organization, tests, docs, git config
- **Output**: Readiness score (0-100) and blocker list

### Usage

```bash
# Preview what would change
/align --retrofit --dry-run

# Step-by-step with confirmations (safest)
/align --retrofit

# Automatic execution (fastest)
/align --retrofit --auto
```

### What Gets Retrofitted

1. **PROJECT.md Creation** - GOALS, SCOPE, CONSTRAINTS, ARCHITECTURE
2. **File Organization** - Move to `.claude/` structure
3. **Test Infrastructure** - Configure test framework and coverage
4. **CI/CD Integration** - Pre-commit hooks, GitHub Actions
5. **Documentation** - CLAUDE.md, CONTRIBUTING.md, README sections
6. **Git Configuration** - .gitignore, commit conventions

### Rollback

```bash
# Automatic on failure
# Manual rollback:
python plugins/autonomous-dev/lib/retrofit_executor.py --rollback <timestamp>
```

---

## When to Use Each Mode

| Scenario | Mode |
|----------|------|
| Regular development check | `/align` |
| After adding/removing components | `/align` |
| Before major release | `/align` |
| Updating documentation only | `/align --docs` |
| Onboarding new developers | `/align --docs` |
| Adopting autonomous-dev | `/align --retrofit` |
| Legacy codebase migration | `/align --retrofit` |

---

## Implementation

Based on arguments, invoke the appropriate alignment workflow:

1. **Default mode** (`/align` or `/align --project`): Invoke the alignment-analyzer agent to validate PROJECT.md and fix conflicts
2. **Documentation mode** (`/align --docs`): Run documentation consistency validation via alignment_fixer.py
3. **Retrofit mode** (`/align --retrofit`): Execute 5-phase brownfield retrofit workflow

---

## Implementation Details

### Mode Detection

```
Parse arguments from user input:

IF --retrofit flag:
    → Run 5-phase brownfield retrofit
    → Check for --dry-run or --auto sub-flags

ELIF --docs flag:
    → Run documentation consistency check
    → alignment_fixer.py + cross-reference validation
    → No code changes, docs only

ELSE (default):
    → Phase 1: alignment_fixer.py (quick scan)
    → Phase 2: alignment-analyzer agent (semantic validation)
    → Phase 3: Hook inflation review
    → Phase 4: Interactive resolution
```

### Libraries Used

**Default mode**:
- `validate_manifest_doc_alignment.py` - Quick count/reference scan
- `alignment-analyzer` agent - Semantic validation (via Claude Code)

**--docs mode**:
- `alignment_fixer.py` - Count validation
- Cross-reference validation logic

**--retrofit mode**:
- `codebase_analyzer.py` - Phase 1
- `alignment_assessor.py` - Phase 2
- `migration_planner.py` - Phase 3
- `retrofit_executor.py` - Phase 4
- `retrofit_verifier.py` - Phase 5

---

## Troubleshooting

### "Alignment check takes too long"

Use `--docs` for faster documentation-only check:
```bash
/align --docs  # 5-15 min vs 10-30 min
```

### "Too many conflicts to review"

Run in batches:
```bash
/align --docs           # Fix docs first
/align                  # Then full check (fewer issues)
```

### "Retrofit fails at Phase 4"

Automatic rollback should restore backup. Manual rollback:
```bash
ls ~/.autonomous-dev/backups/
python plugins/autonomous-dev/lib/retrofit_executor.py --rollback <timestamp>
```

---

## Related Commands

- `/auto-implement` - Uses PROJECT.md for feature alignment
- `/setup` - Initial project setup (calls `/align --retrofit` internally)
- `/health-check` - Plugin integrity validation

---

## Migration from Old Commands

| Old Command | New Command |
|-------------|-------------|
| `/align-project` | `/align` (default) |
| `/align-claude` | `/align --docs` |
| `/align-project-retrofit` | `/align --retrofit` |

**Note**: Old commands archived to `commands/archive/` (Issue #121).
