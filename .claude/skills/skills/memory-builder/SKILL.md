---
name: Memory Builder
description: >
  Extracts structured repository knowledge from source code, git history, ADRs, and
  conversations, then writes it into the layered memory system under docs/agent/.
  Use this skill when asked to "build memory", "update memory", "extract knowledge",
  "refresh context files", "rebuild repository docs", "generate memory", "update context",
  or any variation of rebuilding or refreshing the project's documentation context.
  Also use when a significant code change has landed and the docs/agent/ files may be stale.
version: 1.0.0
---

# Memory Builder

Build, update, and audit the project's structured memory system. The output files
are the primary context for all future agent sessions — they must be accurate enough
that an agent with zero prior context can understand the project and make correct decisions.

## Memory Layout

```
docs/agent/
├── CURRENT_STATE.md              # Layer 1: Live State (changes every session)
├── context/                      # Layer 2: Structured Knowledge (per milestone)
│   ├── ARCHITECTURE.md           #   System design, workflows, data flow, pipeline
│   ├── CONVENTIONS.md            #   Coding patterns, rules, gotchas
│   ├── COMPONENTS.md             #   File map, extension points, test organization
│   ├── TECH_STACK.md             #   Dependencies, APIs, providers, versions
│   └── GLOSSARY.md               #   Term definitions, acronyms, data classes
├── decisions/                    # Layer 3: Decisions (append-only ADRs)
│   └── NNN-short-name.md
└── plans/                        # Layer 4: Plans (implementation checklists)
    └── NNN-plan-name.md
```

Layers 1-2 are what this skill builds and maintains. Layers 3-4 are written by
other workflows (architecture-coordinator, planning sessions) and are read-only
inputs for this skill.

## Operational Modes

Pick the mode that fits the request:

### Mode 1: Full Build

Use when: no context files exist, or the user says "rebuild" / "build memory from scratch".

1. **Audit existing** — read any current `docs/agent/context/*.md` files. Note what exists.
2. **Discover sources** — dynamically scan the codebase (see Discovery below).
3. **Extract** — populate each context file (see Extraction Rules below).
4. **Cross-reference** — verify no contradictions between files.
5. **Quality gate** — run every check (see Quality Gate below).
6. **Report** — output the build report.

### Mode 2: Targeted Update

Use when: specific code changed and the user says "update memory" or similar.

1. Identify which source files changed (check `git diff`, user description, or recent commits).
2. Map changed files to affected context files using the extraction table below.
3. Read only the affected sections, update them, leave the rest untouched.
4. Update the freshness marker on modified files only.

### Mode 3: Audit

Use when: the user says "audit memory" or "verify context files".

1. For each of the 5 context files, pick 5 factual claims at random.
2. Verify each claim against the actual source code.
3. Report: claim, source file checked, pass/fail, correction if needed.
4. Fix any failures found.

---

## Discovery (Step 1)

Never hardcode file lists. Discover the codebase dynamically:

```
# Find all Python source files
find tradingagents/ cli/ -name "*.py" -type f

# Find config and metadata
ls pyproject.toml .env.example tradingagents/default_config.py

# Find all class definitions
grep -rn "^class " tradingagents/ cli/

# Find all @tool decorated functions
grep -rn "@tool" tradingagents/

# Find state/data classes
grep -rn "@dataclass" tradingagents/ cli/
```

### High-Signal Files (read these first)

| File | Why |
|------|-----|
| `tradingagents/default_config.py` | All config keys, defaults, env var pattern |
| `tradingagents/graph/trading_graph.py` | Trading workflow, agent wiring |
| `tradingagents/graph/scanner_graph.py` | Scanner workflow, parallel execution |
| `tradingagents/graph/setup.py` | Agent factory creation, LLM tiers |
| `tradingagents/agents/utils/tool_runner.py` | Inline tool execution loop |
| `cli/main.py` | CLI commands, entry points |
| `pyproject.toml` | Dependencies, versions, Python constraint |
| `docs/agent/decisions/*.md` | Architectural constraints (binding rules) |

### Source Priority

When information conflicts, trust in this order:
1. Source code (always wins)
2. ADRs in `docs/agent/decisions/`
3. Test files
4. Git history
5. Config files
6. README / other docs

---

## Extraction Rules (Step 2)

### CURRENT_STATE.md

Three sections only. Max 30 lines total.

