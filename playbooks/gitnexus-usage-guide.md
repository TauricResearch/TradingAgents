---
date: 2026-05-07
tags: [playbook, gitnexus, static-analysis, refactoring, impact-analysis]
---

# GitNexus Usage Guide for TradingAgents

## Purpose

Use GitNexus to understand code structure, plan refactors safely, and verify change scope before committing. The knowledge graph is already indexed (~3s, 297 files, 4,653 symbols).

---

## Quick Start

```bash
# Check index status
just gn-status

# Re-index after significant changes (~3s)
just gn-analyze

# See all available commands
just gn
```

---

## Use Cases

### 1. Before Refactoring — Impact Analysis

**Question:** "What breaks if I change `calculateTradePlan`?"

```bash
gitnexus impact calculateTradePlan
```

**Result:**
```json
{
  "risk": "LOW",
  "impactedCount": 2,
  "byDepth": {
    "1": [{ "name": "trade-plan.tsx", "relationType": "CALLS" }],
    "2": [{ "name": "trade-plan.ts", "relationType": "CALLS" }]
  }
}
```

**Action:**
- Depth 1 = direct callers (must update)
- Depth 2+ = indirect callers (may need review)
- Risk LOW = few callers, safe to change
- Risk HIGH = many callers or cross-module — plan carefully

**Rule:** Always run `gitnexus impact <symbol>` before modifying a function with >3 callers.

---

### 2. Understanding Unfamiliar Code — Context

**Question:** "What does `DatabaseFactory` do and who uses it?"

```bash
gitnexus context DatabaseFactory
```

**Result:**
- Symbol definition (file, line range)
- Incoming: all callers
- Outgoing: all callees
- Processes: which execution flows include this symbol

**Note:** For const objects like `DatabaseFactory`, incoming/outgoing may be sparse. Use Cypher for more detailed queries.

---

### 3. Pre-Commit Verification — Detect Changes

**Question:** "What did my uncommitted changes actually touch?"

```bash
just gn-changes unstaged
```

**Result:** Maps diffs to affected symbols and execution flows.

**Action:**
- Verify no accidental changes to unrelated files
- Check if test files were updated for changed functions
- Confirm no dead code was introduced

---

### 4. Find Hotspots — Cypher Queries

**Question:** "Which functions have the most callers?"

```bash
gitnexus cypher "
  MATCH (caller)-[:RELATION]->(f:Function)
  RETURN f.name, count(caller) AS callers
  ORDER BY callers DESC
  LIMIT 10
"
```

**Question:** "Where is all the IG-related code?"

```bash
gitnexus cypher "
  MATCH (f:Function)
  WHERE f.filePath CONTAINS 'cli/trading'
     OR f.filePath CONTAINS 'trade-calculator'
  RETURN f.name, f.filePath
"
```

**Question:** "Which files have no tests?"

```bash
gitnexus cypher "
  MATCH (f:File)
  WHERE NOT f.filePath CONTAINS 'test'
    AND NOT f.filePath CONTAINS 'node_modules'
  RETURN f.filePath, f.symbolCount
  ORDER BY f.symbolCount DESC
  LIMIT 20
"
```

---

### 5. Verify IG Integration Scope

After adding IG API code, verify the graph captured it:

```bash
# Re-index to include new files
gitnexus analyze --skip-agents-md

# Check our new code is in the graph
gitnexus cypher "
  MATCH (f:Function)
  WHERE f.filePath CONTAINS 'cli/trading'
  RETURN f.name, f.filePath
  LIMIT 15
"
```

**Expected result:**
```
| f.name              | f.filePath                        |
| calculateTradePlan  | src/server/lib/trade-calculator.ts    |
| calculateATR        | src/server/lib/trade-calculator.ts    |
| getPlatform         | cli/trading/lib/platforms.ts      |
| validateMode        | cli/trading/lib/platforms.ts      |
| ...                 | ...                               |
```

---

## Concrete Scenarios

### Scenario: Add Margin Tiers to Calculator

You want to add IG's tiered margin (20% up to $7,500, 40% above) to `calculateTradePlan`.

