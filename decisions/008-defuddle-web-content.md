# Decision: defuddle for Web Content Extraction

**Date:** 2026-05-11
**Status:** Accepted

## Context

The defuddle extension (`.pi/extensions/defuddle.ts`) provides web content extraction via the hosted `defuddle.md` API. A question arose about whether Browserbase — a headless browser session service — would be a better fit, particularly for JS-heavy pages and paywalled content.

## Decision

Use defuddle for all web content extraction. Do not integrate Browserbase or similar headless browser services for this purpose.

## Rationale

For context-aware research (reading articles, docs, news), defuddle handles the 99% case:
- Server-rendered pages fetched in ~1-3s
- MIT-licensed, locally runnable if needed
- Whitelist/blacklist filtering for problematic domains
- SSRF protection and structured error handling

Browserbase solves a different problem: JS-rendered SPAs, auth-gated sessions, interactive automation. These are edge cases that would add auth overhead, session management, and cost (60 min/mo free, paid beyond) without solving the primary use case.

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| Browserbase | Overkill for text extraction; adds complexity, auth, and cost for JS-rendered edge cases |
| Direct Playwright scraping | Same as Browserbase — heavyweight, requires browser infra, session management |
| Custom Readability.js wrapper | defuddle IS this, with better metadata extraction and async SPA fallback |

## Consequences

**What became easier:**
- Fast, stateless fetches via `defuddle.md` API
- No infra, auth, or session management overhead
- Unified pattern for all web content needs in agents

**What became harder:**
- JS-rendered SPAs (Twitter/X, Reddit) are blocked — these are low-value sources for research anyway

**Constraints this imposes:**
- Blacklisted domains require explicit user override (`/defuddle allow <domain>`) before fetching
- If a future research need requires SPA content, revisit this decision with evidence (not speculation)

## Related

- Extension: `.pi/extensions/defuddle.ts`
- Playbook: `playbooks/defuddle-playbook.md`
- Decision: `decisions/006-jsonl-over-sqlite-knowledge.md` (related: lightweight external services over heavy infra)