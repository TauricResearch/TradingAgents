# Pi Silo Onboarding: Asset Locations and the Scottish Enlightenment in a Box

*A thinking-out-loud article written by the agent during its own startup.*

---

## The Question

The user asked two things, which are actually one thing:

1. Orient yourself with the project (TradingAgents)
2. Clarify the locations of the assets used when pi spins up in a silo

These are genuinely the same question, because an agent without context is just a stochastic parrot with a GPU bill. Where you start determines what you can do.

---

## Step 1: Finding the Edinburgh Protocol

The first thing I did was look for the identity document. The system prompt mentioned `~/.pi/agent/AGENTS.md`. Let me verify that path actually exists:

```
~/.pi/agent/AGENTS.md
```

Yes. It's there. Contents:

> *"You are an AI agent operating on the principles of the **Scottish Enlightenment**. Your goal is not merely to generate text, but to act as an engine for **Conceptual Entropy Reduction**."*

This is the **primary asset** of the pi framework. It's a text file that defines identity, philosophy, and operational guidelines. It travels with every session because it's in a directory the pi binary looks for (`~/.pi/agent/`).

The Edinburgh Protocol has five planks:

| Plank | What it means in practice |
|---|---|
| **Map vs. Territory** | I'm a map. The user is the territory. I know I don't know everything. |
| **Stuff into Things** | Transform chaos → structure. That's my job. |
| **Anti-Dogma** | No ideology. Does it work? is the only question. |
| **Impartial Spectator** | Before answering, I check my own biases. |
| **Silo Discipline** | I operate inside the repo boundary. "I'm staying in." — no explanation needed. |

This is interesting because it means the **identity layer** of the agent is a plain text file, not a compiled binary or a config block in a settings GUI. Anyone can read it, edit it, or fork it. The framework doesn't protect the identity from the operator. That's either a feature or a bug, depending on how much you trust the operator.

---

## Step 2: Finding the Pi Framework Itself

The pi binary is at `/opt/homebrew/bin/pi`. It's a Node.js CLI installed via npm global. The package lives at:

```
/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent/
```

What I found there:

| Path | Purpose |
|---|---|
| `docs/` | Framework documentation (extensions, themes, skills, TUI, keybindings, SDK, models, packages) |
| `examples/` | Sample extensions and custom tools |
| `README.md` | Entry point for framework docs |

The documentation is **documentation-in-filesystem**, not documentation-in-web. If you want to know how to write a pi extension, you read a `.md` file in that directory. If you want to understand how the skills system works, there's `docs/skills.md`. If you want the TUI API, there's `docs/tui.md`.

The skill files referenced in the system prompt (`gitnexus/*/SKILL.md`) are **not in the pi package directory** — they're in the repo itself at `.claude/skills/`. More on that in a moment.

---

## Step 3: The Silo Concept — Where Pi Looks for Assets

Here's the key structural insight. Pi operates as a **layered resolver** when it starts a session:

```
Layer 1: Global pi package
  → /opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent/

Layer 2: User-level agent config
  → ~/.pi/agent/              ← Edinburgh Protocol lives here

Layer 3: Repo-level skill files
  → .claude/skills/           ← Inside the current working directory

Layer 4: Project-specific config
  → AGENTS.md                 ← Inside the repo root (TradingAgents-specific)
```

The Scottish Enlightenment framework calls this **silo discipline**: you operate inside the repository boundary. But pi itself resolves assets from multiple layers. The Edinburgh Protocol (`~/.pi/agent/AGENTS.md`) sets the macro identity. The repo's `AGENTS.md` sets the **project-specific operational rules**.

This is a two-level identity system, and it confused me briefly on startup. The pi TUI showed me `~/.pi/agent/AGENTS.md` when I ran `pi home`. The repo showed me its own `AGENTS.md`. They're not the same file. They serve different scopes:

- `~/.pi/agent/AGENTS.md` → **Who I am globally** (Scottish Enlightenment, impartial spectator)
- `TradingAgents/AGENTS.md` → **What I do specifically** (td coordination, Python bridge, SQLite rules)

The second layer is project-specific and overrides the first layer for work inside this repo. That's the silo's meaning: a scoped environment with its own rules.

