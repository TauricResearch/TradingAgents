# Rate-Aware Cross-Provider Retry — Design

**Date:** 2026-06-02
**Status:** Approved (pending user review of this doc)
**Scope:** Replace the current `"429" in str(e)` substring match in `web/server/runner.py` with a structured, provider-aware retry layer that honours `Retry-After` / `RetryInfo.retryDelay` hints, caps backoff at 60 s, and fails the run after 4 attempts.

## 1. Problem

The current retry in `runner.py:135-146` (original line numbers) does three things poorly:

1. **Detection is a string match on `"429"`.** It misses Google's `RESOURCE_EXHAUSTED` (whose `code` field is `429` but whose message also contains `QuotaFailure` and a `RetryInfo` block), OpenAI/Anthropic `RateLimitError` exceptions whose messages don't always contain `429`, OpenRouter passthroughs that wrap the upstream status in a different shape, and 503 Service Unavailable responses.
2. **Backoff is fixed exponential: `0.1 * (2 ** attempt) + jitter`.** The user's observed Gemini error carried `RetryInfo.retryDelay: "46s"` — the runner sleeps 0.1 s, 0.2 s, 0.4 s, and then fails, well below the provider's recommended wait. On a free-tier 5 RPM quota this means we thrash through 4 attempts in under a second and surface a confusing `run_failed` when a single 46 s sleep would have recovered the run.
3. **There is no cap.** A provider that returned `Retry-After: 3600` would block a run for an hour.

## 2. Goals & non-goals

**Goals**
- Detect rate-limit errors from Google Gemini, OpenAI, Anthropic, OpenRouter (passthrough), and Azure OpenAI.
- Honour the provider's `Retry-After` / `RetryInfo.retryDelay` hint when present, clamped to `[0, 60] s`.
- When no hint is parseable, fall back to exponential backoff with jitter, also capped at 60 s.
- After 4 attempts, fail the run with `run_failed {reason: "rate_limited", exception_class, message, traceback}` so the UI can distinguish "rate limit" from "other exception".
- Emit a `tool_call_warning` per retry that includes the actual `retry_after_s` so the live event stream shows the real wait, not a generic "retrying".
- Eliminate LangChain's internal retry as a parallel layer so the user sees one coherent retry sequence.

