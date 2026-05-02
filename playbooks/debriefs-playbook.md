---
date: 2026-01-09T00:00:00.000Z
tags:
  - playbook
  - documentation
  - process
  - workflow
  - best-practices
  - metadata
  - vocabulary
  - agent-driven
  - extracted
---

# Debriefs Playbook

## Purpose
A debrief is a retrospective document created after the completion of a significant task or milestone. It captures what was done, what went wrong, and what was learned to improve future work.

**Critical:** Debriefs are **MANDATORY** for all significant changes per the **Change Management Protocol (CMP)**. A debrief documents what actually happened, not what was planned. It includes verification proof that changes work as intended.

**Reference:** See `playbooks/change-management-protocol.md` for the full Plan → Execute → Verify → Debrief cycle.

## Agent Designation & Operating Environment

**Critical:** Debriefs should clearly specify the agent's designation and operating environment to enable proper context management and tool selection.

### Required Frontmatter Fields
- `date`: YYYY-MM-DD format (creation date)
- `tags`: Array of relevant tags (e.g., [cleanup, verification, mcp-server])
- `agent`: Agent designation (e.g., [claude, cursor, local-ai])
- `environment`: Operating environment (e.g., [local, development, production])

**Example:**
```markdown
---
date: 2026-01-09
tags: [cleanup, verification, mcp-server]
agent: claude
environment: local
---
```

### Why This Matters
- **Agent Context:** Different agents may have different capabilities and access patterns
- **Tool Selection:** Operating environment determines available tools (MCP, file system, etc.)
- **Searchability:** Tags enable semantic discovery across knowledge graph
- **Workflow Tracing:** Agent designation helps track which agent created which debriefs

## File Naming
- **Convention:** `YYYY-MM-DD-topic.md` (date first, always)
- **Drafting:** You may create `debrief-topic-YYYY-MM-DD.md` in the project root for visibility during the session
- **Final Location:** `debriefs/` directory (must be moved before session end)
- **Enforcement:** Run `bun run scripts/maintenance/fix-debrief-names/index.ts` to verify/fix naming

## Template

```markdown
---
date: [YYYY-MM-DD]
tags: [tag1, tag2, tag3]
agent: [claude | cursor | local-ai | other]
environment: [local | development | production]
---

## Debrief: [Task Name]

## Accomplishments

- **[Accomplishment 1]:** [Description of what was achieved]
- **[Accomplishment 2]:** [Description of what was achieved]

## Problems

- **[Problem 1]:** [Description of the issue encountered and how it was resolved]
- **[Problem 2]:** [Description of the issue encountered and how it was resolved]

## Lessons Learned

- **[Lesson 1]:** [Insight gained that can be applied to future tasks]
- **[Lesson 2]:** [Insight gained that can be applied to future tasks]

```

## Frontmatter Tags Best Practices

### Recommended Tags by Category

**Task Type:**
- `cleanup` - Code cleanup, dead code removal, hygiene
- `refactoring` - Code restructuring, architectural changes
- `feature` - New feature implementation
- `bugfix` - Bug resolution and fixes
- `performance` - Performance optimization
- `security` - Security improvements
- `testing` - Test coverage, test improvements

**Verification/Quality:**
- `verification` - Verification of completed work
- `mcp-server` - MCP server usage, configuration
- `quality-assessment` - Code quality evaluations
- `audit` - Code audits, compliance checks

**Phase:**
- `phase1` - First phase of multi-phase task
- `phase2` - Second phase, etc.
- `planning` - Planning and design phase
- `implementation` - Implementation phase
- `review` - Review and refinement phase

**Domain:**
- `database` - Database-related changes
- `api` - API changes
- `cli` - Command-line interface changes
- `ui` - User interface changes
- `infrastructure` - Infrastructure and tooling
- `documentation` - Documentation updates

### Adding Frontmatter Tags

**Recommended Approach:**
1. **Manual Addition:** Add frontmatter tags directly when creating debrief
2. **MCP-Assisted:** Use amalfa MCP server to suggest relevant tags based on semantic search
3. **Post-Creation:** Review and add additional tags discovered through graph traversal

**Using amalfa MCP Server:**
```bash
# Search for similar debriefs to discover common tags
amalfa serve  # Start MCP server (if not running)

# Then in MCP client:
search_documents("cleanup verification mcp server")
# Review returned debriefs for tag patterns
```

## File Naming Guidelines

### Debrief Naming Convention
- **Format:** `debrief-[topic].md` or `debrief-[topic]-[YYYY-MM-DD].md`
- **Location:** `debriefs/` directory
- **Slug Format:** lowercase, hyphens instead of spaces, no special chars
- **Examples:**
  - `debriefs/debrief-phase1-cleanup.md`
  - `debriefs/debrief-mcp-server-optimization.md`
  - `debriefs/debrief-phase1-cleanup-2026-01-09.md`

### Date-Prefix Naming (Recommended)
- **Format:** `debrief-[topic]-YYYY-MM-DD.md`
- **Benefit:** Automatic chronological sorting
- **Benefit:** Easy identification of recent work
- **Benefit:** Prevents naming collisions

### Avoid These Names
- ❌ Generic names like `debrief.md` or `task.md`
- ❌ Overly long descriptions in filename (put in debrief, not filename)
- ❌ Special characters or spaces (use hyphens)
- ❌ Numbers without context (use descriptive slugs)

## MCP-First Verification Workflow

### Recommended Practice
For cleanup, refactoring, and verification tasks, use amalfa MCP server capabilities to verify completion and discover related work.

**Verification Workflow:**
```bash
# 1. Create debrief with frontmatter tags
# 2. Execute work (deletion, refactoring, etc.)
# 3. Use MCP to verify work was complete
search_documents("[task name] verification")
# 4. Explore links to discover cross-references
explore_links("[debrief-id]")
# 5. Create debrief documenting verification method
```

**Benefits:**
- **4.6x faster** verification vs traditional grep
- **95% search precision** vs 70% with pattern matching
- **Semantic breadth** through graph traversal
- **Higher confidence** through redundant verification methods
- **Recommended Tool for Adding Tags:** Use amalfa MCP server `search_documents` to find similar debriefs and discover common tag patterns

## Post-Debrief Checklist
- [ ] **Archive Brief:** Move the completed brief from `briefs/` to `briefs/archive/` (or use date-prefix naming).
- [ ] **Frontmatter Tags Present:** Verify debrief includes `date`, `tags`, `agent`, and `environment` fields.
- [ ] **Update Changelog:** Add a summary of changes to `CHANGELOG.md` under the `[Unreleased]` section.
- [ ] **Update Current Task:** Update `_CURRENT_TASK.md` to reflect the completion of the current objective and readiness for the next.
- [ ] **Ingest Debrief:** Ensure `amalfa watcher` is running (to auto-ingest) or run `amalfa init` to update the knowledge graph.