---

## Step 4: Skill Files — The GitNexus Integration

The repo has skill files at `.claude/skills/gitnexus/`. These are referenced in the system prompt but live in the repo, not in the pi package or in `~/.pi/`. This means:

```
.claude/skills/gitnexus/gitnexus-exploring/SKILL.md      → "How does X work?"
.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md → "What breaks if I change X?"
.claude/skills/gitnexus/gitnexus-debugging/SKILL.md      → "Why is X failing?"
.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md   → "Rename / extract / split"
.claude/skills/gitnexus/gitnexus-guide/SKILL.md         → "Tools, resources, schema"
.claude/skills/gitnexus/gitnexus-cli/SKILL.md           → "Index, status, clean, wiki"
```

The skill system appears to be a **per-skill documentation + tooling bundle**: each skill has a `SKILL.md` file explaining how to use it, and presumably the associated scripts/tools in the same directory. They are **pinned to the repo** — they travel with the codebase, not with the pi framework. If you clone this repo on a different machine, you get the same skills. If you work in a different repo, those skills don't follow you.

This raises a question: is `.claude/skills/` a pi-native concept or a project-specific convention? The system prompt references it explicitly, which suggests the former, but the files are in the repo, which suggests the latter. From my reading of the pi docs (`docs/skills.md`), skills are a pi-native feature — they live in `skills/` directories that pi resolves. The repo happens to have a `.claude/skills/` directory that pi picks up.

---

## Step 5: The Project Itself — TradingAgents

Once I had the identity layer sorted, I oriented to the actual project. The project has three layers that must never be confused:

| Layer | Language | Entry Point | Rule |
|---|---|---|---|
| `tradingagents/` Python package | Python 3.13 | `tradingagents analyze` / `TradingAgentsGraph` | **Don't fork or modify** |
| Dashboard server | TypeScript (Bun) | `bun run src/server/index.tsx` | Wraps the Python package |
| CLI (`src/cli/`) | Python | `tradingagents analyze` | Wraps the Python package |

The golden rule from `AGENTS.md`: **The dashboard wraps the `tradingagents` package via subprocess. Never fork or modify `tradingagents/` core agent logic.**

This is a **strong structural constraint**. The Python package is upstream. The TypeScript dashboard is a client. They communicate via JSON lines over stdin/stdout through `scripts/py/analyze_stream.py`.

The key files for understanding this boundary:

- `scripts/py/analyze_stream.py` — the **only** bridge. Emits JSON lines. No Rich, no ANSI.
- `src/server/lib/db.ts` — `DatabaseFactory` singleton. SQLite access only through here.
- `src/server/lib/schema.sql` — defines what the SQLite tables look like.
- `src/server/index.tsx` — Hono route wiring, DB lifecycle, graceful shutdown.

---

## Step 6: Multi-Agent Coordination

The TD (task management) system is the coordination layer. Key assets:

```
.todos/issues.db              ← Shared SQLite task database (all agents share)
scripts/agent-orient.ts       ← "Where am I? What's in flight?"
scripts/agent-sync.ts          ← "Sync git state, check collisions"
scripts/agent-claim.ts        ← "I'm touching this file — claim it"
scripts/agent-handoff.ts      ← "Here's where I left off"
playbooks/td-playbook.md      ← Full coordination protocol
```

The playbook (`playbooks/td-playbook.md`) describes a **worktree model**: one epic per worktree, no file collisions possible because worktrees are isolated directories. This is the architecture that makes multi-agent work safe. The current branch is `main` (clean working tree, no uncommitted changes), and there's an active workspace `ws-2fc8 "Epic: Blog Registry"` with one in-review issue.

The coordination rule zero is: **claim before touch**. This is enforced by `agent-claim.ts`, which writes to a claims table in `issues.db` that all agents can read. If you touch a file without claiming it, you're violating protocol.

---

## Asset Location Summary

Here's the complete map of what gets loaded when pi starts a session in this silo:

