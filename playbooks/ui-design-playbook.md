# UI Design Playbook — TradingAgents Minimalist CLI-Adjacent UI

> **Source of truth** for all visual design tokens. ARCHITECTURE.md references this file.
> **CI gate:** `scripts/py/validate_design_tokens.py` must pass before any CSS commit.
> **Last reviewed:** 2026-05-24 (aligns with `briefs/2026-05-23-brief-google-design-md.md`)

---

## 1. Design Tokens

```yaml
system:
  name: "TradingAgents CLI-Adjacent UI"
  version: "1.0.0"
  philosophy: "Deductive Minimalism / Brutal Utility"

typography:
  font_family: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"
  base_size: "14px"
  line_height: "1.5"

colors:
  background: "#0d1117"       # Dark slate / high contrast canvas
  surface: "#161b22"          # Card / module boundary
  border: "#30363d"           # Thin structural separator
  text_primary: "#c9d1d9"     # Off-white data stream
  text_secondary: "#8b949e"   # Muted metadata / labels (WCAG AA: 5.62:1 on surface)
  text_low_emphasis: "#6e7681"  # AA large only (3.0:1) — large text, metadata, low-emphasis labels
  accent_green: "#2ea44f"     # Position open / positive metric / execution success
  accent_red: "#da3633"       # Position stopped / stop-loss trigger / failure
  accent_amber: "#d29922"     # Pending order / metric warning

layout:
  max_width: "1200px"
  grid_gap: "16px"
  border_radius: "0px"        # Sharp corners / brutalist layout boundary
  padding_base: "12px"

```

> **WCAG note:** `#8b949e` on `#161b22` passes WCAG AA (5.62:1 contrast ratio) for normal
> text. For large text or low-emphasis labels, use `#6e7681`. Do not use secondary colors
> for critical data, active state indicators, or error conditions.

---

## 2. Bento Box Protocol — 12-Column CSS Grid

All layout regions are defined once in the shell (`src/server/views/layout.tsx`) as a CSS
Grid with named template areas. Components reference the area name, not column numbers.

```css
.grid-shell {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  grid-template-areas:
    "market market market market market market exec exec exec exec exec exec"
    "telemetry telemetry telemetry telemetry telemetry telemetry telemetry telemetry telemetry telemetry telemetry telemetry";
  gap: 16px;
  max-width: 1200px;
}
```

| Zone | CSS Grid Area | Columns | Content |
|------|--------------|---------|---------|
| Market Stream Grid | `market` | 6/12 | Key asset indicators with strict tracking alignment |
| Execution Console | `exec` | 6/12 | Trade activity, bracket orders, manual intervention targets |
| Telemetry Log | `telemetry` | 12/12 | Append-only console for agent processes and system health |

**Responsive breakpoint:** Below 768px, all three zones collapse to full-width stacked layout.

---

## 3. Implementation Constraints

- **Interactivity:** Zero animation fluff. State changes flash text colors momentarily using
  `accent_green` or `accent_red` before stabilizing.
- **Responsive Control:** Containers wrap aggressively on terminal-adjacent windows without
  losing high-precision tabular formatting.
- **Datatype font:** Use `src/server/static/fonts/Datatype.woff2` for sparklines, bars, and
  chart elements. CSS: `font-feature-settings: 'calt' 1, 'liga' 1`. Apply `.signal` class
  on parent div.

---

## 4. Validation Script (CI Gate)

The `just check` command runs `scripts/py/validate_design_tokens.py` as part of the pre-commit
gate. This script parses this playbook and asserts:

- Every hex code is valid 6-character CSS hex
- Contrast ratio of text colors on background ≥ 4.5:1 (AA normal) / 3:1 (AA large)
- Font stack entries are non-empty
- No duplicate token keys

Exit code 1 on any failure; exit 0 on clean pass. See `scripts/py/validate_design_tokens.py`.

---

## Related

- Architecture reference: `ARCHITECTURE.md`
- Design brief: `briefs/2026-05-23-brief-google-design-md.md`
- CSS implementation: `src/server/static/style.css`
- Validation script: `scripts/py/validate_design_tokens.py`