# Brief: Code Registry — ast-grep Sync to code/INDEX.jsonl

**Date**: 2026-05-11
**Status**: Open
**Epic**: UNIFIED-CLI-001

## Problem

The document registry system (`reg-sync.ts` → `*/INDEX.jsonl`) covers docs, briefs, debriefs, playbooks — but not code. The codebase is invisible to `just check`. This creates a structural gap: you can see what you know, but not what you have.

The justfile is an **operational facade** — it exposes what you can do, not what the system is. It tells you `just analyze TSLA` but not what symbols the analysis module contains or what it depends on. This is fine for operations. It is not fine for development navigation, audit, or architecture understanding.

The codebase and the documents are two halves of one knowledge base. Without a code index, there is no bridge between them.

## Observations

### Requirements emerge from artefacts

Briefs do not appear from nowhere. They emerge from considering existing work:

- Document registries exist → same pattern could apply to code
- `reg-sync.ts` is established → the sync pattern is proven
- `just check` is the integration point → new sync hooks into existing pipeline
- `playbooks/td-playbook.md` was found via registry → code symbols should be findable the same way

The brief is not imposed. It is induced from the gap between what exists and what the system already knows how to do.

### ast-grep is already installed

No new tooling to install — ast-grep is available, addable to `flox.toml` if needed.

### Code index enables the bridge

Once code has a canonical index (`code/INDEX.jsonl`), the registry system becomes cross-cutting:

- Briefs link to code symbols
- Code symbols reference related briefs
- `just search <query>` hits both code and documents
- Audit questions ("what code touches LLM calls?") become answerable

## Proposed Changes

### 1. `scripts/reg-sync.ts`

Run ast-grep queries against the codebase, output `code/INDEX.jsonl`.

**Index schema:**

```json
{
  "file": "src/lib/db.ts",
  "symbols": ["DatabaseFactory.connect", "DatabaseFactory.close"],
  "patterns": ["sqlite", "singleton", "wal-mode"],
  "date": "2026-05-11",
  "meta": {
    "type": "infrastructure",
    "domain": "database",
    "owns_schema": true
  }
}
```

- `symbols`: top-level exports and important functions (ast-grep query: `function_declaration`, `class_declaration`, `export`)
- `patterns`: conceptual tags derived from domain conventions or ast-grep rule matches
- `meta.domain`: functional area (database, trading, cli, server, etc.)

**ast-grep queries to implement:**

1. All exported symbols per file
2. All `DatabaseFactory` usages (enforces convention)
3. All LLM API calls (external service touch points)
4. All file operations (I/O surface)
5. All Python package imports in tradingagents/ (boundary crossing)

### 2. Integration with `just check`

Add `reg-sync` to the check pipeline:

```bash
bun scripts/reg-sync.ts --all
bun scripts/reg-sync.ts --fix
```

Run both on `just check`. Exit non-zero if either has drift.

### 3. `just search` hits both registries

Extend `just search` (or create a new recipe) to query both `code/INDEX.jsonl` and document registries, unified.

### 4. Link briefs to code symbols

When briefs refer to code (e.g., the IG API client brief mentions `src/cli/lib/ig-instruments.ts`), the code index makes the reference verifiable and navigable.

## Implementation Order

1. `scripts/reg-sync.ts` — ast-grep → `code/INDEX.jsonl`, basic schema
2. Run on `just check` — integrate into pipeline
3. Add domain/pattern tagging — semantic enrichment
4. Extend `just search` — unified query across code + docs
5. Link existing briefs to code symbols — close the bridge

## Verification

- `bun scripts/reg-sync.ts` runs without error
- `code/INDEX.jsonl` contains entries for all `.ts`, `.tsx`, `.py` files
- `symbols` field populated for files with exports
- `just check` includes reg-sync in pipeline
- `just search "DatabaseFactory"` returns code entries + related docs

## Dependencies

- ast-grep (already installed, confirm `which ag` or `ag --version`)
- Bun (for scripts/)
- Existing `reg-sync.ts` pattern (reference implementation)

## Notes

- Start with basic symbol extraction (ast-grep default rules)
- Domain tagging can be manual initially, automated later via convention rules
- The code index is read-heavy — sync only on change, not at runtime
- Consider `watch` mode for development (ast-grep has `--watch`)

## Design Philosophy: Local Registers, Not Remote Services

Most code-intelligence solutions reach for remote services — MCP servers, Sourcegraph, GitHub Copilot, vector databases. These are powerful but come with a cost: external dependencies, API keys, network latency, potential data egress, observability gaps.

Our approach: close the gap with a local index. Same pattern as document registries — `scripts/reg-sync.ts` → `code/INDEX.jsonl`. The register is:

- **Local** — no API calls, no network dependency, no vendor lock-in
- **Silo-native** — lives in the project, boots with the project, moves with the project
- **Proven** — 5 registries already use this exact pattern (`briefs/`, `debriefs/`, `decisions/`, `playbooks/`, `docs/`)
- **Light** — a script that runs `ast-grep` and writes JSONL

The agent doesn't need a remote service to understand the codebase. It needs a local index that tells it what's in it. That's what the register provides. The silo provides the tools. The agent orients.

If a remote service is later preferred (e.g., Sourcegraph for large-codebase search), it can be added as an additional layer. The local register remains the canonical index for the silo.

---

*Owner: peter@ed.ac.uk*
*Epic: UNIFIED-CLI-001*
*Emerges from: document registry gap, justfile facade limitation, code↔docs bridge requirement*