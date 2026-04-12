# Graph Report - .  (2026-04-12)

## Corpus Check
- Corpus is ~9,921 words - fits in a single context window. You may not need a graph.

## Summary
- 62 nodes · 60 edges · 17 communities detected
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 3 edges (avg confidence: 0.78)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Graph Node Utils|Graph Node Utils]]
- [[_COMMUNITY_Frontend Stack & Core Components|Frontend Stack & Core Components]]
- [[_COMMUNITY_Event & Run Lifecycle|Event & Run Lifecycle]]
- [[_COMMUNITY_Run Control Flow|Run Control Flow]]
- [[_COMMUNITY_API & WebSocket Config|API & WebSocket Config]]
- [[_COMMUNITY_Auth & Multi-Tenancy|Auth & Multi-Tenancy]]
- [[_COMMUNITY_App Entry Point|App Entry Point]]
- [[_COMMUNITY_Ticker & Run Start|Ticker & Run Start]]
- [[_COMMUNITY_Metric Header UI|Metric Header UI]]
- [[_COMMUNITY_Portfolio Viewer|Portfolio Viewer]]
- [[_COMMUNITY_Agent Stream Hook|Agent Stream Hook]]
- [[_COMMUNITY_Tailwind Config|Tailwind Config]]
- [[_COMMUNITY_Vite Config|Vite Config]]
- [[_COMMUNITY_PostCSS Config|PostCSS Config]]
- [[_COMMUNITY_Main Entry|Main Entry]]
- [[_COMMUNITY_Vite Env Types|Vite Env Types]]
- [[_COMMUNITY_Theme Config|Theme Config]]

## God Nodes (most connected - your core abstractions)
1. `AgentOS Frontend` - 11 edges
2. `loadHistory()` - 5 edges
3. `WebSockets` - 3 edges
4. `CommandCenter Component` - 3 edges
5. `useAgentStream Hook` - 3 edges
6. `AuthContext` - 3 edges
7. `TradingAgents Observability Dashboard` - 3 edges
8. `parseTickerInput()` - 2 edges
9. `loadPausedRun()` - 2 edges
10. `startRun()` - 2 edges

## Surprising Connections (you probably didn't know these)
- `AgentOS Frontend` --references--> `AuthContext`  [EXTRACTED]
  README.md → README.md  _Bridges community 1 → community 5_

## Hyperedges (group relationships)
- **AgentOS Frontend Tech Stack** — readme_react, readme_vite, readme_chakra_ui, readme_axios, readme_websockets, readme_react_context_hooks [EXTRACTED 1.00]
- **AgentOS Frontend Core Components** — readme_command_center, readme_portfolio_component, readme_useagentstream, readme_authcontext [EXTRACTED 1.00]
- **AgentOS Communication Layer** — readme_axios, readme_websockets, readme_useagentstream [INFERRED 0.85]

## Communities

### Community 0 - "Graph Node Utils"
Cohesion: 0.14
Nodes (0): 

### Community 1 - "Frontend Stack & Core Components"
Cohesion: 0.29
Nodes (11): AgentOS Frontend, Axios, Chakra UI, CommandCenter Component, Portfolio Component, React, React Context / Hooks, TradingAgents Observability Dashboard (+3 more)

### Community 2 - "Event & Run Lifecycle"
Cohesion: 0.22
Nodes (0): 

### Community 3 - "Run Control Flow"
Cohesion: 0.4
Nodes (5): loadHistory(), loadPausedRun(), resumeRun(), stopRun(), submitPhase3Decision()

### Community 4 - "API & WebSocket Config"
Cohesion: 0.67
Nodes (2): buildWebSocketUrl(), getBackendOrigin()

### Community 5 - "Auth & Multi-Tenancy"
Cohesion: 0.67
Nodes (3): AuthContext, Mock Auth, Multi-Tenant Support

### Community 6 - "App Entry Point"
Cohesion: 1.0
Nodes (0): 

### Community 7 - "Ticker & Run Start"
Cohesion: 1.0
Nodes (2): parseTickerInput(), startRun()

### Community 8 - "Metric Header UI"
Cohesion: 1.0
Nodes (0): 

### Community 9 - "Portfolio Viewer"
Cohesion: 1.0
Nodes (0): 

### Community 10 - "Agent Stream Hook"
Cohesion: 1.0
Nodes (0): 

### Community 11 - "Tailwind Config"
Cohesion: 1.0
Nodes (0): 

### Community 12 - "Vite Config"
Cohesion: 1.0
Nodes (0): 

### Community 13 - "PostCSS Config"
Cohesion: 1.0
Nodes (0): 

### Community 14 - "Main Entry"
Cohesion: 1.0
Nodes (0): 

### Community 15 - "Vite Env Types"
Cohesion: 1.0
Nodes (0): 

### Community 16 - "Theme Config"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **4 isolated node(s):** `Chakra UI`, `React Context / Hooks`, `Multi-Tenant Support`, `Mock Auth`
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `App Entry Point`** (2 nodes): `App()`, `App.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Ticker & Run Start`** (2 nodes): `parseTickerInput()`, `startRun()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Metric Header UI`** (2 nodes): `MetricHeader()`, `MetricHeader.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Portfolio Viewer`** (2 nodes): `fetchList()`, `PortfolioViewer.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Agent Stream Hook`** (2 nodes): `useAgentStream.ts`, `useAgentStream()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Tailwind Config`** (1 nodes): `tailwind.config.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Vite Config`** (1 nodes): `vite.config.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `PostCSS Config`** (1 nodes): `postcss.config.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Main Entry`** (1 nodes): `main.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Vite Env Types`** (1 nodes): `vite-env.d.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Theme Config`** (1 nodes): `theme.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AgentOS Frontend` connect `Frontend Stack & Core Components` to `Auth & Multi-Tenancy`?**
  _High betweenness centrality (0.037) - this node is a cross-community bridge._
- **Why does `AuthContext` connect `Auth & Multi-Tenancy` to `Frontend Stack & Core Components`?**
  _High betweenness centrality (0.013) - this node is a cross-community bridge._
- **Why does `loadHistory()` connect `Run Control Flow` to `Event & Run Lifecycle`?**
  _High betweenness centrality (0.002) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `CommandCenter Component` (e.g. with `TradingAgents Observability Dashboard` and `useAgentStream Hook`) actually correct?**
  _`CommandCenter Component` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Chakra UI`, `React Context / Hooks`, `Multi-Tenant Support` to the rest of the system?**
  _4 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Graph Node Utils` be split into smaller, more focused modules?**
  _Cohesion score 0.14 - nodes in this community are weakly interconnected._