# Briefs Playbook

## Writing a Brief

Every brief is a single `.md` file in `briefs/`. Use this format:

```markdown
# Epic/Brief: [Name]

**Date:** [YYYY-MM-DD]
**Epic ID:** [ID or omit for single brief]
**Status:** [Open | In Progress | Done]

---

## Task: [Task Name]

**Objective:** One sentence. No jargon.

## What

- [ ] Specific, testable requirement 1
- [ ] Specific, testable requirement 2

## How to Verify

- [ ] Run `just check`
- [ ] Manual: [exact steps to confirm it works]
- [ ] Edge case: [what breaks if X]

## Technical Notes

Any non-obvious constraints, dependencies, or decisions.

---

## Done

When all `[ ]` items are checked and verified.
```

**Rules:**
- One brief per task or epic
- Epic = multi-story, single brief = one deliverable
- File name: `brief-[topic]-[YYYY-MM-DD].md` or `epic-[name].md`
- Frontmatter (`date`, `tags`, `agent`, `environment`) is optional — use if you want MCP searchability
- Be specific in requirements — "show sparklines" is not a requirement, "sparklines from prices table spread over holding period" is

## Executing a Brief

1. **Review** the brief before starting
2. **Verify** conditions at the top (what must already exist)
3. **Check off** items as you complete them
4. **Test** manually before closing
5. **Update Status** to Done when verified

## Archiving

Completed briefs stay in `briefs/`. Keep them — they're a record of what was decided and why.

## Epic Structure

An epic groups related stories. Use this in `epic-[name].md`:

```markdown
# Epic: [Name]

**Date:** [YYYY-MM-DD]
**Epic ID:** [PREFIX-NNN]
**Status:** [Open | In Progress | Done]
**Stories:** [PREFIX-NNN-S01 through S0N]

---

## Vision

One paragraph. Why does this matter?

---

## Stories

### PREFIX-NNN-S01 — [Story name]

**What:** [Description]

**Acceptance:**
- [ ] [Specific acceptance criterion]

**Estimate:** [0.25d | 0.5d | 1d]

---

## Done

| Story | Status |
|---|---|
| ... | 🔲 |

## Exit Criteria

What must be true for the epic to be considered complete?
```

## Review Checklist

Before committing a brief:
- [ ] Requirements are specific and testable
- [ ] Verification steps are executable (not "test it works")
- [ ] No ambiguous language ("should", "maybe", "consider")
- [ ] Dependencies are listed
- [ ] Technical notes explain non-obvious decisions