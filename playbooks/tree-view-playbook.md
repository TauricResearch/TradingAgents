# Tree View SSR Playbook

## Project identity

| Concern | Tech | Role |
|---------|------|------|
| Rendering | Hono JSX + `@pierre/trees/vanilla` | SSR + client hydration |
| Reactive events | Context menus → HTMX/SSE | Reactivity trigger |
| State surface | Prepared input from Hono routes | Path-first, server-authoritative |
| Navigation | Hono route handlers | Routing layer |

---

## Core principle: Vanilla, not React

TradingAgents uses **vanilla `@pierre/trees`** for the tree runtime, not the React wrapper. This is the correct choice because:

1. Hono's JSX does not support React-style hooks or controlled components
2. Vanilla model (`new FileTree(...)`) aligns with the imperative Hono route pattern
3. SSR hydration (`hydrate({ fileTreeContainer })`) attaches to server-preloaded markup
4. Context menus and mutations stay path-first, decoupled from React state

Do not reach for `@pierre/trees/react`. If React patterns appear in design discussions, redirect to vanilla + Hono.

---

## Two distinct tree types

The playbook covers two separate trees with different semantics:

### Type 1: Repo Explorer (static)

Navigates the repository structure. Path-first identity maps directly to filesystem paths.

```
TradingAgents/
├── tradingagents/           (Python core)
│   ├── agents/
│   │   ├── analysts/
│   │   ├── researchers/
│   │   └── traders/
│   └── graph/
├── src/                     (TypeScript dashboard)
│   ├── server/
│   │   ├── routes/
│   │   ├── views/
│   │   └── lib/
│   └── cli/
├── playbooks/
└── justfile
```

**Characteristics:**
- Static prepared input (generated at build or startup)
- No live agent state
- Context menu: "Open", "Copy Path", "Open in Editor"
- Replaces flat nav with hierarchical structure

### Type 2: Workflow Navigator (dynamic)

Navigates the active trading workflow. Paths map to agent/decision trees, not files.

```
TradingAgents/
├── Market Context/
│   ├── feeds/               (Live data feeds)
│   ├── sentiment/           (Sentiment cache)
│   └── regime/              (Current market regime)
├── Agent Teams/
│   ├── analysts/
│   │   ├── fundamentals/    (Fundamental analyst)
│   │   ├── sentiment/       (Sentiment analyst)
│   │   ├── news/            (News analyst)
│   │   └── technical/       (Technical analyst)
│   ├── researchers/
│   │   ├── bullish/         (Bullish researcher)
│   │   └── bearish/         (Bearish researcher)
│   └── traders/
│       └── decision-team/   (Trading decision)
├── Decision Trail/
│   ├── [session-id]/
│   │   ├── analyst-reports/
│   │   ├── debate-round-N/
│   │   └── final-signal/
│   └── [historical-sessions]/
└── Governance/
    ├── risk-management/
    └── portfolio-manager/
```

**Characteristics:**
- Dynamic prepared input (from SQLite + live agent state)
- Agent status via `renderRowDecoration` (Thinking/Debating/Idle/Error)
- Context menu triggers SSE streams for live agent rationale
- Decision paths are traversable, not just displayed

---

## Implementation layers

### Layer 1: Server-side prepared input

Both tree types require prepared input generated on the server. This is not optional — raw `paths` is only for demos.

```typescript
// src/server/lib/tree-prep.ts
import { prepareFileTreeInput } from '@pierre/trees';

export interface TreeNode {
  path: string;
  label: string;
  icon?: string;
  agentState?: 'thinking' | 'debating' | 'idle' | 'error';
  decisionTime?: string;
}

export function buildRepoTree(paths: string[]) {
  return prepareFileTreeInput(paths, {
    flattenEmptyDirectories: true,
  });
}

export function buildWorkflowTree(agents: AgentState[]) {
  const paths = agents.map(a => a.path);
  const prepared = prepareFileTreeInput(paths, { flattenEmptyDirectories: true });
  // Attach agent state as metadata for renderRowDecoration
  return prepared;
}
```

### Layer 2: SSR preload

Use `@pierre/trees/ssr` for first-paint performance on large trees.

