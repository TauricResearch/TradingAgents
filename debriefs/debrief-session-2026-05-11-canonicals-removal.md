---
date: 2026-05-11
tags: [debrief, registry, playbook, cleanup]
updated_by: pi
environment: local
---

# Debrief: canonicals/ Removal — 2026-05-11

## Context

Session focused on defuddle vs. Browserbase comparison, template creation for briefs/debriefs/decisions/playbooks, and cleanup of the `canonicals/` directory that was created by a prior agent session (ses_0dd889, 2026-05-09).

## What Was Done

1. **Defuddle review:** Compared Browserbase (headless browser sessions) against defuddle (content extraction API). Concluded defuddle handles 99% of use cases for context-aware research. Created `decisions/008-defuddle-web-content.md`.

2. **Templates created:** Added `TEMPLATE.md` to briefs/, debriefs/, and playbooks/ folders. All registered in their respective `INDEX.jsonl` files with `template: true` flag.

3. **canonicals/ removed:** The `canonicals/` directory (created by ses_0dd889) was deleted. 12 non-colliding playbooks moved back to `playbooks/`. 7 colliders already existed in `playbooks/` — discarded. All registry scripts updated to reference `playbooks/` instead of `canonicals/`. Updated playbooks-playbook.md and unified-registry-playbook.md to reflect new model.

## Problems

- **Self-inflicted complexity:** The `canonicals/` directory created more overhead than value. The distinction between "canonical" (generic) and "project" (specific) playbooks was a fine-grained internal classification that added a second index, second set of scripts, and second directory — for a problem that didn't require it. The external registry (if one exists) should own canonical versions, not this project.
- **Context loss:** The agent that created `canonicals/` (ses_0dd889) focused on the registry classification problem in isolation without step-back to the larger principle: the project should not maintain parallel stores of the same information.
- **Biome formatting drift:** Two registry scripts had multiline ternary operators that biome wanted collapsed. Fixed as part of cleanup.

## Lessons Learned

- **Complexity for theoretical future = smell.** The `canonicals/` directory was built to support "lift-and-shift to just-silo" — a future goal. But introducing a second directory, second index, and second set of scripts creates immediate maintenance cost. The right move was to keep all playbooks in one place and submit proven patterns to an external registry when needed.
- **Registry owns canonical, project doesn't.** The model clarified: the project does not maintain a canonical store. When a playbook proves its worth, submit it to the external registry. That registry owns the canonical version. The project holds its local copy.
- **Template discipline accelerates creation.** Having `briefs/TEMPLATE.md`, `debriefs/TEMPLATE.md`, `playbooks/TEMPLATE.md` available means new documents follow a consistent structure without looking up a playbook to copy from. This was a fast, high-value change.
- **`just check` as commit gate is essential.** The canonicals removal would have been caught earlier if `reg-sync` had been run more frequently — index drift was accumulating silently. The `just check` gate ensures this doesn't happen.

## Decisions Made

1. **Remove `canonicals/`** — all playbooks in `playbooks/`; registry tracks source via `meta.source`
2. **Templates for all document types** — briefs, debriefs, decisions, playbooks all have `TEMPLATE.md`
3. **`agent` field semantics** — renamed to `updated_by` to track who last touched the file (not who created it); git history covers creation

## Related

- Brief: `briefs/2026-05-09-brief-canonical-registry.md` (Superseded)
- Debrief: `debriefs/debrief-session-2026-05-09-s01-canonicals.md` (Superseded)
- Decision: `decisions/008-defuddle-web-content.md` (analogy: lightweight external services over heavy infra)
- Playbook: `playbooks/playbooks-playbook.md` (updated to remove canonicals model)
- Playbook: `playbooks/unified-registry-playbook.md` (updated)