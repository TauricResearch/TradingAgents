# Workflow Patterns: Substrate Matching

*Match the tool to the nature of the work. Shell for state, LLM for sense-making, human for decisions.*

---

## The Pattern

When a workflow has multiple phases of different *character*, use the cheapest correct tool for each phase. Do not let one tool do work it is ill-suited for.

| Phase | Nature | Right Tool | Wrong Tool |
|-------|--------|-----------|------------|
| **Capture** | Deterministic, idempotent, stateful | Shell scripts, `gh`, `defuddle` | LLM (slow, expensive, hallucinates URLs) |
| **Interpret** | Probabilistic, pattern-matching, noisy-input → structured-output | LLM (Gemini Flash, GPT-4o-mini) | Shell scripts (cannot read comprehension) |
| **Decide** | Judgment, priority, resource allocation | Human (you) | LLM (has no context on team capacity) |

---

## Case Study: PR Review Cache

### Before (high friction)

1. Create PR → wait for bots
2. Read 900 lines of raw markdown review
3. Manually extract 4 actionable issues
4. Create TDs, prioritise, assign

**Problem:** Cognitive overload. Easy to miss issues. Repetitive.

### After (two-station pipeline)

**Station 1 — Capture (deterministic)**

```bash
just pr-fetch-all   # gh → defuddle → debriefs/reviews/pr-N.md
```

Properties: idempotent, free, no API keys, no hallucination risk.

**Station 2 — Interpret (probabilistic)**

```bash
just pr-summarize 8   # LLM → structured checklist
```

Properties: ~3K tokens, fractions of a penny, 4 issues extracted from 900 lines.

**Station 3 — Decide (human)**

Read `debriefs/reviews/pr-8.md`, create TDs, prioritise, assign to agents.

---

## Historical Analogy: Watt's Separate Condenser

James Watt did not invent the steam engine. Newcomen did. Watt made it practical by separating the cooling function (the condenser) from the cylinder. Each part did one thing, did it well, and the whole system became 4× more efficient.

This pattern is the same: separate capture from interpretation. Let the shell do what shells do well (state, pipes, idempotence). Let the LLM do what LLMs do well (reading comprehension, pattern extraction). Let the human do what only humans can do (judgment, priority, delegation).

---

## Anti-Patterns

| Anti-Pattern | Why It Fails |
|-------------|--------------|
| "One script to rule them all" | LLM does fetching → slow, expensive, hallucinates URLs. Shell does interpretation → misses nuance, cannot structure output. |
| "SQLite database for ephemeral PRs" | Adds schema, migration, query complexity. Markdown is human-readable, git-tracked, and sufficient. |
| "Daemon that polls every 5 minutes" | Burns API credits and CPU for no gain. PRs are event-driven; fetch on demand. |
| "LLM decides priorities" | Has no context on team capacity, dependencies, or business value. |

---

## Heuristic

> **If the work is deterministic, use a deterministic tool.**
> **If the work requires judgment, use a human.**
> **Only use an LLM where the input is noisy and the output must be structured.**

Do not make the piston cleverer. Give each job its proper station.