```typescript
// src/server/routes/repo.tsx
import { preloadFileTree } from '@pierre/trees/ssr';
import { buildRepoTree } from '../lib/tree-prep.ts';

repoRouter.get('/tree', async (c) => {
  const paths = await getRepoPaths();  // filesystem scan or cached index
  const preparedInput = buildRepoTree(paths);
  
  const payload = preloadFileTree({
    preparedInput,
    id: 'repo-tree',
    initialExpandedPaths: ['src/server', 'tradingagents/agents'],
    search: true,
    initialVisibleRowCount: 14,
  });
  
  return c.html(<RepoTreeView payload={payload} paths={paths} />);
});
```

### Layer 3: Vanilla hydration in view

The view renders server markup and hydrates with vanilla `FileTree`.

```tsx
// src/server/views/repo-tree-view.tsx
import { FileTree } from '@pierre/trees';
import type { FileTreeSsrPayload } from '@pierre/trees/ssr';

interface RepoTreeViewProps {
  payload: FileTreeSsrPayload;
  paths: readonly string[];
}

export function RepoTreeView({ payload, paths }: RepoTreeViewProps) {
  // Server renders initial tree via payload
  // Client hydrates via external script
  return (
    <div class="tree-panel">
      <div id="repo-tree" 
           hx-get="/repo/node-details"
           hx-trigger="click"
           hx-swap="none">
        {/* Server pre-renders tree here via payload */}
      </div>
      <script src="/static/scripts/repo-tree.js" />
    </div>
  );
}
```

```javascript
// src/server/static/scripts/repo-tree.js
import { FileTree } from '@pierre/trees';

const fileTree = new FileTree({
  preparedInput: window.__PREPARED_INPUT__,
  id: 'repo-tree',
  initialExpandedPaths: ['src/server', 'tradingagents/agents'],
  search: true,
  initialVisibleRowCount: 14,
});

const container = document.getElementById('repo-tree');
if (container) {
  fileTree.hydrate({ fileTreeContainer: container });
}

// Context menu: Open, Copy Path, Open in Editor
fileTree.setComposition({
  contextMenu: {
    enabled: true,
    triggerMode: 'both',
    buttonVisibility: 'when-needed',
  },
});
```

### Layer 4: Context menu as reactivity trigger

Context menus are the event bus, not React state. They trigger HTMX requests or SSE streams.

```tsx
// src/server/views/workflow-tree-view.tsx
export function WorkflowTreeView({ payload, agents }: WorkflowTreeViewProps) {
  return (
    <div class="tree-panel workflow-panel">
      <div id="workflow-tree" 
           data-session-id={currentSessionId}
           hx-get="/workflow/agent-details"
           hx-trigger="click[target.closest('[data-agent-path]')]"
           hx-swap="none">
      </div>
      <div id="agent-stream" class="stream-panel" hx-get="/workflow/stream/init" hx-trigger="load">
      </div>
      <script src="/static/scripts/workflow-tree.js" />
    </div>
  );
}
```

```javascript
// src/server/static/scripts/workflow-tree.js
import { FileTree } from '@pierre/trees';

const fileTree = new FileTree({
  preparedInput: window.__WORKFLOW_PREPARED__,
  id: 'workflow-tree',
  initialExpandedPaths: ['Market Context', 'Agent Teams/analysts'],
  search: true,
  fileTreeSearchMode: 'hide-non-matches',
  // Agent state decoration
  renderRowDecoration: ({ item }) => {
    const state = window.__AGENT_STATES__[item.path];
    if (!state) return null;
    return {
      icon: state === 'thinking' ? 'icon-thinking' 
          : state === 'debating' ? 'icon-debate'
          : state === 'error' ? 'icon-error'
          : 'icon-idle',
      title: `Agent: ${state}`,
    };
  },
  composition: {
    contextMenu: {
      enabled: true,
      triggerMode: 'both',
      buttonVisibility: 'when-needed',
    },
  },
});

fileTree.render({ fileTreeContainer: document.getElementById('workflow-tree') });

// Context menu handler → SSE stream
fileTree.onMutation('select', ({ path }) => {
  // Trigger SSE stream for selected agent/debate node
  const sessionId = document.getElementById('workflow-tree').dataset.sessionId;
  htmx.ajax('GET', `/workflow/stream/${encodeURIComponent(path)}`, {
    target: '#agent-stream',
    swap: 'innerHTML',
  });
});
```

---

## SSE stream integration

The Workflow Navigator uses SSE for live agent updates. Context menu selection triggers the SSE stream.

