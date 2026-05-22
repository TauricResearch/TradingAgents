# Epic/Brief: Align Orientation Procedures with Remote PR Gates

**Date:** 2026-05-22
**Epic ID:** td-6731ce
**Status:** In Progress
**Stories:** td-7bbe3f, td-ca5250, td-b6d5a3, td-852077

---

## Vision
Align onboarding, orientation, and development procedures with remote Pull Request gates and repository protection rules. Tailor the visitor guide to audit and review agents, integrate upstream PR/Action visibility into developer startup tools, and implement a git pre-push hook for absolute main-branch safety.

---

## Stories

### td-7bbe3f — Chore: Refactor VISITOR.md for self-directed review/audit agent
**What:** Rewrite [VISITOR.md](file:///Users/petersmith/dev/github/tradingagents/VISITOR.md) to serve as a fast-onboarding orientation file for an AI agent or auditor whose sole purpose is to perform a self-directed review, audit, or exploration of the workspace. Delete duplicate "Critical Files" and "Language Boundary" tables and point directly to `AGENTS.md` to prevent maintenance drift.

**Acceptance:**
- [ ] `VISITOR.md` is refactored to focus on self-directed review/audit agent capabilities.
- [ ] No duplicate tables (Critical Files, Language Boundaries) exist in `VISITOR.md` (all point to `AGENTS.md`).
- [ ] Onboarding instructions explain how to read registry indices (`code/INDEX.jsonl`, `playbooks/REGISTRY.jsonl`) to search for files and schemas.

---

### td-ca5250 — Feature: Add upstream GitHub status to just orient recipe
**What:** Enhance the `just orient` command to query and print upstream Pull Request and GitHub Actions build status using the `gh` CLI when authenticated and available, ensuring full visibility into CI and remote reviews before starting local sessions.

**Acceptance:**
- [ ] Running `just orient` checks if `gh` CLI is installed and authenticated.
- [ ] If available, it retrieves and outputs current open PR status for the repository.
- [ ] If available, it retrieves and outputs the status of the last 3 GitHub Action runs/builds.
- [ ] Standardizes stdout formatting so it remains readable and handles non-TTY streams correctly.

---

### td-b6d5a3 — Feature: Implement Git pre-push hook for main branch safety
**What:** Create a reusable git pre-push hook that physically blocks direct pushes to the `main` branch from local developer or agent sessions. Add a `just install-hooks` task to copy this hook into `.git/hooks/pre-push`.

**Acceptance:**
- [ ] A script `scripts/git-hooks/pre-push` is created that checks if the branch being pushed is `main` and exits with an error code if so.
- [ ] Added `just install-hooks` recipe to `justfile` that copies the script to `.git/hooks/pre-push` and makes it executable.
- [ ] Direct pushes to `main` fail locally when tested, while pushing other branches succeeds.

---

### td-852077 — Documentation: Add PR gate hard rules to AGENTS.md
**What:** Update the "HARD RULES" and "Working Principles" in [AGENTS.md](file:///Users/petersmith/dev/github/tradingagents/AGENTS.md) to make upstream Pull Request gating an absolute, non-bypassable requirement, correcting the local-merge-only assumptions.

**Acceptance:**
- [ ] `AGENTS.md` clearly states that all merges to `main` must happen upstream through GitHub Pull Request reviews and not via local force-pushes or fast-forward direct pushes to remote `main`.
- [ ] References the git workflow playbook for the complete branch-to-PR integration steps.

---

## Exit Criteria
- [ ] `just check` passes with zero linting or type-checking issues.
- [ ] All four stories are implemented, verified, and approved.
- [ ] A debrief document is published and indexed in `debriefs/INDEX.jsonl`.
