# Tree View Playbook

**Date:** 2026-05-29
**Author:** ses_d16b99

## Lesson Learned: Shadow DOM CSS Cascade Conflicts with Safari

### What happened

The File Explorer (`/explorer`) used `@pierre/trees` — a web component library with declarative shadow DOM (`<template shadowrootmode="open">`). The SSR payload injected the component tree into the page, and the browser's native custom element lifecycle attached shadow DOM and applied the library's built-in CSS.

The layout failed silently: Safari showed a uniform black screen. Investigation revealed:

1. `@pierre/trees` shadow DOM uses `var(--trees-bg)` for all backgrounds, defaulting to `#141415` in dark mode
2. The host element's `background-color: var(--trees-bg)` cascaded through the shadow root
3. The body's `background: #0f1117` was nearly identical to the shadow DOM's `#141415` → no visual contrast
4. Safari's CSS variable resolution in shadow DOM behaves subtly differently from Chrome
5. The `:host` pseudo-class inside shadow DOM inherits CSS from the light DOM differently than expected

### Why raw HTML worked

A stripped-down version with pure inline styles (`background:#ff0000`, etc.) rendered correctly:
- Red nav panel with white text → visible
- White content panel with black text → visible

This confirmed the problem was the shadow DOM CSS cascade, not the HTML structure or server rendering.

### Root cause

`@pierre/trees` v0.x shadow DOM applies `background-color: var(--trees-bg)` to `:host`. CSS custom properties (`--trees-bg-override`) don't propagate into shadow DOM the same way they do in the light DOM. The `--trees-bg-override` on the host element only affects the light DOM layer — the shadow DOM `:host` still resolves `var(--trees-bg)` to its default `#141415`.

### Resolution

**For the File Explorer:** Build the layout as raw HTML with inline styles first. Once the layout is confirmed working, layer in `@pierre/trees` via the JS bundle only (no SSR hydration). Alternatively, use the library in a shadow-root-free mode or fork the CSS injection.

### Decision: Raw HTML Baseline

Always start with a raw HTML layout (no external CSS, no shadow DOM web components) to confirm the layout renders. Then layer in:

1. ✅ Raw HTML + inline styles → confirmed working
2. ⏳ Add content via HTMX swaps into the right panel
3. ⏳ Fold in `@pierre/trees` via JS bundle (no SSR)
4. ⏳ Restore full CSS theming once layout is solid

### When to use web components with shadow DOM

- Shadow DOM is appropriate when the component owns its entire visual surface (no external CSS influence)
- Avoid shadow DOM for layout containers that need to blend with the host page's CSS cascade
- For SSR scenarios, prefer libraries that render into the light DOM (regular HTML) rather than requiring JS hydration to attach shadow roots
- Test shadow DOM components in the target browser early — don't assume Chrome = Safari

### Routes (all three are live)

| Route | Purpose |
|-------|---------|
| `GET /explorer` | Full shell: nav panel + repo tree + content panel |
| `GET /explorer/nav/*` | Renders dashboard page content into the content panel |
| `GET /explorer/file/*` | Renders file content (markdown, JSON, syntax-highlighted code, images) |

### Files

| File | Status | Note |
|------|--------|------|
| `src/server/routes/explorer.tsx` | ✅ Working | Raw HTML, inline styles, 3 routes (shell + nav + file) |
| `src/server/views/explorer-view.tsx` | ❌ Disabled | Shadow DOM approach — kept for reference |
| `src/server/static/scripts/explorer-tree.ts` | 🔄 Standby | JS bundle for future nav tree + file tree hydration |
| `src/server/static/scripts/explorer-tree.bundle.js` | 🔄 Standby | Bundled output |