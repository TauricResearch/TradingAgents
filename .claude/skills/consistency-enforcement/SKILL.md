---
name: consistency-enforcement
version: 1.0.0
type: knowledge
description: Documentation consistency enforcement - prevents drift between README.md and actual codebase state. Auto-activates when updating docs, committing changes, or working with skills/agents/commands.
keywords: readme, documentation, commit, sync, update, skill, agent, command, count, marketplace, consistency, drift
auto_activate: true
allowed-tools: [Read]
---

# Consistency Enforcement Skill

**Layer 4 Defense Against Documentation Drift**

This skill auto-activates to remind you to maintain documentation consistency when working on:
- Documentation updates (README.md, SYNC-STATUS.md, etc.)
- Adding/removing skills, agents, or commands
- Committing changes
- Updating marketplace.json

## When This Activates

Automatically activates on keywords:
- "readme", "documentation", "docs"
- "commit", "sync", "update"
- "skill", "agent", "command"
- "count", "marketplace"
- "consistency", "drift"

---

## Critical Consistency Rules

### Rule 1: README.md is the Source of Truth

**All counts in README.md must match reality:**

```bash
# Count actual skills
ls -d plugins/autonomous-dev/skills/*/ | wc -l

# Count actual agents
ls plugins/autonomous-dev/agents/*.md | wc -l

# Count actual commands
ls plugins/autonomous-dev/commands/*.md | wc -l

# ✅ Verify README.md shows these exact counts
grep -E "[0-9]+ Skills" plugins/autonomous-dev/README.md
grep -E "[0-9]+ (Specialized )?Agents" plugins/autonomous-dev/README.md
grep -E "[0-9]+ (Slash )?Commands" plugins/autonomous-dev/README.md
```

### Rule 2: All Documentation Files Must Match README.md

**These files MUST show the same counts:**

- ✅ `README.md` (primary source)
- ✅ `docs/SYNC-STATUS.md`
- ✅ `docs/UPDATES.md`
- ✅ `INSTALL_TEMPLATE.md`
- ✅ `.claude-plugin/marketplace.json` (metrics section)
- ✅ `templates/knowledge/best-practices/claude-code-2.0.md`

### Rule 3: Never Reference Non-Existent Skills

**Before mentioning a skill, verify it exists:**

```bash
# Get list of actual skills
ls -1 plugins/autonomous-dev/skills/

# ❌ NEVER reference:
# - engineering-standards (doesn't exist)
# - Any skill not in the above list
```

### Rule 4: marketplace.json Metrics Match Reality

**Update marketplace.json whenever counts change:**

```json
{
  "metrics": {
    "agents": 8,
    "skills": 12,
    "commands": 21,
    "hooks": 9
  }
}
```

---

## 4-Layer Defense System

This skill is **Layer 4** of the consistency enforcement strategy:

### Layer 1: Automated Tests (Enforced)
**Location**: `tests/test_documentation_consistency.py`

**What it does**: Automatically fails CI/CD if documentation is out of sync

**Checks**:
- ✅ README.md skill/agent/command counts match actual
- ✅ All mentioned skills actually exist
- ✅ marketplace.json metrics match reality
- ✅ Cross-document consistency verified

**Run**:
```bash
pytest tests/test_documentation_consistency.py -v
```

### Layer 2: Agent Memory (doc-master)
**Location**: `agents/doc-master.md`

**What it does**: doc-master agent has explicit checklist to verify consistency before creating docs.json artifact

**Checks**:
- ✅ 6-point consistency verification checklist
- ✅ Common drift scenarios documented
- ✅ Automated test reminder

### Layer 3: Pre-Tool-Use Hook (Optional)
**Location**: `hooks/validate_docs_consistency.py`

**What it does**: Validates documentation consistency before file modifications

**Note**: Integrated into unified_pre_tool.py hook. Can be annoying, so it's optional. Use for critical repositories.

### Layer 4: This Skill (Auto-Reminder)
**Location**: `skills/consistency-enforcement/SKILL.md`

**What it does**: Auto-activates to remind you about consistency when working on docs

**Triggers**: Keywords like "readme", "commit", "skill", "agent", "command", "update"

