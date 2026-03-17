# Architecture Reading Checklist

Quick-reference checklist for the mandatory reading sequence.
Execute before every technical task.

## Pre-Flight Checklist

```
[ ] 1. Read docs/agent/CURRENT_STATE.md
      → Note active milestone
      → Note blockers
      → Note recent context changes

[ ] 2. List docs/agent/decisions/*.md
      → Identify ADRs relevant to current task
      → For each relevant ADR:
        [ ] Read Consequences & Constraints
        [ ] Read Actionable Rules
        [ ] Verify status is accepted/active
        [ ] Note any hard prohibitions (MUST NOT)

[ ] 3. List docs/agent/plans/*.md
      → Find active plan for current task
      → Identify current step in plan
      → Do not skip steps without user approval

[ ] 4. Acknowledge in response
      → List reviewed files
      → Summarize relevant constraints
      → State intended approach
```

## Quick Relevance Matching

To find relevant ADRs efficiently:

1. **Extract keywords** from the task description
2. **Match against filenames** in `docs/agent/decisions/`
3. **Check YAML tags** in ADR frontmatter
4. **When in doubt, read it** — a false positive is cheaper than a missed constraint

### Common Keyword → ADR Mapping Examples

| Task Keywords | Likely ADR Topics |
|---|---|
| auth, login, token, session | Authentication, authorization |
| database, schema, migration | Data layer, ORM, storage |
| API, endpoint, route | API design, versioning |
| deploy, CI/CD, pipeline | Infrastructure, deployment |
| LLM, model, provider | LLM configuration, vendor routing |
| agent, graph, workflow | Agent architecture, LangGraph |
| config, env, settings | Configuration management |
| test, coverage, fixture | Testing strategy |

## Conflict Response Template

When a conflict is detected, use this template:

```
⚠️ Conflict detected with `docs/agent/decisions/XXXX-name.md`:

Rule: "[exact quoted rule from Consequences & Constraints or Actionable Rules]"

Your request to [brief description of the conflicting action] would violate this constraint.

Options:
  A) Modify the approach to comply with the ADR
  B) Update the ADR to allow this exception (I can draft the amendment)
  C) Proceed with an explicit architectural exception (will be logged)

Which option do you prefer?
```

## Graceful Degradation Quick Reference

| Missing Resource | Action |
|---|---|
| Entire `docs/agent/` | Proceed; suggest scaffolding the directory structure |
| `CURRENT_STATE.md` only | Warn, continue to decisions |
| `decisions/` empty | Note absence, proceed freely |
| `plans/` empty | Proceed without plan context |
| ADR missing `Status` | Default to `accepted` (binding) |
| ADR status `proposed` | Informational only, not binding |
| ADR status `deprecated` | Ignore, not binding |