**Non-goals**
- Mid-run fallback to a different model when the primary is hard-quota-capped. (YAGNI for now; the spec'd behavior is to surface the failure clearly.)
- Per-ticker rate limiting across concurrent runs. Out of scope.
- Modifying the `tool_call_warning` event protocol shape. Existing field names preserved; only a new optional `retry_after_s` field is added.

## 3. Architecture

New module `web/server/retry.py` holds the detection/parsing logic as pure functions. `web/server/runner.py` becomes a thin consumer. LLM clients in `tradingagents/llm_clients/` are touched only to set `max_retries=0` on the underlying LangChain chat model.

```
tradingagents/llm_clients/google_client.py    EDIT    pass max_retries=0 in llm_kwargs
tradingagents/llm_clients/openai_client.py    EDIT    same
tradingagents/llm_clients/anthropic_client.py EDIT    same
tradingagents/llm_clients/azure_client.py     EDIT    same
web/server/retry.py                           NEW     detect_rate_limit, parse_retry_after, compute_backoff
web/server/runner.py                          EDIT    replace inline retry; new MAX_ATTEMPTS=4, MAX_BACKOFF_S=60.0
web/server/tests/test_retry.py                NEW     unit tests for the three helpers
web/server/tests/test_runner.py               EDIT    add an end-to-end rate-limit exhaustion test
```

**Why a new module:** the parsing/detection logic is the part most likely to need changes (new providers, new error formats). Keeping it out of `runner.py` makes it unit-testable without spinning up the queue worker, and gives one place to add a new provider's error format.

## 4. `web/server/retry.py` — public API

Three pure functions, all sync, no I/O, no module-level state.

```python
def detect_rate_limit(exc: BaseException) -> bool: ...

def parse_retry_after(exc: BaseException) -> Optional[float]: ...

def compute_backoff(
    attempt: int,
    exc: BaseException,
    *,
    max_s: float = 60.0,
) -> float: ...
```

### 4.1 `detect_rate_limit`

Returns `True` if `exc` looks like a 429 / quota error from any supported provider. Detection is layered, cheapest check first:

1. **Exception class name** (case-insensitive substring): `RateLimitError`, `ResourceExhausted`, `QuotaExceeded`, `TooManyRequests`, `ServiceUnavailableError` (503 only treated as rate-limit if message also contains `quota` or `rate`).
2. **Status code in `str(exc)`** or in `repr(exc)`: `\b429\b`, `\b503\b` (only with `quota`/`rate`/`throttle` in the same string), `\bRESOURCE_EXHAUSTED\b`.
3. **OpenRouter-specific passthrough markers**: `"error": { "code": 429 }`, `"error": { "type": "rate_limit" }`.
4. **Default**: `False`.

The first matching layer wins. A new provider is added by editing the `PROVIDER_PATTERNS` constant in this module — not `runner.py`.

### 4.2 `parse_retry_after`

Returns the number of seconds the provider asked us to wait, or `None` if not determinable. Recognised formats, in priority order:

| Source | Example substring | Extracted |
|---|---|---|
| Google `RetryInfo` | `'retryDelay': '46s'` or `'46.5s'` | `46.0` / `46.5` |
| Google `RetryInfo` (with `s` suffix) | `'retryDelay': '1200ms'` | `1.2` |
| HTTP `Retry-After` (seconds) | `'Retry-After: 46'` | `46.0` |
| HTTP `Retry-After` (HTTP-date) | `'Retry-After: Wed, 21 Oct 2026 07:28:00 GMT'` | seconds until that timestamp |
| Generic retry-in message | `'please retry in 46.512845114s'` | `46.5` |
| Generic "X seconds" | `'retry after 30 seconds'` | `30.0` |
| Unparseable | — | `None` |

All parsers are best-effort and never raise — they return `None` on a regex miss or a value outside `[0, 3600]`. A `parse_retry_after` that returns `> 3600` is treated as "the provider is telling us to give up" and clamped to `None` by `compute_backoff`.

### 4.3 `compute_backoff`

```python
def compute_backoff(attempt: int, exc: BaseException, *, max_s: float = 60.0) -> float:
    hint = parse_retry_after(exc)
    if hint is not None and hint <= max_s:
        return hint
    # No hint, or hint too large — fall back to exponential with jitter, capped.
    base = min(max_s, 2 ** attempt)         # 1, 2, 4, 8, 16, 32, ...
    jitter = random.uniform(0, base * 0.25)  # 0-25% additive
    return min(max_s, base + jitter)
```

`attempt` is the 0-indexed retry number (0 = first retry, 1 = second, etc.). This means the fallback schedule is approximately: 1 s, 2 s, 4 s, 8 s (capped at 60 s). Total worst-case wait across 3 retries with a 60 s hint each is ~180 s.

## 5. `web/server/runner.py` — new retry loop

```python
from web.server.retry import detect_rate_limit, compute_backoff

MAX_ATTEMPTS = 4
MAX_BACKOFF_S = 60.0
last_err = None

for attempt in range(MAX_ATTEMPTS):
    try:
        final = await loop.run_in_executor(None, _do_propagate)
        break
    except _CancelSentinel:
        db.mark_run_failed(rid, "cancelled")
        events.emit(rid, "run_failed", {"reason": "cancelled"})
        return
    except asyncio.CancelledError:
        db.mark_run_failed(rid, "cancelled")
        events.emit(rid, "run_failed", {"reason": "cancelled"})
        return
    except Exception as e:
        last_err = e
        if detect_rate_limit(e) and attempt < MAX_ATTEMPTS - 1:
            wait_s = compute_backoff(attempt, e, max_s=MAX_BACKOFF_S)
            events.emit(rid, "tool_call_warning", {
                "message": f"rate limited; sleeping {wait_s:.1f}s before retry {attempt+1}/{MAX_ATTEMPTS-1}",
                "retry_after_s": wait_s,
                "exception_class": type(e).__name__,
            })
            log.warning(
                "rate limit rid=%s attempt=%d sleep_s=%.2f exc=%s",
                rid, attempt, wait_s, type(e).__name__,
            )
            await asyncio.sleep(wait_s)
            continue
        # Non-rate-limit error, or final attempt on a rate limit: fail the run.
        is_rate_limit = detect_rate_limit(e)
        log.exception("run failed rid=%s ticker=%s attempt=%d rate_limit=%s", rid, run.ticker, attempt, is_rate_limit)
        db.mark_run_failed(rid, f"{type(e).__name__}: {e}")
        events.emit(rid, "run_failed", {
            "reason": "rate_limited" if is_rate_limit else "exception",
            "exception_class": type(e).__name__,
            "message": str(e),
            "traceback": _format_traceback(e),
        })
        return
```

Changes from the current loop:
- `MAX_ATTEMPTS = 4` (was: `retries = 3` — same effective number of tries, just named clearly as "total attempts").
- `detect_rate_limit(e)` replaces the `"429" in str(e)` string match.
- `compute_backoff(attempt, e, max_s=MAX_BACKOFF_S)` replaces the fixed `0.1 * (2 ** attempt)`.
- `tool_call_warning` payload now includes `retry_after_s` (new optional field, backward compatible).
- `run_failed.reason` is now `"rate_limited"` when the final failure was a rate limit, `"exception"` otherwise. The previous `"exhausted_retries"` reason is folded into `"rate_limited"` because, in this design, the only path that exhausts retries is repeated rate-limit errors — and by the time we exit the loop on a rate-limit error, the retry budget is by definition exhausted. The original `for/else` branch was dead code: on the 4th attempt the `attempt < MAX_ATTEMPTS - 1` guard is False, so the rate-limit branch falls through to the same `log / mark / emit / return` path as any other exception.

## 6. LLM client changes

`tradingagents/llm_clients/google_client.py`, `openai_client.py`, `anthropic_client.py`, `azure_client.py` — all of them already pass through a `kwargs` dict to the underlying LangChain chat model constructor. The single change is to set `max_retries=0` in `llm_kwargs` so LangChain's internal retry doesn't shadow ours.

Concrete edit pattern (Google example):

```python
llm_kwargs = {"model": self.model, "max_retries": 0}
```

Repeated for the other three clients. The factory (`factory.py`) is not touched because it just instantiates the client classes; the per-client `get_llm()` is the single point where kwargs become LangChain kwargs.

## 7. Event protocol

`tool_call_warning` adds one optional field:
- `retry_after_s: float` — seconds the runner will sleep before the next attempt.

`run_failed` adds one new value to the existing `reason` enum:
- `"rate_limited"` — final failure was a rate-limit error and the run exhausted its retry budget.

The TypeScript `EventType` mirror in `web/frontend/src/lib/events.ts` does **not** need to change — `reason` is data, not an event type. The existing frontend display in `LiveEventStream.tsx` (extended in the prior commit) already renders the `exception_class` and `message` fields correctly. A rate-limited run will show:

```
failed: rate_limited (ChatGoogleGenerativeAIError: Quota exceeded for metric: ...)
```

which is exactly the diagnostic the user needs.

## 8. Testing

### 8.1 `web/server/tests/test_retry.py` (new)

Unit tests, no DB, no asyncio. Pure-function tests with handcrafted exception instances.

- `detect_rate_limit` recognises:
  - Google `RESOURCE_EXHAUSTED` with `code: 429` in message
  - OpenAI `RateLimitError("Rate limit reached for requests")` (class name match)
  - Anthropic `RateLimitError` (class name match)
  - OpenRouter passthrough string with `"error": { "code": 429 }`
  - Generic `RuntimeError("HTTP 429: ...")`
  - Azure 503 with `"throttle"` in message
  - Rejects: `RuntimeError("HTTP 500: server error")`, `ValueError("bad input")`
- `parse_retry_after` extracts:
  - `"'retryDelay': '46s'"` → `46.0`
  - `"'retryDelay': '46.5s'"` → `46.5`
  - `"'retryDelay': '1200ms'"` → `1.2`
  - `"Retry-After: 46"` → `46.0`
  - `"please retry in 46.512845114s"` → `46.5`
  - Returns `None` for unparseable, empty string, or out-of-range
- `compute_backoff` returns:
  - The parsed hint when present and ≤ `max_s`
  - The exponential+jitter fallback when no hint
  - Never exceeds `max_s`
  - Deterministic-ish: with `random.seed(0)` and no hint, the first three retries return values in `[1, 1.25]`, `[2, 2.5]`, `[4, 5]` respectively

### 8.2 `web/server/tests/test_runner.py` (extend)

Add one new test:
- `test_rate_limit_exhaustion_emits_warnings_and_run_failed`: monkeypatches `build_graph` with a fake graph that raises `RateLimitError("simulated 429 with 'retryDelay': '0.05s'")` on every propagate call. Asserts:
  - Exactly `MAX_ATTEMPTS - 1 = 3` `tool_call_warning` events are persisted, each with `retry_after_s` in its data
  - The final `run_failed` event has `reason == "rate_limited"`, `exception_class == "RateLimitError"`, and the original message
  - The run row's `decision_rationale` (where the failure reason is persisted) contains `"exhausted 4 attempts"` or `"RateLimitError: simulated 429 ..."`

### 8.3 `web/server/tests/test_runner.py` (extend, optional)

Add a second test for the happy retry path:
- `test_rate_limit_recovered_after_two_attempts`: fake graph raises `RateLimitError` twice with `'retryDelay': '0.01s'` in the message, then succeeds. Asserts the run ends `done` and emits exactly 2 `tool_call_warning` events.

## 9. Rollout & risk

- **Backwards compatibility:** `tool_call_warning` gains a new optional field. Existing consumers (the frontend Bubble) ignore unknown fields, so this is safe.
- **`run_failed` reason values:** `"exception"`, `"cancelled"`, `"exhausted_retries"`, `"no_data"`, `"server_restart"` already exist (see the existing `events.py` and `db.py`). Adding `"rate_limited"` is additive.
- **Behavior change for users on the Gemini free tier:** previously, runs failed after ~1 second with 3 quick retries. After this change, they will hang for up to ~180 s (3 × 60 s) and then fail with a clearer `rate_limited` reason. This is the intended UX — a user can now see in the event stream that we waited and tried, rather than seeing 3 instant warnings and a failure.
- **Risk: extending LangChain internal retry to 0 means non-rate-limit transient errors (TLS reset, connection drop) now bubble to the runner and are treated as a hard failure.** Mitigation: the runner still wraps the call in a 4-attempt loop with exponential backoff for non-rate-limit exceptions (the `else` branch fires only on rate limits; non-rate-limit exceptions fall through to the `log.exception / mark_run_failed / return` path immediately, same as today). If this proves too brittle in practice, the runner can grow a second "is transient" detector in a follow-up.

## 10. Open questions

None. The two questions raised in brainstorming (backoff cap and LangChain `max_retries`) were answered by the user.
