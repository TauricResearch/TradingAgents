---
date: 2026-05-24
updated_by: ses_2696bd
status: Accepted
---

# Decision: Defer BiFrost Local AI Router Integration

**Date:** 2026-05-24
**Updated by:** ses_2696bd
**Status:** Accepted

## Context

On 2026-05-20, `briefs/2026-06-01-brief-bifrost-installation.md` was committed (PR #13)
proposing installation of BiFrost as a local AI router/proxy. No implementation followed.
The brief was subsequently deleted from the current branch without a decision record.

BiFrost is an open-source local AI routing layer. The original proposal aimed to reduce
LLM costs and latency by routing requests through a local proxy with caching and fallback
behaviour. However:

- TradingAgents already supports multi-provider routing via `OPENROUTER_API_KEY` and
  `GOOGLE_API_KEY`/`ANTHROPIC_API_KEY` environment variables.
- The existing `subprocess-bridge` pattern (ADR #005) means the Python core never directly
  manages HTTP — the Bun server side handles env var loading, keeping the interface clean.
- BiFrost introduces an external system dependency that would require a separate daemon,
  config file, and lifecycle management (start/stop/health).
- The proposal had no concrete validation criteria or timeline.

## Decision

**Defer BiFrost integration indefinitely.** Do not add it to the roadmap at this time.

The existing multi-provider key approach (OpenRouter as primary, Google/Anthropic as
fallback via env vars) is sufficient for the current architecture.

If a future need for local model routing emerges (e.g., running local Ollama models,
request coalescing, cost tracking per model), revisit this decision and write a new ADR.

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| Implement BiFrost now | Adds daemon dependency; no immediate cost/latency problem to solve; deferred scope |
| Use OpenRouter only | Already in place — sufficient for current needs |
| Add BiFrost as optional flag | Would require conditional logic in `analyze_stream.py`; adds complexity for uncertain benefit |

## Consequences

**What became easier:**
- No new external system dependency to install, configure, or maintain
- Architecture stays clean — env vars only, no local proxy to manage

**What became harder:**
- Cost optimization via request caching not available (but not currently a problem)
- If multi-model fallback via local proxy is needed later, no groundwork exists

**Constraints this imposes:**
- Multi-provider fallback remains env-var driven only
- If BiFrost is revisited, a fresh brief and ADR are required

## Related

- Brief (archived): `briefs/archive/2026-06-01-brief-bifrost-installation.md` (available in git history at `6751ab1`)
- ADR: `decisions/006-bifrost-local-ai-router.md` (supersedes — this ADR replaces it)
- Playbook: `playbooks/subprocess-bridge-playbook.md` (reference)
- Architecture: `ARCHITECTURE.md`