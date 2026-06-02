---
date: 2026-06-01
updated_by: pi
status: Accepted
---

# Decision: Retain Custom Dark-Theme Stylesheet — Reject Sakura.css

**Date:** 2026-06-01
**Updated by:** pi
**Status:** Accepted

## Context

The suggestion to replace the project's custom stylesheet (`src/server/static/style.css`, 1,078 lines) with a CDN-loaded classless CSS framework (sakura.css v1.5.1) was evaluated. TradingAgents is a dark-theme data dashboard with 14+ views, custom HTMX-driven navigation, a multi-panel file explorer, and an oklch-based colour system — not a content site or greenfield project.

## Decision

**Reject sakura.css.** Retain the existing custom stylesheet as the authoritative styling source. Evaluate incremental CSS refactoring as a separate concern if needed.

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| Drop sakura.css as a replacement for `style.css` | Sakura.css is a light-theme classless typography reset designed for content sites. It sets `background-color: #f9f9f9` and `max-width: 38em` on `body`, which would destroy the dark theme, collapse the explorer layout, and break button styling in every view. |
| Load sakura.css as an additional layer on top of `style.css` | Cascade conflicts would produce unpredictable results — sakura.css applies global styles to `body`, `button`, `input`, `table`, and `pre` without scoping. The two stylesheets fight over the same elements. |
| Scoped use of sakura.css (e.g., only on a new page) | Adds a CDN dependency that fails offline (dashboard runs on `localhost:3000`) and duplicates baseline typography rules already present in `style.css`. |
| Adopt sakura.css and rewrite the dashboard to fit its classless model | Equivalent to rebuilding the UI from scratch. The dashboard's custom components (nav tabs, explorer layout, sentiment chips, kanban columns, datatype font) have no equivalent in a classless framework. |

## Consequences

**What became easier:**
- The design system remains stable and predictable — no cascade conflicts, no CDN outages, no silent visual breakage
- Dark theme, oklch colour variables, and all custom components continue to work as designed
- Offline development remains possible (all assets served from `localhost`)

**What became harder:**
- CSS cleanup must be done incrementally rather than via wholesale replacement
- Any future CSS framework evaluation must account for the existing design system's constraints

**Constraints this imposes:**
- All CSS lives in `src/server/static/style.css` (or future co-located component stylesheets imported from it) — no classless framework overlays
- No CDN-hosted stylesheet dependencies without subresource integrity and version pinning
- Stylesheet changes must be tested against all 14+ views, not just the one being modified

## Related

- Brief: `briefs/2026-06-01-brief-sakura-css-evaluation.md`
- Playbook: `playbooks/ui-design-playbook.md`
- Existing stylesheet: `src/server/static/style.css` (1,078 lines, dark theme, oklch colour system)
