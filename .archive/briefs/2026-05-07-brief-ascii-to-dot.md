# Brief: Replace ASCII Diagrams with DOT + SVG/PNG

## Context

Our markdown files (playbooks, docs) contain ASCII box-drawing diagrams
(`┌─┐`, `│`, `└─┘`). These are fragile — they break on narrow terminals, mobile
views, and any font that is not perfectly monospace.

We now have a working pipeline:
- `.dot` files → `graphviz` → `.svg` (clean, scalable)
- `.dot` files → `graphviz` → `.png` (raster fallback)
- `docs/diagrams/` holds all generated assets

## Objective

Audit all markdown files in `playbooks/` and `docs/`. Replace every ASCII
diagram with:
1. A `.dot` source file in `docs/diagrams/`
2. An `.svg` rendered file (auto-generated)
3. An `.png` rendered file (auto-generated)
4. A markdown `![alt](path.svg)` reference

## Scope

**Found:** 41 lines of ASCII diagram markup across `playbooks/` and `docs/`.

**Priority order:**
1. `playbooks/ci-cd-playbook.md` — has a flowchart (pre-push pipeline)
2. `playbooks/architecture.md` — likely has system diagrams
3. Other playbooks — check each for diagrams

## Acceptance Criteria

- [ ] No ASCII box-drawing characters remain in any `.md` file
- [ ] Each diagram has a `.dot` source in `docs/diagrams/`
- [ ] Each `.dot` is rendered to `.svg` and `.png`
- [ ] Markdown references the `.svg` with `![alt](path)`
- [ ] `just regen-diagrams` reproduces all SVGs/PNGs

## Approach

1. Use `grep` to find all ASCII diagrams (already done — 41 lines)
2. For each diagram:
   a. Hand-craft a `.dot` file (or use `gitnexus` if it is a code graph)
   b. Add to `docs/diagrams/`
   c. Run `just regen-diagrams`
   d. Replace ASCII block with `![alt](docs/diagrams/name.svg)`
3. Verify: `grep` returns zero results

## Not in Scope

- ASCII tables (data tables with `│` separators) — these are fine
- Inline code blocks showing terminal output
- Emoji or unicode symbols used for bullets (✓, →, etc.)

## Estimated Effort

1–2 hours for 3–5 diagrams. Most are simple flowcharts (rectangles + arrows).
