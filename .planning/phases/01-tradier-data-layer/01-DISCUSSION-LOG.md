# Phase 1: Tradier Data Layer - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-29
**Phase:** 01-tradier-data-layer
**Areas discussed:** API Authentication, Data Fetching Strategy, Data Structure, Error Handling, Output Format

---

## API Authentication

| Option | Description | Selected |
|--------|-------------|----------|
| Env var (Recommended) | TRADIER_API_KEY env var, matching existing pattern | ✓ |
| Config file | Store in a config file alongside other settings | |
| Both | Env var with config file fallback | |

**User's choice:** Env var
**Notes:** Consistent with OPENAI_API_KEY, ALPHA_VANTAGE_KEY pattern

---

## Chain Fetch Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Pre-fetch all (Recommended) | Fetch all expirations in DTE range upfront, cache for session | ✓ |
| Lazy per-agent | Each agent fetches only the expirations it needs on demand | |
| Configurable | Default to pre-fetch, allow lazy mode | |

**User's choice:** Pre-fetch all
**Notes:** Avoids redundant API calls across multiple options agents

---

## Data Caching

| Option | Description | Selected |
|--------|-------------|----------|
| In-memory session | Cache in memory for duration of one propagate() call | |
| Disk with TTL | Cache to disk with configurable TTL | |
| You decide | Claude picks best approach | ✓ |

**User's choice:** Claude's discretion
**Notes:** None

---

## Sandbox Support

| Option | Description | Selected |
|--------|-------------|----------|
| Yes (Recommended) | Auto-detect sandbox vs production from env var | ✓ |
| Production only | Only support production API | |

**User's choice:** Yes
**Notes:** TRADIER_SANDBOX=true env var for detection

---

## Rate Limit Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Retry with backoff | Exponential backoff on 429 errors | |
| Queue and throttle | Pre-emptive request queue | |
| You decide | Claude picks based on existing patterns | ✓ |

**User's choice:** Claude's discretion
**Notes:** Should follow AlphaVantageRateLimitError pattern

---

## DTE Range

| Option | Description | Selected |
|--------|-------------|----------|
| 7-60 DTE (Recommended) | Covers income strategies plus weeklies | |
| 0-90 DTE | Wider range | |
| Configurable | User sets min/max DTE | |
| 0-50 DTE (Custom) | User-specified range | ✓ |

**User's choice:** 0-50 DTE
**Notes:** User specified custom range covering near-term through TastyTrade sweet spot

---

## Output Shape

| Option | Description | Selected |
|--------|-------------|----------|
| Pandas DataFrame | Consistent with existing yfinance data handling | |
| Typed dataclass | Custom OptionsChain dataclass | |
| Both | DataFrame for bulk, dataclass for individual access | ✓ |

**User's choice:** Both
**Notes:** Dual format for different consumption patterns

---

## Claude's Discretion

- Caching strategy (in-memory vs disk TTL)
- Rate limit handling approach

## Deferred Ideas

None
