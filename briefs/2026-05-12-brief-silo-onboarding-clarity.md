---
date: 2026-05-12
updated_by: ses_bafbb4
tags: [brief, silo-hygiene, onboarding]
---

# Brief: Silo Onboarding Clarity — Three Manifest Fixes

## Objective

Reduce agent onboarding friction from ~20 minutes of exploration to ~2 minutes by making asset locations, identity override relationships, and skill surface area **explicit rather than inferred**. Three targeted deliverables: a silo manifest, identity override declarations, and a skills index.

## Operational Heuristic

**The first session should not require detective work.** When an agent spins up in this silo, every asset it needs should be findable via a manifest, not by searching the filesystem. The silo's identity layer should declare its own scope. Skills should advertise themselves.

## Functional Requirements

1. **`SILO_MANIFEST.md` at repo root:** Single file enumerating every asset layer with one-line descriptions and relative paths. Must include: Edinburgh Protocol location, pi package docs, skill locations, project AGENTS.md, coordination protocol, shared task DB.

2. **Override declaration in `~/.pi/agent/AGENTS.md`:** Add a trailing section (or inline note) explicitly stating that project-level `AGENTS.md` files override this one for sessions inside a project silo. Even though the file lives at the user level and pi owns it, the declaration makes the override relationship explicit to any agent reading it.

3. **Override declaration in `TradingAgents/AGENTS.md`:** Add a trailing section explicitly stating this file overrides `~/.pi/agent/AGENTS.md` for sessions in this repo. Same reasoning — make the override relationship declarative, not inferred.

4. **`SKILLS_INDEX.md` at `.claude/skills/SKILLS_INDEX.md`:** One-line entries for every skill in `.claude/skills/` and subdirectories, with: skill name, path to `SKILL.md`, and a one-sentence description. Ordered by directory.

## Execution Workflow

1. **Write `SILO_MANIFEST.md`**
   - Create at repo root
   - Enumerate all asset layers in a table: Asset | Location | Description | Owner
   - Include a "Getting Started" section at top: "Run `bun scripts/agent-orient.ts` first."
   - Do NOT duplicate content — just point to canonical locations

2. **Draft override text for `~/.pi/agent/AGENTS.md`**
   - Propose the text for the user to approve/copy into their global file
   - Text: *"When operating inside a project silo with its own AGENTS.md, the project file takes precedence and overrides the rules in this file for the duration of that session."*
   - Note: this file lives at `~/.pi/agent/` — the user must copy this change manually, or we provide a script to patch it

3. **Add override section to `TradingAgents/AGENTS.md`**
   - Append a "Scope" section with: *"This file overrides ~/.pi/agent/AGENTS.md for all agent sessions inside this repository. See SILO_MANIFEST.md for the complete asset map."*

4. **Write `.claude/skills/SKILLS_INDEX.md`**
   - Scan `.claude/skills/` recursively for all `SKILL.md` files
   - Generate the index with skill name (from directory), path, one-line description
   - If a skill has no `SKILL.md`, note it as " undocumented — see owner"

5. **Update `briefs/INDEX.jsonl`**
   - Add this brief with status `done` after implementation

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Onboarding friction | Agent can orient in ≤2 min from manifest alone | Manual test: new session, read manifest, run orient script |
| Asset discoverability | Zero "where does X live?" ambiguity | Checklist: Edinburgh Protocol, skills, project AGENTS.md, coordination protocol — all listed in manifest |
| Override clarity | Neither AGENTS.md file requires inference | Both files contain explicit override language |
| Skill surface area | All skills advertise themselves | SKILLS_INDEX.md lists every skill with ≥1 sentence description |

## Constraints

- **Hard:** No files may be moved — only pointed to. Disrupting existing paths breaks working scripts.
- **Hard:** `~/.pi/agent/AGENTS.md` patch requires user action — we draft, user applies. No automated overwrite.
- **Soft:** `SKILLS_INDEX.md` should auto-update if possible — but a manual update in the same commit as a new skill is acceptable.
- **Soft:** `SILO_MANIFEST.md` should be readable by non-technical users (i.e., a human reviewing the repo) — avoid jargon.

## Related

- Brief: `briefs/brief-static-assets-2026-05-05.md`
- Playbook: `playbooks/td-playbook.md`
- Blog post: `docs/blog/2026-05-12-pi-silo-onboarding-assets.md`
- System prompt: `~/.pi/agent/AGENTS.md` (Edinburgh Protocol)
- Project identity: `TradingAgents/AGENTS.md` (project rules)