---

## Common Documentation Drift Scenarios

### Scenario 1: Adding New Skill

**What happens**:
```bash
# You create new skill
mkdir skills/new-skill-name
# Write skill content...

# ❌ EASY TO FORGET: Update documentation!
```

**Correct workflow**:
```bash
# 1. Create skill
mkdir skills/new-skill-name

# 2. Update README.md
# Change "X Skills" to "Y Skills" (where Y = X + 1)
# Add skill to categorized table

# 3. Update cross-references
# - docs/SYNC-STATUS.md
# - docs/UPDATES.md
# - INSTALL_TEMPLATE.md
# - .claude-plugin/marketplace.json (metrics.skills)
# - templates/knowledge/best-practices/claude-code-2.0.md

# 4. Run tests to verify
pytest tests/test_documentation_consistency.py -v

# ✅ Now all counts match!
```

### Scenario 2: Updating README.md

**What happens**:
```bash
# You update README.md skill count
# "9 Skills" → "12 Skills"

# ❌ EASY TO FORGET: Update other docs!
```

**Correct workflow**:
```bash
# 1. Update README.md
# "9 Skills" → "12 Skills (Comprehensive SDLC Coverage)"

# 2. Update ALL cross-references
grep -r "9 skills\|9 Skills" plugins/autonomous-dev/*.md plugins/autonomous-dev/docs/*.md

# 3. Update each file found
# - SYNC-STATUS.md: "9 skills" → "12 skills"
# - UPDATES.md: "All 9 skills" → "All 12 skills"
# - INSTALL_TEMPLATE.md: "9 Skills" → "12 Skills"

# 4. Update marketplace.json
# "skills": 9 → "skills": 12

# 5. Run tests to verify
pytest tests/test_documentation_consistency.py -v

# ✅ All documents now consistent!
```

### Scenario 3: Removing Skill

**What happens**:
```bash
# You remove old skill
rm -rf skills/deprecated-skill

# ❌ EASY TO FORGET: Update counts AND remove references!
```

**Correct workflow**:
```bash
# 1. Remove skill
rm -rf skills/deprecated-skill

# 2. Update README.md count
# "12 Skills" → "11 Skills"
# Remove skill from table

# 3. Update all cross-references
# (Same as Scenario 2)

# 4. Search for skill references
grep -r "deprecated-skill" plugins/autonomous-dev/

# 5. Remove all references found

# 6. Run tests to verify
pytest tests/test_documentation_consistency.py -v

# ✅ Skill removed, all docs updated!
```

### Scenario 4: Before Committing

**What happens**:
```bash
# You're about to commit documentation changes
git add README.md docs/SYNC-STATUS.md

# ❌ EASY TO FORGET: Verify consistency!
```

**Correct workflow**:
```bash
# 1. Run consistency validation
python plugins/autonomous-dev/hooks/validate_docs_consistency.py

# 2. If checks fail, fix issues

# 3. Re-run validation
python plugins/autonomous-dev/hooks/validate_docs_consistency.py

# 4. When all checks pass, commit
git commit -m "docs: update skill count to 12"

# ✅ Consistent documentation committed!
```

---

## Quick Consistency Checklist

**Before committing documentation changes, verify:**

- [ ] Counted actual skills/agents/commands in directories
- [ ] Updated README.md with correct counts
- [ ] Updated docs/SYNC-STATUS.md with same counts
- [ ] Updated docs/UPDATES.md with same counts
- [ ] Updated INSTALL_TEMPLATE.md with same counts
- [ ] Updated .claude-plugin/marketplace.json metrics
- [ ] Updated templates/knowledge/best-practices/claude-code-2.0.md
- [ ] Searched for and removed broken skill references
- [ ] Ran `pytest tests/test_documentation_consistency.py -v`
- [ ] All tests passed ✅

---

## Commands for Verification

### Count Everything
```bash
# Count skills
ls -d plugins/autonomous-dev/skills/*/ | wc -l

# Count agents
ls plugins/autonomous-dev/agents/*.md | wc -l

# Count commands
ls plugins/autonomous-dev/commands/*.md | wc -l
```

