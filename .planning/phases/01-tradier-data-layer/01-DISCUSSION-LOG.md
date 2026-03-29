# Phase 1: Tradier Data Layer - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.
>
> **Scope:** Rows marked **“Claude's discretion”** / **“You decide”** are discussion-only until copied into **01-CONTEXT.md** (or another canonical doc). Implementation agents should follow **CONTEXT.md**, not un-promoted discussion rows.

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

**User's choice:** Claude's discretion — **TODO:** promote chosen approach (memory vs disk, TTL) into **01-CONTEXT.md** before execution if it becomes a hard requirement.
**Notes:** **Constraints for implementers:** target session scope ≈ one CLI `propagate()` / analysis run; prefer **in-memory** unless persistence is required. If disk cache: document max footprint and TTL (e.g. stale chain tolerance on the order of minutes unless user refreshes). Low-memory environments: in-memory only, no mandatory disk I/O.

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

**User's choice:** Claude's discretion — **TODO:** mirror final retry/throttle design in **01-CONTEXT.md** when locked.
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
**Notes:** User specified custom range covering near-term through **Tastytrade** methodology sweet spot

---

## Output Shape

| Option | Description | Selected |
|--------|-------------|----------|
| Pandas DataFrame | Consistent with existing yfinance data handling | |
| Typed dataclass | Custom OptionsChain dataclass | |
| Both | DataFrame for bulk, dataclass for individual access | ✓ |

**User's choice:** Both — **promoted to CONTEXT D-06:** canonical typed `OptionsChain` / `OptionsContract`; DataFrame via `to_dataframe()` for bulk; single source of truth in the dataclass list (see **01-CONTEXT.md**).
**Notes:** Rationale: dataclasses give validation and clear contracts; DataFrames match existing analyst tooling without duplicating mutable parallel state.

---

## Claude's Discretion

- Caching strategy (in-memory vs disk TTL) — promote to CONTEXT before treating as mandatory
- Rate limit handling approach — promote to CONTEXT before treating as mandatory

## Deferred Ideas

None