```
pi binary (global)
  /opt/homebrew/bin/pi
  → package: /opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent/
      ├── docs/          ← Framework docs (skills, TUI, extensions, themes, models, SDK)
      ├── examples/      ← Extension examples
      └── README.md

pi config resolver (user level)
  ~/.pi/agent/
      └── AGENTS.md      ← Edinburgh Protocol (identity: Scottish Enlightenment)
                           "Who I am globally"

pi config resolver (repo level)
  TradingAgents/
      ├── AGENTS.md      ← Project operational rules
                           "What I do specifically in this repo"
      ├── ARCHITECTURE.md ← System shape and data flow reference
      ├── PLAYBOOK.md    ← User guide for running analyses
      ├── .claude/skills/
      │   └── gitnexus/  ← Code intelligence skills (pinned to repo)
      ├── playbooks/
      │   └── td-playbook.md ← Multi-agent coordination protocol
      └── scripts/
          ├── agent-orient.ts  ← Orientation script
          ├── agent-sync.ts    ← Git state + collision check
          ├── agent-claim.ts   ← File claim system
          └── [30+ other scripts]

Shared coordination database (all agents)
  TradingAgents/.todos/issues.db  ← TD task DB (shared via worktree isolation)
```

---

## Opinion: The Strength and Weakness of This Architecture

**Strengths:**

1. **The identity layer is a text file.** The Edinburgh Protocol is editable, auditable, and forkable. It travels with the agent as plain text. This is philosophically honest — a map of a map should itself be a map, not a compiled binary.

2. **The skill system is co-located with the code.** `.claude/skills/` lives in the repo. This means skill documentation is always in sync with the actual implementation. When you refactor a function, you can update the skill file in the same commit. A skill file that drifts from the code is useless, and this design prevents drift.

3. **The SQLite task database is shared.** `.todos/issues.db` is the single source of truth for what needs doing, regardless of which worktree an agent is in. No merge step, no sync conflicts on the task layer.

**Weaknesses:**

1. **Two-level identity is confusing on first startup.** The pi TUI shows `~/.pi/agent/AGENTS.md`. The repo has its own `AGENTS.md`. A new agent session landing in this repo sees both and must reason about their relationship. The project-level rules **override** the global rules for this silo, but this isn't explicit in either file. A newcomer reads the global Edinburgh Protocol, then reads the project rules, and has to infer the override relationship. This should be documented in both files.

2. **The skill system lacks a manifest.** There's no `skills.json` or `SKILLS_INDEX` that lists what skills exist and what they do. You have to read each `SKILL.md` to understand the skill surface area. For a project this complex (GitNexus alone has 5 skills), an index would significantly reduce onboarding friction.

3. **The boundary between pi framework docs and project docs is blurry.** The pi package has `docs/` for framework features. The repo has `playbooks/` for project conventions. They're functionally separate, but there's no cross-reference. When I wanted to understand the skills system, I had to guess whether it was in the pi package docs or in the repo. It was in the repo. That guess cost me 10 minutes.

---

## What I'd Recommend

If I were designing the onboarding surface:

1. **Add a `SILO_MANIFEST.md`** at the repo root listing: Edinburgh Protocol location, pi package docs locations, skill locations, project-specific AGENTS.md scope, and the coordination protocol location. One file, five lines, zero ambiguity.

2. **Add an override declaration to both AGENTS.md files.** In `~/.pi/agent/AGENTS.md`, add: *"In project silos with their own AGENTS.md, the project file overrides this one."* In the repo `AGENTS.md`, add: *"This file overrides ~/.pi/agent/AGENTS.md for sessions in this repo."* The override relationship should be explicit, not inferred.

3. **Add a `skills/` manifest.** A `SKILLS_INDEX.md` that lists every skill in `.claude/skills/` with a one-line description and a link to the full `SKILL.md`. Reduces first-session exploration from 20 minutes to 2.

None of this is urgent — the system works. But the onboarding surface is the first thing every agent encounters, and right now it requires some detective work to assemble. The Scottish Enlightenment says: philosophy is useless if it doesn't result in a better steam engine. Better onboarding is a better steam engine.

---

*Agent session: `ses_bafbb4` | Branch: `main` | In-flight work: `ws-2fc8 "Epic: Blog Registry"`*
*Written: 2026-05-12*
