# Decision: HTMX + SSR over SPA Framework

**Date:** 2026-05-02
**Status:** Accepted

## Context

The dashboard has 11 tabs, each with its own data. The choice was between a traditional SPA (React, Vue, Svelte) with a JSON API, or server-rendered HTML with HTMX for partial updates. The dashboard is used by a single operator, not a public audience — performance and SEO are not primary concerns.

## Decision

Server-side rendered HTML via Hono JSX, HTMX 2.0 for partial page swaps, SSE for real-time analysis streaming. No client-side framework. No client-side markdown rendering.

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| React SPA + JSON API | Doubles the codebase (client + server state); hydration complexity; overkill for single-user dashboard |
| Vue + JSON API | Same SPA overhead; no TypeScript ecosystem advantage over React |
| Svelte | Compile step adds build complexity; HTMX gives same interactivity with zero client JS |
| Alpine.js + server HTML | Viable alternative; HTMX chosen for better SSE support and `hx-trigger` declarative patterns |

## Consequences

**What became easier:**
- Single source of truth (server state is the state)
- No client-side state management
- Partial updates via HTMX `hx-get` / `hx-swap` without writing fetch() calls
- All rendering logic in one place (server views)

**What became harder:**
- HTMX + JSON APIs don't mix — `hx-swap="innerHTML"` on JSON dumps raw text into DOM
- Client-side interactivity beyond HTMX's built-in triggers requires inline scripts
- Debugging requires server logs, not browser DevTools React panels

**Constraints this imposes:**
- Every route must serve HTML (for full pages) or HTML fragments (for HTMX partials)
- `pageOrPartial(c, <View />)` pattern required for dual-mode routes
- JSON endpoints must use `hx-swap="none"` + direct `fetch()` — never HTMX auto-swap
- No npm client-side dependencies — Datatype font is the only client asset beyond HTMX

## Related

- Debrief: `debriefs/debrief-dashboard-foundation-2026-05-02.md`
- Playbook: `playbooks/htmx-playbook.md`
- Playbook: `playbooks/typescript-hono-playbook.md`