```markdown
# Current Milestone
[One paragraph: what's the active focus and next deliverable]

# Recent Progress
[Bullet list: what shipped recently, merged PRs, key fixes]

# Active Blockers
[Bullet list: what's stuck or fragile, with brief context]
```

Source: `git log --oneline -20`, open PRs, known issues.

### ARCHITECTURE.md

System-level design. Someone reading only this file should understand how the
system works end-to-end.

| Section | What to extract | Source |
|---------|----------------|--------|
| System Description | One paragraph: what the project is, agent count, vendor count, provider count | `setup.py`, `default_config.py` |
| 3-Tier LLM System | Table: tier name, config key, default model, purpose | `default_config.py` |
| LLM Provider Factory | Table: provider, config value, client class | `setup.py` or wherever `get_llm_client` lives |
| Data Vendor Routing | Table: vendor, capabilities, role (primary/fallback) | `dataflows/`, vendor modules |
| Trading Pipeline | ASCII diagram: analysts → debate → trader → risk → judge | `trading_graph.py` |
| Scanner Pipeline | ASCII diagram: parallel scanners → deep dive → synthesis | `scanner_graph.py` |
| Pipeline Bridge | How scanner output feeds into per-ticker analysis | `macro_bridge.py` or pipeline module |
| CLI Architecture | Commands, UI components (Rich, MessageBuffer) | `cli/main.py` |
| Key Source Files | Table: file path, purpose (10-15 files max) | Discovery step |

### CONVENTIONS.md

Rules and patterns. Written as imperatives — "Always...", "Never...", "Use...".
Every convention must cite its source file.

| Section | What to extract |
|---------|----------------|
| Configuration | Env var override pattern, per-tier overrides, `.env` loading |
| Agent Creation | Factory closure pattern `create_X(llm)`, tool binding rules |
| Tool Execution | Trading: `ToolNode` in graph. Scanners: `run_tool_loop()`. Constants: `MAX_TOOL_ROUNDS`, `MIN_REPORT_LENGTH` |
| Vendor Routing | Fail-fast default (ADR 011), `FALLBACK_ALLOWED` whitelist (list all methods), exception types to catch |
| yfinance Gotchas | `top_companies` has ticker as INDEX not column, `Sector.overview` has no perf data, ETF proxies |
| LangGraph State | Parallel writes need reducers, `_last_value` reducer, list all state classes |
| Threading | Rate limiter: never hold lock during sleep/IO, rate limits per vendor |
| Ollama | Never hardcode `localhost:11434`, use configured `base_url` |
| CLI Patterns | Typer commands, Rich UI, `MessageBuffer`, `StatsCallbackHandler` |
| Pipeline Patterns | `MacroBridge`, `ConvictionLevel`, `extract_json()` |
| Testing | pytest commands, markers, mocking patterns (`VENDOR_METHODS` dict patching), env isolation |
| Error Handling | Fail-fast by default, exception hierarchies per vendor, `raise from` chaining |

### COMPONENTS.md

Concrete inventory. The reader should be able to find any file or class quickly.

| Section | What to extract |
|---------|----------------|
| Directory Tree | Run `find` and format as tree. Verify against actual filesystem. |
| Class Inventory | Table: class name, file, purpose. Use `grep "^class "` to discover. |
| Extension Guides | Step-by-step: how to add a new analyst, scanner, vendor, config key, LLM provider |
| CLI Commands | Table: command name, description, entry point |
| Test Organization | Table: test file, type (unit/integration), what it covers, markers |

### TECH_STACK.md

Dependencies and external services. All version constraints come from `pyproject.toml`.

| Section | What to extract |
|---------|----------------|
| Core Dependencies | Table: package, version constraint (from pyproject.toml), purpose |
| External APIs | Table: service, auth env var, rate limit, primary use |
| LLM Providers | Table: provider, config value, client class, example models |
| Python Version | From pyproject.toml `requires-python` |
| Dev Tools | pytest version, conda, etc. |

Do NOT include packages that aren't in `pyproject.toml`. Do NOT list aspirational
or unused dependencies.

### GLOSSARY.md

Every project-specific term, organized by domain. Each term cites its source file.