### Check README.md
```bash
# Find skill count mentions
grep -E "[0-9]+ Skills" plugins/autonomous-dev/README.md

# Find agent count mentions
grep -E "[0-9]+ (Specialized )?Agents" plugins/autonomous-dev/README.md

# Find command count mentions
grep -E "[0-9]+ (Slash )?Commands" plugins/autonomous-dev/README.md
```

### Check Cross-References
```bash
# Find all skill count mentions across docs
grep -r "skills" plugins/autonomous-dev/*.md plugins/autonomous-dev/docs/*.md | grep -E "[0-9]+"

# Check marketplace.json
cat .claude-plugin/marketplace.json | grep -A 5 '"metrics"'
```

### Run Automated Tests
```bash
# Run consistency tests
pytest tests/test_documentation_consistency.py -v

# Run only README checks
pytest tests/test_documentation_consistency.py::TestREADMEConsistency -v

# Run only cross-document checks
pytest tests/test_documentation_consistency.py::TestCrossDocumentConsistency -v

# Run only marketplace.json checks
pytest tests/test_documentation_consistency.py::TestMarketplaceConsistency -v
```

### Validate Before Commit
```bash
# Run pre-commit validation script
python plugins/autonomous-dev/hooks/validate_docs_consistency.py

# If validation passes (exit code 0), safe to commit
echo $?
```

---

## Why This Matters

**Documentation drift is insidious:**

- ❌ User reads README.md: "9 Core Skills"
- ❌ Plugin actually has: 12 skills
- ❌ User confusion: "Where are the other 3 skills?"

**Or worse:**

- ❌ README.md mentions: "engineering-standards skill"
- ❌ Skill doesn't exist (was never created)
- ❌ User tries to use it: Doesn't work!

**With 4-layer defense:**

- ✅ Layer 1: Tests fail in CI/CD → Can't merge inconsistent docs
- ✅ Layer 2: doc-master agent checks → Catches before creating docs.json
- ✅ Layer 3: Pre-commit hook → Blocks commit (if enabled)
- ✅ Layer 4: This skill → Reminds you during work

**Result**: Documentation always matches reality 🎯

---

## Integration with Other Skills

This skill works with:

- **documentation-guide**: Documentation standards and format
- **git-workflow**: Commit conventions and PR workflows
- **project-management**: PROJECT.md structure and consistency

**Cross-reference pattern**:
- Use `documentation-guide` for HOW to write docs
- Use `consistency-enforcement` for WHEN to update docs
- Use `git-workflow` for HOW to commit doc changes

---

## Troubleshooting

### "Tests are failing but I don't know why"

```bash
# Run tests with verbose output
pytest tests/test_documentation_consistency.py -v

# Read the assertion error - it tells you exactly what's wrong
# Example: "README.md shows 9 skills but actual is 12"
```

### "I updated README.md but tests still fail"

**Check**: Did you update ALL cross-references?

```bash
# Find all skill count mentions
grep -r "[0-9]+ skills" plugins/autonomous-dev/*.md plugins/autonomous-dev/docs/*.md

# Each file should show the SAME count
```

### "marketplace.json metrics don't match"

```bash
# Check current metrics
cat .claude-plugin/marketplace.json | grep -A 5 '"metrics"'

# Count actual resources
ls -d plugins/autonomous-dev/skills/*/ | wc -l
ls plugins/autonomous-dev/agents/*.md | wc -l
ls plugins/autonomous-dev/commands/*.md | wc -l

# Update marketplace.json to match
vim .claude-plugin/marketplace.json
```

### "Pre-commit hook is blocking my commit"

**Option 1**: Fix the inconsistency (recommended)
```bash
python plugins/autonomous-dev/hooks/validate_docs_consistency.py
# Read output, fix issues
```

**Option 2**: Skip hook (NOT RECOMMENDED)
```bash
git commit --no-verify
# Only use in emergency!
```

---

**Version**: 1.0.0
**Type**: Knowledge skill (auto-activates)
**Priority**: Critical (prevents documentation drift)
**See Also**: documentation-guide, git-workflow, project-management
