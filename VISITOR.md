# TradingAgents — Visitor & Auditor Orientation

> **Boot Time:** ~30 seconds. This guide is tailored for AI agents, review substrates, and developers visiting the workspace to perform self-directed reviews, audits, or code explorations.

---

## 1. Single Source of Truth (SSOT)

All project rules, coding standards, database conventions, and file-protection guidelines are declared strictly in [AGENTS.md](file:///Users/petersmith/dev/github/tradingagents/AGENTS.md). 

> [!IMPORTANT]
> **Do not duplicate rules:** To prevent documentation drift, always reference [AGENTS.md](file:///Users/petersmith/dev/github/tradingagents/AGENTS.md) as the authoritative reference for:
> - Hard rules (e.g. `DatabaseFactory` only, absolute PR-merge constraints)
> - Critical protected files (e.g. `schema.sql`, `justfile`, Hono database layers)
> - Language boundaries (Python 3.13 langgraph core vs. Bun/TypeScript dashboard)

---

## 2. Exploring the Workspace

This repository is self-indexing. To locate files, verify endpoints, or trace architectural history, read these indexing registries:

| Registry / Index | Purpose | Target Format |
|------------------|---------|---------------|
| [code/INDEX.jsonl](file:///Users/petersmith/dev/github/tradingagents/code/INDEX.jsonl) | CLI & server command registry | JSON Lines mapping commands to files |
| [playbooks/REGISTRY.jsonl](file:///Users/petersmith/dev/github/tradingagents/playbooks/REGISTRY.jsonl) | System playbooks registry | Master index of development guides |
| [debriefs/INDEX.jsonl](file:///Users/petersmith/dev/github/tradingagents/debriefs/INDEX.jsonl) | Retrospective history index | Historical debriefs from past sessions |
| [briefs/INDEX.jsonl](file:///Users/petersmith/dev/github/tradingagents/briefs/INDEX.jsonl) | System tasks and briefs index | Completed and active task briefs |

For a high-level conceptual diagram and architectural design, consult [ARCHITECTURE.md](file:///Users/petersmith/dev/github/tradingagents/ARCHITECTURE.md).

---

## 3. Workflow & Task Gating

We use a local task database CLI (`td`) to track session states and claim issues:

- `just orient` — Check current branch, status, and active tasks.
- `td usage --new-session` — Register your current session identity on boot.
- `td next` — Locate the highest priority open task.
- `td start <task-id>` — Claim and start working on a task.
- `td review <task-id>` — Request review once complete.

*Full workflow details: [playbooks/td-playbook.md](file:///Users/petersmith/dev/github/tradingagents/playbooks/td-playbook.md)*

---

## 4. Current Context Diagnostics

Run the following commands to inspect the live status of the workspace:

```bash
# Verify active branch and last commit
echo "=== BRANCH ===" && git branch --show-current
echo "=== LAST COMMIT ===" && git log -1 --oneline

# View open issues and review statuses in the td tracker
echo "=== OPEN ISSUES ===" && td list --json 2>/dev/null | jq '.issues[] | select(.status == "open") | .title' 2>/dev/null || echo "(td not available)"
echo "=== IN REVIEW ===" && td reviewable 2>/dev/null || echo "(td not available)"
```

---

## 5. Auditor / Explorer Onboarding Checklist

If you are starting a self-directed audit or exploration session, execute these steps:

1. **Orient:** Run `just orient` to see the current git status and branch.
2. **Verify Integrity:** Run `just check` to ensure all type-checkers, lints, and database checks are passing cleanly.
3. **Register:** Run `td usage --new-session` to configure your session context.
4. **Scan Registries:** Explore [code/INDEX.jsonl](file:///Users/petersmith/dev/github/tradingagents/code/INDEX.jsonl) and [playbooks/REGISTRY.jsonl](file:///Users/petersmith/dev/github/tradingagents/playbooks/REGISTRY.jsonl) to trace current components and architectural playbooks.