**Step 1: Impact analysis**
```bash
gitnexus impact calculateTradePlan
# → Risk: LOW
# → Affected: trade-plan.tsx, trade-plan.ts, tests
# → Safe to change
```

**Step 2: Check callers for test coverage**
```bash
gitnexus context calculateTradePlan
# → Incoming: tests/trade-calculator.test.ts (3x), integration test, trade-plan route
# → Add test for margin tiers in trade-calculator.test.ts
```

**Step 3: Verify no dead code after change**
```bash
just gn-changes
# → Confirm only trade-calculator.ts, trade-calculator.test.ts, trade-plan.tsx changed
```

---

### Scenario: Refactor Platform Config

You want to split `cli/trading/lib/platforms.ts` into per-platform files.

**Step 1: Impact analysis**
```bash
gitnexus impact getPlatform
# → Shows all callers (plan.ts, test files)
# → Plan: update imports in all callers
```

**Step 2: Check for hardcoded platform names**
```bash
grep -r "ig\|ajbell\|aviva\|nsandi" src/cli/ src/server/routes tests/ \
  --include="*.ts" --include="*.tsx"
# → Find all references to update
```

---

## Visualisation with Graphviz

Since `gitnexus serve` is broken, use `scripts/gitnexus-to-dot.ts` to export subgraphs to Graphviz DOT format and render them locally.

### Symbol Impact Graph

```bash
# See what calls and is called by calculateTradePlan
bun scripts/gitnexus-to-dot.ts --symbol calculateTradePlan --depth 1 --render
# → graph.dot, graph.svg, graph.png
```

### Module Graph

```bash
# See all symbols and their relationships within a file
bun scripts/gitnexus-to-dot.ts --file cli/trading/commands/plan.ts --render --output plan.dot
# → plan.dot, plan.svg, plan.png
```

### Deeper Traversal

```bash
# 2-level impact analysis (can get large — use --max-nodes)
bun scripts/gitnexus-to-dot.ts --symbol DatabaseFactory --depth 2 --render --max-nodes 50
```

### Colour Coding

| Node Type | Colour |
|-----------|--------|
| Function | Blue `#4a90d9` |
| Class | Orange `#e8a838` |
| Method | Purple `#c990e8` |
| Interface | Green `#50c878` |
| File | Grey `#f5f5f5` |
| Route | Red `#ff6b6b` |
| Process | Violet `#9b59b6` |

**Requirements:** `gitnexus` (CLI) and `dot` (Graphviz). Already installed.

---

## What NOT to Use

| Command | Status | Why |
|---------|--------|-----|
| `gitnexus query` | ❌ Broken | FTS index segfaults in LadybugDB. Use `grep` or Cypher instead. |
| `gitnexus serve` | ❌ Broken | CSP on gitnexus.vercel.app blocks localhost. Impossible to fix from user side. |
| `gitnexus-to-dot.ts` | ✅ Working | Export subgraph to Graphviz DOT → SVG/PNG. See Visualisation below. |

---

## Index Maintenance

| Trigger | Action |
|---------|--------|
| After adding new directories | `gitnexus analyze --skip-agents-md` |
| After major refactor | `gitnexus analyze --skip-agents-md` |
| Before impact analysis on new code | `gitnexus analyze --skip-agents-md` |
| Daily (if actively developing) | `just gn-analyze` |

**Always use `--skip-agents-md`** — prevents overwriting our `AGENTS.md` with GitNexus boilerplate.

---

## Quick Reference

| Need | Command |
|------|---------|
| What's this function do? | `gitnexus context <symbol>` |
| What breaks if I change it? | `gitnexus impact <symbol>` |
| What did my changes touch? | `just gn-changes` |
| Re-index the repo | `just gn-analyze` |
| Custom graph query | `gitnexus cypher "MATCH ..."` |
| Visualise impact graph | `bun scripts/gitnexus-to-dot.ts --symbol X --render` |
| Visualise module graph | `bun scripts/gitnexus-to-dot.ts --file X.ts --render` |
| Index status | `just gn-status` |

---

## References

- `playbooks/gitnexus-playbook.md` — Original evaluation, limitations, Cypher examples
- `just gn` — All GitNexus just recipes