| Domain Section | Terms to include |
|---------------|-----------------|
| Agents & Workflows | Trading Graph, Scanner Graph, Agent Factory, ToolNode, run_tool_loop, Nudge |
| Data Layer | route_to_vendor, VENDOR_METHODS, FALLBACK_ALLOWED, ETF Proxy, etc. |
| Configuration | quick_think, mid_think, deep_think, _env(), _env_int() |
| Vendor-Specific | Exception types (AlphaVantageError, FinnhubError, etc.) |
| State & Data Classes | All @dataclass classes, state types |
| Pipeline | MacroBridge, MacroContext, StockCandidate, TickerResult, ConvictionLevel |
| CLI | MessageBuffer, StatsCallbackHandler, AnalystType, FIXED_AGENTS |
| Constants | All significant constants with actual values and source line |

---

## Quality Gate (Step 3)

Every context file must pass ALL of these before you're done:

1. **Accurate** — Every statement is verifiable in the current source code. If you wrote
   "17 agents", count them. If you wrote ">=3.10", check pyproject.toml.
2. **Current** — Reflects the latest code on the working branch, not an old snapshot.
3. **Complete** — All 8 subsystems covered: agents, dataflows, graphs, pipeline, CLI,
   LLM clients, config, tests. If a subsystem is missing, the gate fails.
4. **Concise** — No information duplicated across context files. Each fact lives in
   exactly one file.
5. **Navigable** — A reader can find any specific fact within 2 scrolls or searches.
6. **Quantified** — Constants use actual values from source code (e.g., `MAX_TOOL_ROUNDS=5`),
   never vague descriptions ("a maximum number of rounds").
7. **Cross-referenced** — Every convention cites a source file. Every glossary term
   links to where it's defined.

### Mandatory Verification Steps

These checks catch the most common errors. Run them before declaring the gate passed.

1. **Dependency verification**: Parse `pyproject.toml` `[project.dependencies]` and
   `[project.optional-dependencies]`. Only list packages that actually appear there.
   If a package exists in source imports but not in pyproject.toml, flag it as
   "undeclared dependency" — do not silently add it to TECH_STACK.

2. **Model name verification**: Read `default_config.py` and extract the actual model
   identifiers (e.g., `"gpt-4o-mini"`, not guessed names). Cross-check any model names
   in ARCHITECTURE.md against what's actually in the config.

3. **Agent count verification**: Run `grep -rn "def create_" tradingagents/agents/` and
   count unique agent factory functions. Use the real count, not an estimate.

4. **ADR cross-reference verification**: Every ADR cited in context files (e.g., "ADR 011")
   must exist in `docs/agent/decisions/`. Run `ls docs/agent/decisions/` and confirm.

5. **Class existence verification**: Every class listed in COMPONENTS.md must exist in
   the codebase. Run `grep -rn "^class ClassName" tradingagents/ cli/` for each one.

### What NOT to do

- Do not copy code blocks into docs — reference the file and line instead
- Do not describe aspirational or planned features as current facts
- Do not use stale information from old branches or outdated READMEs
- Do not round numbers — use the exact values from source
- Do not skip CLI or pipeline subsystems (common oversight)
- Do not list dependencies without version constraints from pyproject.toml
- Do not list model names you haven't verified in default_config.py
- Do not include packages from imports that aren't declared in pyproject.toml
- Do not exceed 200 lines per context file — if you're over, split or trim

## Freshness Markers (Step 4)

Every context file starts with:
```
<!-- Last verified: YYYY-MM-DD -->
```
Set to today's date when creating or updating the file.

## Build Report (Step 5)

After completing any mode, output:

```
## Memory Build Report

**Mode**: Build | Update | Audit
**Date**: YYYY-MM-DD

### Files
| File | Status | Lines |
|------|--------|-------|
| CURRENT_STATE.md | created/updated/unchanged | N |
| context/ARCHITECTURE.md | created/updated/unchanged | N |
| ... | ... | ... |

### Sources Consulted
- [list of key files read]

### Quality Gate
| Criterion | Status |
|-----------|--------|
| Accurate | pass/fail |
| Current | pass/fail |
| Complete | pass/fail |
| Concise | pass/fail |
| Navigable | pass/fail |
| Quantified | pass/fail |
| Cross-referenced | pass/fail |

### Subsystem Coverage
- [x] Agents
- [x] Dataflows
- [x] Graphs
- [x] Pipeline
- [x] CLI
- [x] LLM Clients
- [x] Config
- [x] Tests
```
