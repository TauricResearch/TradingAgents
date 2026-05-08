# GitNexus Playbook

## What It Is

GitNexus indexes a codebase into a knowledge graph — every function, class, call chain, cluster, and execution flow — stored in LadybugDB (a KuzuDB fork). The graph is queried via CLI commands or Cypher.

Installed globally: `npm install -g gitnexus`

---

## What Works

| Command | Use for | Example |
|---------|---------|---------|
| `context` | 360° view of a symbol (callers, callees, methods, imports) | `just gn-context TradingAgentsGraph` |
| `impact` | Blast radius — what breaks if you change a symbol | `just gn-impact propagate upstream` |
| `detect-changes` | Map uncommitted diffs to affected symbols and flows | `just gn-changes unstaged` |
| `cypher` | Raw Cypher queries against the graph | `just gn-cypher "MATCH (n:Function) RETURN n.name LIMIT 10"` |
| `analyze` | Re-index the repo | `just gn-analyze` |
| `list` | Show indexed repos and stats | `just gn-status` |

All wrapped in the justfile under the `gn` group: `just gn` to see them.

---

## What Does NOT Work

### `query` command — completely broken

The `query` command (semantic/keyword search via BM25) does not work. Root cause:

1. `analyze` intentionally skips FTS index creation to save ~2.2s (see `bm25-index.ts` comments)
2. FTS indexes are supposed to be created lazily on first query
3. But the query path opens the DB **read-only** (`pool-adapter.js` line 249: `new lbug.Database(dbPath, 0, false, true)`)
4. `CALL CREATE_FTS_INDEX(...)` fails on a read-only DB

We attempted three fixes:
- **Open DB writable**: Segfaults on first query (LadybugDB N-API crash)
- **Create FTS during analyze**: Segfaults after creating 1-2 indexes (LadybugDB can't handle sequential FTS creation in one process)
- **Separate processes per index**: Works on some runs, but `analyze` calls `process.exit(0)` before WAL is flushed, leaving the DB in an inconsistent state for subsequent opens

**Verdict:** This is a LadybugDB native binding bug. Not worth fighting. Skip `query` entirely — you have grep, Warp semantic search, and Cypher for structural queries.

### `serve` command — completely broken in practice

`gitnexus serve` starts on port 4747 and bridges the CLI index to the web UI at gitnexus.vercel.app. **It does not work.**

**Root cause:** The web UI is hosted on `gitnexus.vercel.app` (Vercel). Its Content-Security-Policy sets `default-src 'none'`, which blocks all cross-origin connections to `localhost:4747`. The browser console shows:

```
GET http://localhost:4747/ 404 (Not Found)
Connecting to 'http://localhost:4747/.well-known/appspecific/com.chrome.devtools.json'
violates Content Security Policy directive: "default-src 'none'".
```

This is an architectural impossibility: a remote web app cannot connect to a local server when CSP forbids it. No workaround without modifying Vercel's CSP headers (not possible for users).

**Verdict:** Do not use `serve`. The CLI (`context`, `impact`, `cypher`) gives you everything you need.

**Alternative for visualisation:** Use `scripts/gitnexus-to-dot.ts` to export a subgraph to Graphviz DOT format, then render to SVG/PNG locally. See `playbooks/gitnexus-usage-guide.md` for details.

---

## Recommended Workflow

### Initial setup

```bash
npm install -g gitnexus
gitnexus analyze              # from repo root
```

### Day-to-day

- **Before refactoring:** `just gn-impact <symbol>` to see blast radius
- **Exploring unfamiliar code:** `just gn-context <symbol>` to see the full picture
- **Before committing:** `just gn-changes` to verify affected scope
- **After significant changes:** `just gn-analyze` to re-index (~3s for this repo)

### Useful Cypher queries

```cypher
-- All classes
MATCH (c:Class) RETURN c.name, c.filePath

-- Functions with most callers (hotspots)
MATCH (caller)-[:RELATION]->(f:Function) RETURN f.name, count(caller) AS callers ORDER BY callers DESC LIMIT 10

-- All execution flows (property is `label`, not `name`)
MATCH (p:Process) RETURN p.label, p.processType, p.stepCount LIMIT 20

-- Node type distribution
MATCH (n) RETURN labels(n) AS type, count(*) AS cnt ORDER BY cnt DESC LIMIT 10

-- Discover properties on any node type
MATCH (p:Process) RETURN * LIMIT 1
```

---

## Generated Files

`analyze` creates two files in the repo root:

| File | Purpose | Keep? |
|------|---------|-------|
| `CLAUDE.md` | MCP integration instructions for Claude Code | Ignore — we use CLI only, not MCP |
| `AGENTS.md` | Appends a GitNexus section | Our AGENTS.md predates this — check for unwanted changes after analyze |

Both reference MCP tools we don't use. The `--skip-agents-md` flag prevents modifications:

```bash
gitnexus analyze --skip-agents-md
```

---

## LadybugDB Lessons

LadybugDB is a KuzuDB fork with Node.js N-API bindings. It has the same class of problems as SQLite defaults:

| Issue | Detail |
|-------|--------|
| Read-only incompatible with writes | DB opened read-only can't create FTS indexes (same pattern as SQLite WAL + read-only) |
| N-API segfaults | Creating multiple FTS indexes in one process crashes the native bindings |
| WAL not flushed on process.exit | `analyze` calls `process.exit(0)` which kills pending native I/O |
| 130+ open issues | Actively unstable — don't patch the installed package, wait for upstream fixes |

**Rule:** Do not modify the installed gitnexus package (`node_modules/gitnexus`). Patches get overwritten on `npm update` and the segfault issues are in the native bindings, not fixable from JS.

---

## Codebase Analysis Findings (2026-05-07)

### Summary

No structural issues found. Zero dead code in core package, no god objects, short execution chains, even cluster distribution.

### Hotspots (max fan-in)

Peak is 12 (`parse_rating`, `render_diagrams:run`). Utility functions like `safe_ticker_component` (11), `yf_retry` (10), `route_to_vendor` (10) are correctly centralised.

### File density — watch list

| File | Lines | Symbols | Why it's fine |
|------|------:|--------:|---------------|
| `cli/main.py` | 1221 | 156 | 125 are Typer command variables — structural, not complex. Split if it passes ~1500 lines. |
| `server/index.tsx` | 183 | 81 | 34 route definitions + 32 file imports — route registry, correctly centralised. |
| `server/lib/intel-compute.ts` | 416 | 73 | 66 consts — computation module, density is appropriate. |
| `tradingagents/agents/utils/agent_states.py` | 73 | 58 | TypedDict definitions — 58 symbols in 73 lines is just type declarations. |

### Cross-community flows

Longest chains are 6 steps. All data pipeline flows. Short and well-bounded.

### Dead code

Zero orphan functions in `tradingagents/`.

---

## Index Stats (TradingAgents)

```
297 files | 4,653 nodes | 6,461 edges | 106 clusters | 135 flows
Indexed at: .gitnexus/lbug (~60MB)
Analyze time: ~3s
```

---

## Version

- gitnexus: 1.6.3
- Evaluated: 2026-05-07
