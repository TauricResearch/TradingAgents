# Project Brief: "TradingAgents File Explorer with SSR Markdown Rendering"

**Status:** Focused on core deliverables. Workflow visualization deferred.

---

## Objective

Replace **Glow** (markdown viewer) with a **tree-view file explorer** that:
1. Renders markdown files with SSR in the browser
2. Shows other file types as appropriate
3. Provides hierarchical navigation of the repository

The workflow visualization (agent state, decision trails, SSE streams) is **deferred** — re-evaluate after core file explorer ships.

---

## Scope

### P1 — Core (must ship)

| Feature | Description |
|---------|-------------|
| **Tree-view file explorer** | SSR-rendered, vanilla-hydrated `@pierre/trees` component. Hierarchical navigation of the repo. |
| **Markdown rendering** | Pick a `.md` file from the tree → render it in the panel. Replaces Glow. |
| **Context menu** | Open, Copy Path, Open in Editor. HTMX triggers for navigation. |
| **Prepared input** | Server-side tree shaping via `prepareFileTreeInput`. Client hydrates, not reconstructs. |

### P2 — Later (next sprint)

| Feature | Description |
|---------|-------------|
| **Code file rendering** | Syntax-highlighted view for `.ts`, `.tsx`, `.py` files |
| **Config file rendering** | JSON, YAML, TOML with basic formatting |
| **Search within tree** | Built-in `@pierre/trees` search |

### P3 — Deferred (nice to have, re-evaluate later)

| Feature | Description |
|---------|-------------|
| **Workflow Navigator** | Agent state, decision trails, SSE live streams |
| **Agent row decoration** | Thinking/Debating/Idle/Error status on tree rows |
| **Multi-market composition** | US/UK/crypto market branches |
| **Fault origin traversal** | Visual debugging of trade failures |
| **Historical replay** | Decision path replay from Decision Trail |

---

## Architectural decisions

### Vanilla runtime (not React)

Hono JSX does not support React hooks. Vanilla `FileTree` aligns with imperative Hono routes.

```text
Server: prepareFileTreeInput() → preloadFileTree() → SSR markup
Client: fileTree.hydrate({ fileTreeContainer }) → interactive tree
```

### Prepared input on server

Moving tree shaping to the server avoids client-side cost and makes hydration straightforward.

```typescript
// src/server/lib/tree-prep.ts
import { prepareFileTreeInput } from '@pierre/trees';

export function buildRepoTree(paths: string[]) {
  return prepareFileTreeInput(paths, {
    flattenEmptyDirectories: true,
  });
}
```

### Context menus trigger HTMX

Right-click opens context menu. Selection triggers HTMX request for file content → renders in `#content` panel.

```text
Tree selection → HTMX GET /explorer/file/:path → SSR markdown render → swap into #content
```

### File type routing

| Extension | Render strategy |
|-----------|-----------------|
| `.md` | Markdown → HTML via `marked` or custom renderer |
| `.ts`, `.tsx` | Code syntax highlight |
| `.py` | Code syntax highlight |
| `.json` | Pretty-printed JSON |
| Other | Binary indicator or raw text fallback |

---

## File structure

```text
src/server/
├── lib/
│   └── tree-prep.ts              # Prepared input builder
├── views/
│   └── explorer-view.tsx         # Tree + content panel
├── routes/
│   └── explorer.tsx              # Tree routes + file content routes
└── static/
    └── scripts/
        └── explorer-tree.js      # Vanilla tree hydration + context menu
```

---

## Implementation steps

### Step 1: Spike — confirm SSR + hydrate works

Before committing to the full plan, verify:
- `@pierre/trees/ssr` + Hono SSR renders tree markup
- Vanilla `hydrate()` attaches correctly
- Context menu triggers HTMX request

**Deliverable:** Minimal working tree with one file type rendering.

### Step 2: Core tree structure

- Repo Explorer with full filesystem paths
- Expand/collapse, search, selection
- Context menu: Open, Copy Path

**Deliverable:** `/explorer/tree` route — working file tree.

### Step 3: Markdown rendering

- Pick `.md` file from tree → render markdown in `#content`
- Replace Glow as the markdown viewer
- Syntax highlighting for code blocks in markdown

**Deliverable:** `/explorer/file/:path` route — markdown rendered.

### Step 4: Other file types

- Code files (`.ts`, `.tsx`, `.py`)
- Config files (`.json`, `.yaml`, `.toml`)
- Pretty-print or syntax highlight as appropriate

**Deliverable:** File type routing for common extensions.

---

## Deferred: Workflow Navigator

The brief originally proposed a Workflow Navigator with live agent state and SSE streams. This remains a compelling feature, but it's **deferred** until the core file explorer ships.

**Why:**
- Core deliverable (file explorer + markdown) is clear and achievable
- Workflow Navigator requires auditing existing data model first
- SSE + HTMX boundary needs more design work
- Better to ship one thing well than ship two things badly

**Re-evaluate after:** Step 4 complete. Audit existing trading graph output and SQLite schema.

---

## Opinion

The original plan tried to do too much — two trees, SSE streams, agent state, decision trails — before proving the core pattern worked. The revised plan:

1. **Proves SSR + hydrate first** (spike)
2. **Ships the file explorer** with markdown rendering (core)
3. **Adds other file types** (next sprint)
4. **Re-evaluates workflow visualization** after evidence

This is a "map that matches the territory" approach. We know we want to replace Glow. We know we want tree navigation. We don't know enough about the workflow visualization to commit to it yet — so we defer.

**Hume's Razor:** Don't invent the workflow visualization until we understand the data model.