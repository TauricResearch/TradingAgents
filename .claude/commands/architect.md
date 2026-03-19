---
description: "Spawn the Architect agent to coordinate a full development task"
arguments:
  - name: request
    description: "Description of the feature, bug fix, or task to implement"
    required: true
---

Spawn the Architect agent (`.claude/agents/architect.md`) to handle this request.
Pass the user's full request as the task. The Architect will:

1. Clarify any gaps in the request
2. Read project claude.md for general conventions and read memeory docs/agent if request needs more information
3. Create an implementation plan
4. Set up a branch
5. Spawn implementation agents with full context
6. Validate changes
7. Commit and create a PR
8. Clean up worktrees
9. Update project memory

User request: $ARGUMENTS
