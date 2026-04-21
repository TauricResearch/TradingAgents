# Feature 13: ADR 022 JSON Scanner Graph Facts

**Parent plan:** `docs/superpowers/plans/2026-04-19-json-scanner-graph-facts.md`

**Goal:** Add the architectural decision record that makes `scanner_graph_facts.json` the canonical scanner graph contract and defines how ADR 023 Neo4j consumes it later.

**Gap this task closes:** The parent plan references `022-json-scanner-graph-facts.md`; this task adds the ADR and cross-checks that the Neo4j successor plan consumes `scanner_graph_facts.json`.

**File to create:**
- `docs/agent/decisions/022-json-scanner-graph-facts.md`

---

## Required ADR Content

The ADR must include:

- Status: Accepted.
- Context:
  - Raw `scanner_context_packet` is too broad for ticker prompts.
  - Scanner summaries now provide structured JSON/Markdown inputs.
  - The Neo4j graph is deferred and should not parse raw summaries directly.
- Decision:
  - `scanner_graph_facts.json` is the immutable scanner-phase graph artifact.
  - Normal execution builds it after scanner completion.
  - Ticker analysis renders graph context from the artifact.
  - ADR 023 Neo4j ingests this artifact later.
- Rules:
  - Missing/corrupt required scanner inputs fail loud.
  - No silent fallback to `scanner_context_packet` in normal execution.
  - `scanner_context_packet` remains operator-resume-only with a warning banner.
  - v1 inputs are `market/*_summary.md` and `market/macro_scan_summary.json`.
  - v1 excludes ticker reports, raw scanner reports, analyst prose, and Neo4j writes.
  - Retrieval is ticker 2-hop plus compact global regime.
  - Confidence uses the plan's confidence computation table.
  - Alias registry is a living file; warnings drive updates.
- Consequences:
  - The scanner graph is reproducible and diffable.
  - Rebuild is explicit and the only overwrite path.
  - Neo4j gets a stable semantic input in ADR 023.
  - Backend/prompt wiring must fail loudly until the artifact exists.

---

## Suggested ADR Skeleton

```md
# ADR 022: JSON Scanner Graph Facts

## Status

Accepted

## Context

...

## Decision

...

## Rules

...

## Consequences

...

## Relationship To ADR 023

ADR 023 consumes `scanner_graph_facts.json`; it does not reparse raw scanner summaries.
```

---

## Step 1: Write ADR

Create `docs/agent/decisions/022-json-scanner-graph-facts.md` using the required content above.

---

## Step 2: Cross-check ADR 023 plan

Confirm `docs/superpowers/plans/2026-04-18-graphrag-knowledge-graph.md`:

- Uses ADR number 023.
- Says Neo4j ingests `scanner_graph_facts.json`.
- Mirrors the resume rule.

---

## Step 3: Run docs check

```bash
rg -n "022-json-scanner-graph-facts|023-graphrag-knowledge-graph|scanner_graph_facts.json|scanner_context_packet" docs/agent/decisions docs/superpowers/plans
```

---

## Done When

- ADR 022 exists and matches the parent plan.
- ADR 023 plan points to the JSON artifact as input.
- No plan text implies Neo4j should reparse raw scanner summaries before consuming JSON scanner graph facts.
