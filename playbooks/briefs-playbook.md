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
- **Workflow Tracing:** Agent designation helps track which agent created which briefs

## File Naming
- **Format:** `brief-[slug].md`
- **Location:** `briefs/` directory
- **Example:** `briefs/brief-sidebar-refinements.md`

### Brief Naming Convention
- **Format:** `brief-[slug].md` or `brief-[topic]-[YYYY-MM-DD].md`
- **Location:** `briefs/` directory
- **Slug Format:** lowercase, hyphens instead of spaces, no special chars
- **Examples:**
  - `briefs/brief-sidebar-refinements.md`
  - `briefs/brief-phase1-cleanup.md`
  - `briefs/brief-mcp-server-optimization.md`

### Date-Prefix Naming (Recommended)
- **Format:** `brief-[topic]-[YYYY-MM-DD].md`
- **Benefits:** 
  - Automatic chronological sorting
  - Easy identification of recent work
  - Prevents naming collisions
- **Example:** `brief-phase1-cleanup-2026-01-09.md`

### Avoid These Names
- ❌ Generic names like `brief.md` or `task.md`
- ❌ Overly long descriptions in filename (put in brief, not filename)
- ❌ Special characters or spaces (use hyphens)
- ❌ Numbers without context (use descriptive slugs)

## Template

```markdown
---
date: [YYYY-MM-DD]
tags: [tag1, tag2, tag3]
agent: [claude | cursor | local-ai | other]
environment: [local | development | production]
---

## Task: [Task Name]

**Objective:** [Concise description of the main goal]

- [ ] [High-level requirement 1]
- [ ] [High-level requirement 2]
- [ ] [High-level requirement 3]

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
1. **Manual Addition:** Add frontmatter tags directly when creating brief
2. **MCP-Assisted:** Use amalfa MCP server to suggest relevant tags based on semantic search
3. **Post-Creation:** Review and add additional tags discovered through graph traversal

**Using amalfa MCP Server:**
```bash
# Search for similar briefs to discover common tags
amalfa serve  # Start MCP server (if not running)

# Then in MCP client:
search_documents("cleanup verification mcp server")
# Review returned briefs for tag patterns
```

**Recommended Tool for Adding Tags:** Use amalfa MCP server `search_documents` to find similar briefs and discover common tag patterns.

## Key Actions Checklist:

- [ ] [Actionable step 1]
- [ ] [Actionable step 2]
- [ ] [Actionable step 3]

## Detailed Requirements / Visuals

[Optional: Add detailed descriptions, ASCII art layouts, or specific constraints here]

## Best Practices
- **Keep it focused:** One brief per distinct task.
- **Use checklists:** Checklists allow for tracking progress within the brief itself.
- **Be visual:** Use ASCII art or diagrams to explain layout changes.
- **Include frontmatter:** Add `date`, `tags`, `agent`, and `environment` fields for discoverability.
- **Tag strategically:** Use descriptive tags that enable semantic discovery across knowledge graph.
- **Document verification:** Specify how work will be verified (manual testing, MCP server, automated tests).
- **Date-prefix naming:** Use `brief-[topic]-[YYYY-MM-DD].md` format for automatic chronological sorting.