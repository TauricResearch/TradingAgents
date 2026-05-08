# Decision: Bun + Hono as Dashboard Stack

**Date:** 2026-05-02
**Status:** Accepted

## Context

The TradingAgents dashboard needed a web server. The upstream Python package uses LangGraph + FastAPI patterns, but we needed real-time SSE streaming, server-side HTML rendering, and subprocess management. The ecosystem choice was between staying in Python (FastAPI/Flask), using Node.js (Express), or adopting Bun.

## Decision

Bun runtime with Hono web framework, server-side JSX rendering via Hono's built-in JSX support, HTMX for client interactivity.

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| FastAPI (Python) | Already used by upstream but SSE streaming is clunky; no native JSX; Python subprocess management from Python adds no value |
| Express (Node.js) | Mature but slower; no native TypeScript; requires tsc transpilation step |
| Next.js / React SPA | Client-side rendering adds complexity for a dashboard; hydration issues with SSE; overkill for 11 tabs |

## Consequences

**What became easier:**
- Native TypeScript execution without transpilation
- SSE streaming via Hono's stream API
- Server-side markdown rendering (marked library)
- Subprocess spawning with Bun's native API
- Single-file components (`.tsx`) without build tooling

**What became harder:**
- Bun ecosystem is smaller than Node — fewer middleware packages
- Hono JSX has subtle differences from React JSX (style props are strings, no `className`)
- Some Node libraries need Bun polyfills

**Constraints this imposes:**
- Must use Hono JSX conventions, not React patterns
- `/** @jsxImportSource hono/jsx */` required in every `.tsx` file
- Biome linter must be configured for Hono JSX, not React JSX

## Related

- Debrief: `debriefs/debrief-dashboard-foundation-2026-05-02.md`
- Playbook: `playbooks/typescript-hono-playbook.md`
- Playbook: `playbooks/htmx-playbook.md`
