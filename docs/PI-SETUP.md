# Pi Coding Agent Setup

**Scope:** Custom extensions, playbooks, and toolchain configuration for this machine  
**Last updated:** 2026-06-02

---

## Core Identity

| Component | Location | Purpose |
|-----------|----------|---------|
| **AGENTS.md** | `~/.pi/agent/AGENTS.md` | Edinburgh Protocol — Scottish Enlightenment identity, task management |
| **Settings** | `~/.pi/agent/settings.json` | Default provider (openrouter), model (deepseek-v4-pro), thinking level |

**Edinburgh Protocol principles:**
- Mentational Humility (acknowledge limitations)
- Stuff → Things (transform chaos to structure)
- Anti-Dogma (empirical over theoretical)
- The Impartial Spectator (self-bias checking)

---

## Extensions

### Custom Tools

| Extension | Location | Purpose | Status |
|-----------|----------|---------|--------|
| **defuddle** | `~/.pi/agent/extensions/defuddle.ts` | Web content fetching with cleaning (strips ads, nav, sidebar) | Active |
| **herdr-agent-state** | `~/.pi/agent/extensions/herdr-agent-state.ts` | Herdr terminal integration — reports agent state (working/blocked/idle) | Active |
| **silo-sandbox** | `~/.pi/agent/extensions/silo-sandbox/` | TradingAgents silo integration | **Disabled** |

### Extension Configuration

```
~/.pi/agent/extensions/
├── defuddle.ts              # Web fetch with content cleaning
├── herdr-agent-state.ts     # Herdr terminal state reporting
└── silo-sandbox/            # (disabled) TradingAgents integration
    ├── config.json          # { "siloRoot": "...", "enabled": false }
    ├── index.ts
    └── package.json
```

---

## Packages (npm)

| Package | Purpose | Status |
|---------|---------|--------|
| `@ollama/pi-web-search` | Web search via Ollama | Active |
| `pi-intercom` | Session-to-session coordination | Active |
| `pi-doom` | Doom game extension | Installed (hobby) |

---

## Agent Types (Role Templates)

Located in `~/.pi/agent/agents/`:

| Agent | Purpose |
|-------|---------|
| **planner** | Task planning and decomposition |
| **reviewer** | Quality gate and review |
| **scout** | Discovery and exploration |
| **spec** | Specification writing |
| **visual-tester** | UI testing coordination |
| **worker** | Standard execution |

---

## External Tools

### RTK (Rust Token Killer)

**Purpose:** CLI output filtering — reduces token consumption 60-90% on common dev commands  
**Install:** `brew install rtk` or `curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh`  
**Version:** 0.28.2+  
**Config:** `~/.config/rtk/config.toml`

**Governance:** See `~/.pi/agent/playbooks/rtk-usage-playbook.md`

Key principle: **RTK is a precision instrument, not a cost-cutting bludgeon.** Use targeted, not always-on.

### Bumblebee

**Purpose:** Package inventory scanner (npm, Go, Ruby, Python, MCP, browser extensions)  
**Install:** `go install` from `github.com/perplexityai/bumblebee`  
**Usage:** `bumblebee scan > inventory.ndjson`

### Defuddle (standalone)

**Purpose:** Standalone web fetching tool  
**Location:** `/opt/homebrew/bin/defuddle`  
**Note:** Also available as pi extension, but standalone binary exists

---

## Scripts

| Script | Purpose |
|--------|---------|
| `refresh-bifrost-models.py` | Refresh model definitions for Bifrost |

Location: `~/.pi/agent/scripts/`

---

## Playbooks

| Playbook | Purpose |
|----------|---------|
| `rtk-usage-playbook.md` | RTK governance — when to use, when to avoid, risk classification |

---

## Skills

| Skill | Location | Purpose |
|-------|----------|---------|
| **cua-driver** | `~/.agents/skills/cua-driver/` | Native macOS app automation via CUA protocol |
| **pi-intercom** | `~/.pi/agent/npm/node_modules/pi-intercom/skills/` | Session coordination |

---

## Configuration Files

```
~/.pi/agent/
├── AGENTS.md                    # System prompt (Edinburgh Protocol)
├── settings.json                # Provider, model, thinking level config
├── models.json                  # Available models
├── extensions/                  # Custom tool extensions
├── agents/                      # Agent role templates
├── playbooks/                   # Tool governance playbooks
├── scripts/                     # Utility scripts
└── npm/node_modules/            # NPM packages
```

---

## Decisions

Relevant architectural decisions:

- `decisions/2026-06-cli-first-architecture.md` — CLI preferred over MCP
- `decisions/008-defuddle-web-content.md` — Defuddle adopted
- `docs/MCP-AUDIT-2026-05-29.md` — MCP server audit results

---

## Onboarding Checklist

For new pi sessions on this machine:

1. [ ] Edinburgh Protocol identity loaded from `AGENTS.md`
2. [ ] RTK available (`rtk --help`)
3. [ ] Defuddle available (`defuddle --help`)
4. [ ] Bumblebee available (`bumblebee scan`)
5. [ ] herdr-agent-state extension active (if in Herdr terminal)
6. [ ] pi-intercom available for multi-session coordination

---

*This document serves as the system inventory for pi setup. Update when extensions, packages, or tools change.*