```typescript
// src/server/routes/workflow-stream.tsx
workflowRouter.get('/stream/:agentPath', async (c) => {
  const agentPath = c.req.param('agentPath');
  
  const stream = new ReadableStream({
    start(controller) {
      const encoder = new TextEncoder();
      
      // Send agent status
      controller.enqueue(encoder.encode(
        `data: ${JSON.stringify({ type: 'start', agentPath })}\n\n`
      ));
      
      // Poll agent state and stream updates
      const interval = setInterval(async () => {
        const state = await getAgentState(agentPath);
        controller.enqueue(encoder.encode(
          `data: ${JSON.stringify({ type: 'agent_report', ...state })}\n\n`
        ));
      }, 2000);
      
      c.req.raw.signal.addEventListener('abort', () => {
        clearInterval(interval);
        controller.close();
      });
    },
  });
  
  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
    },
  });
});
```

SSE event types:
- `start`: Stream initiated
- `agent_report`: Live agent rationale
- `debate_round`: New debate contribution
- `decision`: Trading decision finalized
- `complete`: Stream closed
- `error`: Agent failure

---

## Context menu command vocabulary

### Repo Explorer commands

| Command | Action | Persistence |
|---------|--------|-------------|
| Open | Navigate to file detail view | HTMX swap |
| Copy Path | Copy canonical path to clipboard | Client-side |
| Open in Editor | Launch external editor | Shell exec via API |
| Delete | Remove file (with confirmation) | Server action |
| Rename | Inline rename | Server action |

### Workflow Navigator commands

| Command | Action | Persistence |
|---------|--------|-------------|
| Stream Live | Start SSE stream for agent | SSE connection |
| Stop Stream | End SSE stream | SSE cleanup |
| View Reports | Navigate to agent reports | HTMX swap |
| Quarantine | Mark agent/debate as quarantined | SQLite |
| Barnacle Remove | Prune stale history node | SQLite |
| Replay Path | Replay decision from this node | Load historical data |
| Export Debate | Export debate transcript | File download |

---

## Data flow patterns

### Static tree (Repo Explorer)

```
[Build/Startup] → [Path scan] → [prepareFileTreeInput] 
    → [preloadFileTree] → [SSR markup] → [hydrate]
```

### Dynamic tree (Workflow Navigator)

```
[SQLite + Agent state] → [TreeBuilder] → [prepareFileTreeInput]
    → [preloadFileTree] → [SSR markup] → [hydrate]
    → [Context menu select] → [SSE stream] → [HTMX update]
```

---

## File structure

```
src/server/
├── lib/
│   ├── tree-prep.ts              # Prepared input builders
│   ├── repo-tree-data.ts         # Repo tree data fetching
│   └── workflow-tree-data.ts     # Workflow tree data fetching
├── views/
│   ├── repo-tree-view.tsx        # Repo Explorer component
│   ├── workflow-tree-view.tsx    # Workflow Navigator component
│   └── partials/
│       ├── tree-node.tsx         # Reusable tree node partial
│       └── agent-stream.tsx      # SSE stream display
├── routes/
│   ├── repo-tree.tsx             # Repo Explorer routes
│   ├── workflow-tree.tsx         # Workflow Navigator routes
│   └── workflow-stream.tsx       # SSE stream endpoints
└── static/
    └── scripts/
        ├── repo-tree.js          # Vanilla tree hydration + context menu
        └── workflow-tree.js      # Vanilla tree + SSE integration
```

---

## Context menu reactivity pattern (HTMX + SSE)

Context menus trigger reactivity through HTMX requests and SSE streams, not React state. The pattern:

1. **Selection** → Tree model updates selection state (vanilla)
2. **Context menu open** → Render menu from `composition.renderContextMenu` (vanilla DOM)
3. **Command select** → HTMX request or SSE connection initiated
4. **Response** → HTMX swap updates `#content` panel; SSE updates `#agent-stream`
5. **Model update** → `setGitStatus`, `setIcons`, `renderRowDecoration` for visual feedback

This keeps Hono as the routing authority while trees remain the navigation surface.

---

## Naming conventions

- Tree IDs: `repo-tree`, `workflow-tree`
- Prepared input: `__REPO_PREPARED__`, `__WORKFLOW_PREPARED__`
- Agent states: `thinking`, `debating`, `idle`, `error`
- SSE event types: `start`, `agent_report`, `debate_round`, `decision`, `complete`, `error`
- Context menu commands: lowercase with hyphens (`stream-live`, `barnacle-remove`)

---

## Validation

