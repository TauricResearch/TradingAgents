# Brief: Sakura.css Drop-in Stylesheet

**Date:** 2026-06-01
**Status:** Rejected

---

## Task: Replace custom CSS with sakura.css CDN link

**Objective:** Drop `<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/sakura.css/css/sakura.css">` into the web app and remove the custom stylesheet.

## What

- [ ] Add sakura.css CDN link to `layout.tsx` `<head>`
- [ ] Remove `src/server/static/style.css` (1,078 lines)
- [ ] Verify all views still render functionally

## Opinion: Reject

Sakura.css is a fine library for greenfield projects that want a clean typographic baseline with zero effort. But it is a poor fit for TradingAgents for three reasons:

### 1. It would destroy the existing design system

TradingAgents has a 1,078-line dark-theme stylesheet built on oklch color variables, a specific nav system with HTMX-driven tab states, and custom components (explorer layout, markdown-body, datatype font, sentiment chips, screening tables, kanban columns). Sakura.css would:

- **Clobber the dark theme** — sakura.css is light-only (`body { background-color: #f9f9f9; color: #4a4a4a }`), overriding every `--bg`, `--surface`, `--text` variable
- **Force `max-width: 38em` on body** — collapses the dashboard into a narrow reading column, breaking the multi-panel explorer layout and all data tables
- **Reset all form styles** — overrides button, input, and select styling in 14 views
- **Override HTMX nav system** — sakura.css styles `button` globally (teal background, white text), conflicting with the `.tab` button pattern

### 2. It introduces an unnecessary CDN dependency

- **Fails offline** — the dashboard runs locally on `localhost:3000`. A CDN dependency means it breaks without internet
- **Version lock risk** — `sakura.css` on jsdelivr resolves to latest. A future update could silently change styling with no code diff
- **No subresource integrity** — no `integrity` attribute means no way to detect tampering or cache corruption

### 3. It's solving a problem we don't have

Sakura.css is designed for content sites (blogs, documentation, personal pages) that want "pretty by default" without writing CSS. TradingAgents is a data-dense dashboard with custom components, HTMX interactions, and a carefully tuned dark theme. The stylesheet isn't debt — it's the UI.

**The current stylesheet is not broken.** It uses oklch color math, CSS custom properties, and a consistent design language. Replacing it with a classless reset framework would be a regression, not an improvement.

### What would be useful instead

If the goal is cleaner CSS, the right approach is **incremental refactoring**, not replacement:

| Approach | Cost | Benefit |
|----------|------|---------|
| Extract component CSS to co-located files | Low | Reduces file size, improves locality |
| Add CSS custom properties for spacing scale | Low | Reduces magic numbers |
| Adopt sakura.css | High | Destroys existing UI, adds CDN dependency |

## Technical Notes

- Current stylesheet: 1,078 lines, served as `/static/style.css` with immutable cache headers
- Sakura.css: ~1.5KB gzipped, classless, light-theme only
- The `just check` gate would still pass (no CSS linting) — but every page would look broken
- If sakura.css must be evaluated, do it in a **fresh branch** with a **single test page**, not by replacing the production stylesheet

## Decision

**Rejected.** The cost of replacing the existing design system outweighs any benefit. If CSS refactoring is desired, open a separate brief for incremental cleanup of the existing stylesheet.
