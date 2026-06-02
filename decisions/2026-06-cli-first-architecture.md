# DECISION: CLI-First Architecture, MCP Deprecated

**Date:** 2026-06-02  
**Status:** `adopted`  
**Impact:** Low — architectural preference, no current MCP usage in this silo

---

## Context

Post-bumblebee MCP audit revealed 32 configured MCP servers across the machine, most inactive or scaffolded. After cleanup (removed 15+ empty plugins), remaining active servers are minimal and mostly notification-related (discord, telegram, imessage).

Simultaneously, RTK (Rust Token Killer) has been evaluated and adopted as the preferred mechanism for output management — providing 60-90% token reduction without MCP protocol overhead.

## Decision

**CLI tools preferred over MCP servers** for this silo.

### Rationale

| Factor | MCP | CLI + RTK |
|--------|-----|-----------|
| Integration complexity | High — protocol, auth, lifecycle | Low — direct command, pipe |
| Output management | Requires protocol-level filtering | RTK handles transparently |
| Debugging | JSON-RPC tracing, serialization issues | Direct stdout/stderr |
| Composition | Awkward cross-server calls | Unix pipes work naturally |
| Trust | "Trust this running server" | "Audit this binary" |
| Token efficiency | Protocol overhead adds tokens | RTK compresses output 60-90% |

### Exception Cases

- **Notification tools** (discord, telegram, imessage) may use MCP if CLI equivalents don't exist
- **Browser automation** (cua-driver skill) requires platform-specific integration
- **External APIs without CLI** (cloudflare MCP) remain in use until CLI alternatives exist

### Migration Path

1. New integrations → CLI first, RTK for output
2. Existing MCP configs → Review and remove if unused
3. Amalfa MCP server → CLI mode is primary, MCP wrapper optional

## Related Decisions

- `008-defuddle-web-content.md` — Defuddle adopted for web content
- `013-decommission-bifrost.md` — External service dependencies minimized
- RTK usage playbook — `~/.pi/agent/playbooks/rtk-usage-playbook.md`

## Implementation

No immediate code changes. This decision informs:
- New feature integration choices
- Cleanup of any MCP-related scaffolding
- Documentation of CLI-first workflow

---

*Edinburgh Protocol alignment: prefer empirical, composable tools over high-context protocol layers.*