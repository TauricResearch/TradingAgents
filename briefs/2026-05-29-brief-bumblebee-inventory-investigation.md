---
date: 2026-05-29
updated_by: pi
tags: [brief, security, inventory, supply-chain]
---

# Brief: Bumblebee Package Inventory Integration

## Objective

Investigate integrating bumblebee (endpoint package inventory scanner) into the TradingAgents silo workflow for supply-chain visibility, vulnerability tracking, and MCP server inventory.

## Operational Heuristic

**Inventory precedes governance.** You cannot secure, audit, or manage what you cannot enumerate. Bumblebee provides the enumeration; our job is to decide what to do with it.

## Context

**What is bumblebee?**
- Go binary at `~/go/bin/bumblebee`
- Scans ecosystems: npm, Go, Ruby, Python, MCP, browser extensions
- Outputs NDJSON with package name, version, source path, ecosystem, confidence
- 1.4s scan time, 480K files, ~22K packages on this machine

**Existing inventory:**
- `SILO_MANIFEST.md` — asset map for human-discoverable resources
- `briefs/INDEX.jsonl`, `playbooks/REGISTRY.jsonl` — registry of process artifacts
- `uv.lock`, `pnpm-lock.yaml`, `bun.lock` — language-specific lock files
- **No unified package inventory view**

**The gap:**
We have lockfiles for our direct dependencies, but no systematic view of:
1. Transitive dependencies (what do our deps depend on?)
2. MCP server configs across our AI tools
3. Tooling packages (linters, test runners, build tools)
4. Vulnerable package detection surface

## Functional Requirements

1. **Inventory capture:** Run `bumblebee scan` in CI/post-checkout, emit NDJSON artifact
2. **Ecosystem filter:** Focus on `npm`, `python`, `mcp` ecosystems relevant to TradingAgents
3. **Delta tracking:** Compare inventory snapshots between runs to detect new packages
4. **MCP server audit:** Enumerate MCP server configs across `.claude`, `.gemini`, `.codex`, `.cursor`
5. **Brief generation:** Auto-generate a brief when new high-confidence packages appear in unexpected locations

## Execution Workflow

### Phase 1: Discovery (this brief)
- [ ] Examine `bumblebee.ndjson` structure in detail
- [ ] Identify which packages are "ours" (in `tradingagents/` tree) vs "tooling" (CLI, test deps)
- [ ] Map MCP servers to their capabilities (what can they access?)
- [ ] Assess vulnerability scanning potential (Integration with OSV, GHSA?)

### Phase 2: Integration Options

**Option A: Passive inventory (read-only)**
```
just inventory  # runs bumblebee, shows summary
just inventory --delta  # shows changes since last run
```
Pros: No CI changes, useful for manual review
Cons: No automated alerting

**Option B: CI gate (lightweight)**
```
# .github/workflows/inventory.yml
- run: bumblebee scan > inventory-${{ hash(format('{0}', github.run_id)) }}.ndjson
- uses: actions/upload-artifact@v4
```
Pros: Historical tracking, delta detection
Cons: Adds ~2s to CI

**Option C: First-class registry entry**
Add `package_index.jsonl` to the asset map:
```json
{"package": "pino", "ecosystem": "npm", "version": "9.x", "purpose": "logging", "owner": "src/server/*"}
```

### Phase 3: MCP Server Focus

Current MCP servers across AI tools:
- `hashicorp/terraform-mcp-server` (Claude plugins)
- `@upstash/context7-mcp` (context7)
- `amalfa` (Gemini/CodeX)
- `xcodebuildmcp`, `cloudflare-api` (CodeX)
- 30+ total

**Questions to answer:**
1. Which have network access?
2. Which can read/write files?
3. Which store credentials or tokens?
4. Are any self-hosted vs third-party?

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Inventory capture time | <5s | `time bumblebee scan` |
| Package categorization accuracy | >90% | Manual review of sample |
| MCP server list completeness | 100% | Cross-reference all `.{tool}/mcp*` dirs |
| Integration complexity | <20 LoC | Lines in CI gate or just recipe |
| False positive rate | <5% | Packages flagged as "unknown" that aren't |

## Constraints

**Hard:**
- Must not slow down developer workflow (scan <5s, optional)
- NDJSON output must be parseable by standard jq
- MCP server enumeration must not require authentication

**Soft:**
- Should integrate with existing `just` recipe pattern
- Should emit briefs for anomalous packages (new ecosystems, high-risk lifecycle scripts)
- Should align with SILO_MANIFEST.md format

## Related

- `SILO_MANIFEST.md` — existing asset map
- `briefs/2026-05-09-brief-canonical-registry.md` — registry methodology
- `decisions/NNN-bumblebee-*.md` — decision records (to be created)
- `playbooks/security-*.md` — if security playbooks exist