```bash
# Check tree components load
curl -s http://localhost:3000/repo/tree | grep 'id="repo-tree"'

# Check SSR hydration
curl -s http://localhost:3000/repo/tree | grep 'data-trees-ssr'

# Check SSE endpoint
curl -s http://localhost:3000/workflow/stream/analysts/sentiment

# Verify prepared input in page
curl -s http://localhost:3000/repo/tree | grep '__PREPARED_INPUT__'
```

---

## Experimental proposals

The following are optional enhancements to evaluate during the experiment phase.

### EXP-1: Agent state as row decoration

Use `renderRowDecoration` to display live agent status (Thinking/Debating/Idle/Error) directly on tree rows.

**Implementation:**
```typescript
renderRowDecoration: ({ item }) => {
  const state = agentStates.get(item.path);
  if (!state) return null;
  const icons = {
    thinking: { icon: 'icon-thinking', text: '💭', title: 'Thinking...' },
    debating: { icon: 'icon-debate', text: '⚔️', title: 'In debate' },
    idle: { icon: 'icon-idle', text: '💤', title: 'Idle' },
    error: { icon: 'icon-error', text: '⚠️', title: 'Error' },
  };
  return icons[state];
}
```

**Decision trigger:** Evaluate after initial workflow tree is functional. If agent state updates cause flicker or performance issues, fall back to git-status style markers.

### EXP-2: Decision path replay

Traversable historical decision paths in the tree. Click any node in `Decision Trail/` to replay the agent debate from that point.

**Implementation:**
- Store debate transcripts in SQLite with session + round indices
- Tree paths map to `Decision Trail/[session]/[round]/`
- Context menu "Replay" triggers HTMX load of historical stream
- Visual indicator (play icon) on nodes with replayable content

**Decision trigger:** Evaluate if `Decision Trail` tree depth exceeds 20 levels. If so, virtual scrolling and lazy-load replay may be needed.

### EXP-3: Multi-market tree composition

Composite tree showing multiple market contexts (e.g., NASDAQ, LSE, crypto) as parallel branches.

**Implementation:**
```typescript
const multiMarketTree = prepareFileTreeInput([
  'US/analysts/fundamentals',
  'US/analysts/sentiment',
  'UK/analysts/fundamentals',
  'UK/analysts/sentiment',
  'CRYPTO/analysts/fundamentals',
]);
```

**Decision trigger:** Evaluate if number of concurrent markets exceeds 5. If so, consider lazy-loading market branches on expansion.

### EXP-4: Barnacle removal context menu

Right-click pruning of stale agent logs and deprecated research notes directly from the tree.

**Implementation:**
```typescript
composition: {
  contextMenu: {
    enabled: true,
    triggerMode: 'both',
  },
}
// Context menu: "Quarantine", "Remove Stale", "Delete"
```

**Decision trigger:** Evaluate if `quarantine` flag in SQLite causes schema drift. If so, use soft-delete with `WHERE active = 1` filter.

### EXP-5: Visual debugging — fault origin traversal

On trade failure, traverse tree to specific agent and debate branch where faulty logic originated.

**Implementation:**
- Tree path maps to `Decision Trail/[session]/[round]/agents/[agent]/`
- "Fault origin" flag on debate nodes with errors
- Highlight path from root to fault node in red
- Context menu: "Debug from here" → load agent rationale at that point

**Decision trigger:** Evaluate if SSE stream can include fault context without overwhelming the stream. If so, prioritize EXP-1 (agent state) first.

---

## Forbidden patterns

| Pattern | Rationale | Correct alternative |
|---------|-----------|---------------------|
| `@pierre/trees/react` | Hono does not support React hooks | Use vanilla runtime |
| React-style `style={{...}}` | Hono JSX requires string style | Use `<div style="...">` |
| Raw `paths` for large trees | Client-side shaping is expensive | Use `prepareFileTreeInput` on server |
| Tree state in React context | Context menus are the event bus | HTMX + SSE for reactivity |
| Inline `<script>` in views | Hono HTML-encodes quotes, breaking JS | External JS file via `<script src>` |
| DOM scraping for tree state | Model is the source of truth | Use `fileTree.getSelectedPaths()`, `getFocusedPath()` |

---

## Quick reference

```bash
# Install @pierre/trees
bun add @pierre/trees

# SSR preload
import { preloadFileTree } from '@pierre/trees/ssr';

# Vanilla tree
import { FileTree } from '@pierre/trees';

# Prepared input
import { prepareFileTreeInput } from '@pierre/trees';

# Check tree renders
curl -s http://localhost:3000/repo/tree | grep 'id="repo-tree"'
```