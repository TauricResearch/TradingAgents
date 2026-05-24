```
[LOCUS: DESIGN-MD-SPEC]
[STRATEGY: DEDUCTIVE MINIMALISM (COG-12)]
[MODE: TACTICAL ACTION MODE (TAM)]

```

### 1. Conceptual Mapping (`PHI-1`, `PHI-14`)

We are embedding a design token specification as a formal playbook within `playbooks/`,
adjacent to `conventions-playbook.md`. This establishes an explicit, low-entropy contract
for the minimalist user interface, preventing visual presentation drift during automated
iterations.

> **Deliverable change:** Originally proposed `tradingagents/DESIGN.md`. ARCHITECTURE.md
> is the canonical architecture reference — it would be redundant to have a second top-level
> design doc. This spec lives in `playbooks/ui-design-playbook.md` and is referenced by a
> one-liner in ARCHITECTURE.md.

---

### 2. Deliverable: `playbooks/ui-design-playbook.md`

```markdown
# UI Design Playbook — TradingAgents Minimalist CLI-Adjacent UI

> **Source of truth** for all visual design tokens. ARCHITECTURE.md references this file.
> **CI gate:** `scripts/py/validate_design_tokens.py` must pass before any CSS commit.

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
  text_low_emphasis: "#6e7681"# Extended secondary (larger text, metadata only)
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

## 2. Structural Architecture (Bento Box Protocol)

**Grid system:** 12-column CSS Grid with named template areas. All layout regions are
defined once in the shell (layout.tsx) and referenced by name throughout the codebase.

```
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

**Responsive:** Below 768px, all three zones collapse to full-width stacked layout.

---

## 3. Implementation Constraints

* **Interactivity:** Zero animation fluff. State changes flash text colors momentarily using
  `accent_green` or `accent_red` before stabilizing.
* **Responsive Control:** Containers wrap aggressively on terminal-adjacent windows without
  losing high-precision tabular formatting.
* **Verification Gates:** All design tokens are validated via
  `scripts/py/validate_design_tokens.py` in the pre-commit hook (`just check`).
  This script asserts each hex value is valid CSS, fonts are declared correctly,
  and color pairs meet WCAG AA thresholds.

---

## 4. Validation Script (CI Gate)

`scripts/py/validate_design_tokens.py` — parses `playbooks/ui-design-playbook.md`
and asserts:
- Every hex code is valid 6-character CSS hex
- Contrast ratio of text colors on background ≥ 4.5:1 (AA normal) / 3:1 (AA large)
- Font stack entries are non-empty
- No duplicate token keys

Exit code 1 on any failure; exit 0 on clean pass.

---

```

### 3. State Update (`PHI-13`)

```jsonL
{"timestamp": "2026-05-24T00:00:00Z", "action": "update_file", "path": "briefs/2026-05-23-brief-google-design-md.md", "status": "revision_complete"}
{"timestamp": "2026-05-24T00:00:00Z", "action": "create_file", "path": "playbooks/ui-design-playbook.md", "status": "pending_persistence"}
{"timestamp": "2026-05-24T00:00:00Z", "action": "create_file", "path": "scripts/py/validate_design_tokens.py", "status": "pending_persistence"}
{"timestamp": "2026-05-24T00:00:00Z", "action": "update_index", "path": "decisions/INDEX.jsonl", "status": "synchronized"}

```

```
[SYSTEM STATUS: SPEC REVISED]
[EXECUTION: IN_PROGRESS]

```

What is our next objective?