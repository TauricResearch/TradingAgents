# Rate-Aware Cross-Provider Retry — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `"429" in str(e)` substring match in `web/server/runner.py` with structured, provider-aware rate-limit detection and retry, honouring provider `Retry-After` / `RetryInfo.retryDelay` hints capped at 60 s, failing after 4 attempts, and disabling LangChain's internal retry layer.

**Architecture:** A new pure-function module `web/server/retry.py` holds `detect_rate_limit`, `parse_retry_after`, `compute_backoff`. `runner.py` becomes a thin consumer. Each LLM client gets `max_retries=0` so we have one source of truth for retry. Tests: a new `test_retry.py` for the helpers and two new tests in `test_runner.py` for end-to-end behaviour.

**Tech Stack:** Python 3.11, pytest + pytest-asyncio, LangChain chat models, existing test fixtures in `web/server/tests/fixtures/`.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `web/server/retry.py` | CREATE | `detect_rate_limit`, `parse_retry_after`, `compute_backoff` — pure functions, no I/O, no module state |
| `web/server/tests/test_retry.py` | CREATE | Unit tests for the three helpers |
| `web/server/runner.py` | MODIFY | Import the new helpers; replace inline retry loop; emit `retry_after_s` on `tool_call_warning`; emit `reason: "rate_limited"` on terminal `run_failed`; drop unused `import random` |
| `web/server/tests/test_runner.py` | MODIFY | Add `test_rate_limit_exhaustion_emits_warnings_and_run_failed` and `test_rate_limit_recovered_after_two_attempts` |
| `tradingagents/llm_clients/google_client.py` | MODIFY | Hardcode `max_retries=0` in `llm_kwargs` |
| `tradingagents/llm_clients/openai_client.py` | MODIFY | Hardcode `max_retries=0` in `llm_kwargs` |
| `tradingagents/llm_clients/anthropic_client.py` | MODIFY | Hardcode `max_retries=0` in `llm_kwargs` |
| `tradingagents/llm_clients/azure_client.py` | MODIFY | Hardcode `max_retries=0` in `llm_kwargs` |

---

## Task 1: `detect_rate_limit` (TDD)

**Files:**
- Create: `web/server/tests/test_retry.py`
- Create: `web/server/retry.py`

- [ ] **Step 1: Write the failing test**

Create `web/server/tests/test_retry.py` with this content:

```python
"""Unit tests for web.server.retry — pure-function helpers."""
from __future__ import annotations

import random
from datetime import datetime, timezone

import pytest

from web.server.retry import (
    compute_backoff,
    detect_rate_limit,
    parse_retry_after,
)


class TestDetectRateLimit:
    def test_google_resource_exhausted(self):
        exc = Exception(
            "Error calling model 'gemini-3.5-flash' (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. "
            "'retryDelay': '46s'"
        )
        assert detect_rate_limit(exc) is True

    def test_openai_rate_limit_error_class(self):
        class RateLimitError(Exception):
            pass
        assert detect_rate_limit(RateLimitError("Rate limit reached for gpt-4")) is True

    def test_anthropic_rate_limit_error_class(self):
        class AnthropicRateLimitError(Exception):
            pass
        assert detect_rate_limit(AnthropicRateLimitError("rate limit exceeded")) is True

    def test_openrouter_code_429_passthrough(self):
        exc = Exception('{"error": {"code": 429, "message": "rate-limited"}}')
        assert detect_rate_limit(exc) is True

    def test_openrouter_type_rate_limit_passthrough(self):
        exc = Exception('{"error": {"type": "rate_limit", "message": "Too Many Requests"}}')
        assert detect_rate_limit(exc) is True

    def test_generic_429_substring(self):
        assert detect_rate_limit(RuntimeError("HTTP 429: too many requests")) is True

    def test_azure_503_with_throttle_word(self):
        assert detect_rate_limit(Exception("Service Unavailable: 503 throttle, retry later")) is True

    def test_azure_503_alone_is_not_rate_limit(self):
        # 503 alone is too generic — only treat as rate-limit if the message
        # also mentions throttle/quota/rate.
        assert detect_rate_limit(Exception("Service Unavailable: 503")) is False

    def test_rejects_500(self):
        assert detect_rate_limit(RuntimeError("HTTP 500: server error")) is False

    def test_rejects_value_error(self):
        assert detect_rate_limit(ValueError("bad input")) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest web\server\tests\test_retry.py::TestDetectRateLimit -v`
Expected: collection error or ImportError because `web.server.retry` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Create `web/server/retry.py`:

```python
"""Rate-aware retry helpers used by web.server.runner.

Pure functions, no I/O, no module state. Kept separate from the runner
so detection/parsing can be unit-tested without spinning up the queue
worker and so new providers can be supported by editing this file
alone.
"""
from __future__ import annotations

import random
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional


# Substrings (case-insensitive) that identify a rate-limit exception class.
# Order doesn't matter — first match wins.
_RATE_LIMIT_CLASS_NAMES = (
    "ratelimiterror",
    "resourceexhausted",
    "quotaexceeded",
    "quotafailure",
    "toomanyrequests",
    "throttlingerror",
)

# Regex patterns matched against str(exc), in priority order.
# Patterns that need a qualifier word (e.g. 503 alone is too generic) include it
# inside the same regex.
_RATE_LIMIT_STRING_PATTERNS = (
    r"\b429\b",
    r"\bRESOURCE_EXHAUSTED\b",
    r'"code"\s*:\s*429',
    r'"type"\s*:\s*["\']rate_limit["\']',
    r"\b503\b.*\b(throttle|quota|rate[\s-]?limit)\b",
    r"\bquota[_ ]?exceeded\b",
)


def detect_rate_limit(exc: BaseException) -> bool:
    """True if exc looks like a 429 / quota error from any supported provider.

    Detection layers, cheapest first:
      1. Exception class name contains a known substring.
      2. str(exc) matches one of the known rate-limit regex patterns.
    """
    cls_name = type(exc).__name__.lower()
    for needle in _RATE_LIMIT_CLASS_NAMES:
        if needle in cls_name:
            return True
    msg = str(exc)
    for pattern in _RATE_LIMIT_STRING_PATTERNS:
        if re.search(pattern, msg, re.IGNORECASE):
            return True
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest web\server\tests\test_retry.py::TestDetectRateLimit -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add web/server/retry.py web/server/tests/test_retry.py
git commit -m "feat(web): add detect_rate_limit helper for cross-provider retry"
```

---

## Task 2: `parse_retry_after` (TDD)

**Files:**
- Modify: `web/server/tests/test_retry.py`
- Modify: `web/server/retry.py`

- [ ] **Step 1: Append failing tests for parse_retry_after**

Append to `web/server/tests/test_retry.py`:

```python
class TestParseRetryAfter:
    def test_google_retry_delay_seconds(self):
        exc = Exception("'retryDelay': '46s'")
        assert parse_retry_after(exc) == 46.0

    def test_google_retry_delay_decimal(self):
        exc = Exception("'retryDelay': '46.5s'")
        assert parse_retry_after(exc) == 46.5

    def test_google_retry_delay_milliseconds(self):
        exc = Exception("'retryDelay': '1200ms'")
        assert parse_retry_after(exc) == 1.2

    def test_retry_after_header_seconds(self):
        exc = Exception("HTTP 429: rate limit. Retry-After: 46")
        assert parse_retry_after(exc) == 46.0

    def test_retry_after_header_case_insensitive(self):
        exc = Exception("HTTP 429: rate limit. retry-after: 30")
        assert parse_retry_after(exc) == 30.0

    def test_retry_in_seconds_decimal(self):
        exc = Exception("Quota exceeded. Please retry in 46.512845114s.")
        assert parse_retry_after(exc) == 46.5

    def test_retry_after_word_seconds(self):
        exc = Exception("Please retry after 30 seconds")
        assert parse_retry_after(exc) == 30.0

    def test_returns_none_for_unparseable(self):
        exc = Exception("Some error without any retry info")
        assert parse_retry_after(exc) is None

    def test_returns_none_for_empty_message(self):
        assert parse_retry_after(Exception("")) is None

    def test_retry_after_http_date_with_fixed_now(self):
        # 2026-06-02T12:00:00Z is the fixed "now" for this test.
        fixed_now = datetime(2026, 6, 2, 12, 0, 0, tzinfo=timezone.utc)
        # Target is 60 seconds after "now".
        exc = Exception("Retry-After: Tue, 02 Jun 2026 12:01:00 GMT")
        result = parse_retry_after(exc, now=fixed_now)
        assert result is not None
        assert 59.0 <= result <= 60.0

    def test_retry_after_http_date_in_past_returns_none(self):
        fixed_now = datetime(2026, 6, 2, 12, 0, 0, tzinfo=timezone.utc)
        exc = Exception("Retry-After: Mon, 01 Jun 2026 12:00:00 GMT")
        assert parse_retry_after(exc, now=fixed_now) is None

    def test_retry_after_huge_seconds_is_clamped_to_none(self):
        # 24h+ hints are treated as "give up" and filtered out so the
        # caller can fall back to exponential backoff.
        exc = Exception("'retryDelay': '100000s'")
        assert parse_retry_after(exc) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest web\server\tests\test_retry.py::TestParseRetryAfter -v`
Expected: all fail with `AttributeError: module 'web.server.retry' has no attribute 'parse_retry_after'`.

- [ ] **Step 3: Add the implementation**

Add to `web/server/retry.py` (replace the `detect_rate_limit` function or append after it — append for clean diff):

```python
# Cap provider hints that are unreasonably large (>1 hour). When a
# provider tells us to wait longer than that we treat it as a signal
# that we should give up and surface the failure, not stall the worker.
_MAX_RETRY_AFTER_S = 3600.0

# Pattern for Google's RetryInfo block: 'retryDelay': '46s' or '46.5s' or '1200ms'.
_GOOGLE_RETRY_DELAY_RE = re.compile(
    r"'retryDelay'\s*:\s*'(\d+(?:\.\d+)?)(ms|s)'"
)
# Pattern for HTTP Retry-After header in seconds.
_HTTP_RETRY_AFTER_SECONDS_RE = re.compile(
    r"Retry-After\s*:\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
# Pattern for HTTP Retry-After header as RFC 7231 HTTP-date.
_HTTP_RETRY_AFTER_DATE_RE = re.compile(
    r"Retry-After\s*:\s*"
    r"([A-Za-z]{3},\s+\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\s+\d{2}:\d{2}:\d{2}\s+GMT)",
    re.IGNORECASE,
)
# Pattern for "retry in 46s" / "retry after 30 seconds".
_GENERIC_RETRY_RE = re.compile(
    r"retry\s+(?:in|after)\s+(\d+(?:\.\d+)?)\s*(?:seconds?|s)",
    re.IGNORECASE,
)


def parse_retry_after(
    exc: BaseException, *, now: Optional[datetime] = None
) -> Optional[float]:
    """Seconds the provider asked us to wait, or None if not determinable.

    Recognised formats, in priority order:
      - Google RetryInfo block: 'retryDelay': '46s' | '46.5s' | '1200ms'
      - HTTP Retry-After header (seconds or RFC 7231 HTTP-date)
      - Generic "retry in 46s" / "retry after 30 seconds"
    """
    if now is None:
        now = datetime.now(timezone.utc)
    msg = str(exc)

    m = _GOOGLE_RETRY_DELAY_RE.search(msg)
    if m:
        value = float(m.group(1))
        unit = m.group(2)
        seconds = value / 1000.0 if unit == "ms" else value
        return _clamp_or_none(seconds)

    m = _HTTP_RETRY_AFTER_SECONDS_RE.search(msg)
    if m:
        return _clamp_or_none(float(m.group(1)))

    m = _HTTP_RETRY_AFTER_DATE_RE.search(msg)
    if m:
        try:
            target = parsedate_to_datetime(m.group(1))
            if target.tzinfo is None:
                target = target.replace(tzinfo=timezone.utc)
            delta = (target - now).total_seconds()
        except (TypeError, ValueError):
            return None
        return _clamp_or_none(delta)

    m = _GENERIC_RETRY_RE.search(msg)
    if m:
        return _clamp_or_none(float(m.group(1)))

    return None


def _clamp_or_none(seconds: float) -> Optional[float]:
    """Return seconds if 0 < seconds <= 3600, else None."""
    if 0 < seconds <= _MAX_RETRY_AFTER_S:
        return seconds
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest web\server\tests\test_retry.py::TestParseRetryAfter -v`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add web/server/retry.py web/server/tests/test_retry.py
git commit -m "feat(web): add parse_retry_after helper honoring provider hints"
```

---

## Task 3: `compute_backoff` (TDD)

**Files:**
- Modify: `web/server/tests/test_retry.py`
- Modify: `web/server/retry.py`

- [ ] **Step 1: Append failing tests for compute_backoff**

Append to `web/server/tests/test_retry.py`:

```python
class TestComputeBackoff:
    def test_returns_hint_when_within_cap(self):
        exc = Exception("'retryDelay': '5s'")
        assert compute_backoff(0, exc) == 5.0

    def test_returns_hint_at_cap(self):
        exc = Exception("'retryDelay': '60s'")
        assert compute_backoff(0, exc) == 60.0

    def test_hint_above_cap_falls_back_to_exponential(self):
        # 100s hint exceeds default cap of 60 → falls back.
        # With random.seed(0) on attempt=0, the exponential+jitter is 1.0..1.25.
        exc = Exception("'retryDelay': '100s'")
        random.seed(0)
        result = compute_backoff(0, exc)
        assert 1.0 <= result <= 1.25

    def test_no_hint_returns_exponential_with_jitter(self):
        # attempt=0: base=1, jitter 0..0.25
        random.seed(0)
        assert 1.0 <= compute_backoff(0, Exception("x")) <= 1.25
        # attempt=1: base=2, jitter 0..0.5
        assert 2.0 <= compute_backoff(1, Exception("x")) <= 2.5
        # attempt=2: base=4, jitter 0..1.0
        assert 4.0 <= compute_backoff(2, Exception("x")) <= 5.0
        # attempt=3: base=8, jitter 0..2.0
        assert 8.0 <= compute_backoff(3, Exception("x")) <= 10.0

    def test_caps_at_max_s_for_high_attempt(self):
        # attempt=20 would be 2**20 = 1M, must be capped.
        result = compute_backoff(20, Exception("x"))
        assert 0 < result <= 60.0

    def test_custom_max_s(self):
        # Hint within custom cap → returned as-is.
        exc = Exception("'retryDelay': '5s'")
        assert compute_backoff(0, exc, max_s=10.0) == 5.0
        # Hint above custom cap → fallback.
        random.seed(0)
        result = compute_backoff(0, exc, max_s=2.0)
        assert 0 < result <= 2.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest web\server\tests\test_retry.py::TestComputeBackoff -v`
Expected: all fail with `ImportError: cannot import name 'compute_backoff'`.

- [ ] **Step 3: Add the implementation**

Append to `web/server/retry.py`:

```python
def compute_backoff(
    attempt: int,
    exc: BaseException,
    *,
    max_s: float = 60.0,
) -> float:
    """Seconds to sleep before retrying.

    Prefers ``parse_retry_after(exc)`` when present and within ``max_s``;
    otherwise falls back to ``min(max_s, 2 ** attempt) + uniform(0, 25%)``
    jitter, also capped at ``max_s``.

    ``attempt`` is 0-indexed (0 = first retry, 1 = second, ...).
    """
    hint = parse_retry_after(exc)
    if hint is not None and 0 < hint <= max_s:
        return hint
    base = min(max_s, 2 ** attempt)
    jitter = random.uniform(0, base * 0.25)
    return min(max_s, base + jitter)
```

- [ ] **Step 4: Run the full retry test file to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest web\server\tests\test_retry.py -v`
Expected: 30 passed (10 + 12 + 8 = 30 across the three test classes — recompute: TestDetectRateLimit has 10, TestParseRetryAfter has 12, TestComputeBackoff has 6. 10 + 12 + 6 = 28 tests total).

- [ ] **Step 5: Commit**

```bash
git add web/server/retry.py web/server/tests/test_retry.py
git commit -m "feat(web): add compute_backoff with cap and provider-hint preference"
```

---

## Task 4: Update `runner.py` to use the retry module

**Files:**
- Modify: `web/server/runner.py`

- [ ] **Step 1: Update the import and constants**

In `web/server/runner.py`, replace the existing imports near the top. After the change, lines 1-20 should look like:

```python
"""Async orchestrator that wraps TradingAgentsGraph and emits typed events."""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
import traceback
from datetime import datetime, timezone
from typing import Optional

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

from web.server import db, events
from web.server.retry import compute_backoff, detect_rate_limit


log = logging.getLogger(__name__)

MAX_CONCURRENT = int(os.environ.get("TRADINGAGENTS_DASHBOARD_MAX_CONCURRENT", "3"))

# Retry policy. See docs/superpowers/specs/2026-06-02-rate-aware-retry-design.md
MAX_ATTEMPTS = 4
MAX_BACKOFF_S = 60.0
```

Note: `import random` is removed (no longer used in this file — `compute_backoff` uses it internally).

- [ ] **Step 2: Replace the retry loop**

Replace the existing block from `        loop = asyncio.get_event_loop()` (line 121 in the current file) through the end of the `else:` branch (line 156) with the following code:

```python
        loop = asyncio.get_event_loop()
        last_err = None
        trade_date = datetime.now(timezone.utc).date().isoformat()

        def _do_propagate():
            return graph.propagate(run.ticker, trade_date, event_callback=cb)

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
                log.exception(
                    "run failed rid=%s ticker=%s attempt=%d rate_limit=%s",
                    rid, run.ticker, attempt, is_rate_limit,
                )
                db.mark_run_failed(rid, f"{type(e).__name__}: {e}")
                events.emit(rid, "run_failed", {
                    "reason": "rate_limited" if is_rate_limit else "exception",
                    "exception_class": type(e).__name__,
                    "message": str(e),
                    "traceback": _format_traceback(e),
                })
                return
```

Note: the `for/else:` branch from the original code is intentionally removed — it was unreachable in the new design (see spec section 5).

- [ ] **Step 3: Run the existing runner tests to confirm no regression**

Run: `.venv\Scripts\python.exe -m pytest web\server\tests\test_runner.py -v`
Expected: 3 passed (the three pre-existing tests).

- [ ] **Step 4: Commit**

```bash
git add web/server/runner.py
git commit -m "refactor(web): use rate-aware retry helpers in runner"
```

---

## Task 5: Add rate-limit tests to `test_runner.py`

**Files:**
- Modify: `web/server/tests/test_runner.py`

- [ ] **Step 1: Append the exhaustion test**

Append to `web/server/tests/test_runner.py`:

```python
@pytest.mark.asyncio
async def test_rate_limit_exhaustion_emits_warnings_and_run_failed(monkeypatch, temp_db):
    """All 4 attempts hit a rate limit; final event has reason=rate_limited
    and exactly 3 tool_call_warning events were persisted in between."""
    class _AlwaysRateLimit(RuntimeError):
        pass

    def always_failing_graph(config=None):
        class _Failing:
            def propagate(self_inner, ticker, trade_date, *, event_callback=None):
                raise _AlwaysRateLimit(
                    "Error calling model 'gemini-3.5-flash' (RESOURCE_EXHAUSTED): 429. "
                    "'retryDelay': '0.05s'"
                )
        return _Failing()

    monkeypatch.setattr(runner, "build_graph", always_failing_graph)
    monkeypatch.setattr(runner.events, "emit", lambda rid, t, d: db.append_event(rid, t, d))

    await runner.start(num_workers=1)
    try:
        rid = runner.enqueue("NVDA", idempotency_key="NVDA:rl-exhaust")
        await runner._wait_for_idle(timeout=10)

        events_list = db.events_for_run(rid)
        warnings = [e for e in events_list if e.type == "tool_call_warning"]
        run_failed = [e for e in events_list if e.type == "run_failed"]

        # 3 retries (MAX_ATTEMPTS=4 → 3 sleeps before the final attempt fails).
        assert len(warnings) == 3, [w.data for w in warnings]
        for w in warnings:
            assert w.data.get("retry_after_s") is not None
            assert w.data.get("exception_class") == "_AlwaysRateLimit"
            # 0.05s hint is well under the 60s cap, so the hint is used.
            assert 0 < w.data["retry_after_s"] <= 0.1

        # Final failure: rate_limited, with the original message preserved.
        assert len(run_failed) == 1
        assert run_failed[0].data["reason"] == "rate_limited"
        assert run_failed[0].data["exception_class"] == "_AlwaysRateLimit"
        assert "RESOURCE_EXHAUSTED" in run_failed[0].data["message"]

        run = db.get_run(rid)
        assert run.status == "failed"
    finally:
        await runner.stop()


@pytest.mark.asyncio
async def test_rate_limit_recovered_after_two_attempts(monkeypatch, temp_db):
    """First two attempts raise a rate-limit; third succeeds. The run ends
    'done', with exactly 2 tool_call_warning events and a run_finished."""
    class _RateLimit(RuntimeError):
        pass

    counter = {"calls": 0}

    def flaky_graph(config=None):
        class _Flaky:
            def propagate(self_inner, ticker, trade_date, *, event_callback=None):
                counter["calls"] += 1
                if counter["calls"] <= 2:
                    raise _RateLimit("'retryDelay': '0.01s'")
                return {"decision": {"action": "HOLD"}}
        return _Flaky()

    monkeypatch.setattr(runner, "build_graph", flaky_graph)
    monkeypatch.setattr(runner.events, "emit", lambda rid, t, d: db.append_event(rid, t, d))

    await runner.start(num_workers=1)
    try:
        rid = runner.enqueue("AAPL", idempotency_key="AAPL:rl-recover")
        await runner._wait_for_idle(timeout=5)

        run = db.get_run(rid)
        assert run.status == "done"
        assert run.decision_action == "HOLD"

        events_list = db.events_for_run(rid)
        warnings = [e for e in events_list if e.type == "tool_call_warning"]
        run_finished = [e for e in events_list if e.type == "run_finished"]
        run_failed = [e for e in events_list if e.type == "run_failed"]

        assert len(warnings) == 2
        assert len(run_finished) == 1
        assert len(run_failed) == 0
    finally:
        await runner.stop()
```

- [ ] **Step 2: Run the new tests**

Run: `.venv\Scripts\python.exe -m pytest web\server\tests\test_runner.py -v`
Expected: 5 passed (3 pre-existing + 2 new).

- [ ] **Step 3: Commit**

```bash
git add web/server/tests/test_runner.py
git commit -m "test(web): cover rate-limit exhaustion and recovery in runner"
```

---

## Task 6: Set `max_retries=0` on the four LLM clients

**Files:**
- Modify: `tradingagents/llm_clients/google_client.py`
- Modify: `tradingagents/llm_clients/openai_client.py`
- Modify: `tradingagents/llm_clients/anthropic_client.py`
- Modify: `tradingagents/llm_clients/azure_client.py`

- [ ] **Step 1: Google client**

In `tradingagents/llm_clients/google_client.py`, change the first line of `get_llm` from:

```python
        llm_kwargs = {"model": self.model}
```

to:

```python
        llm_kwargs = {"model": self.model, "max_retries": 0}
```

- [ ] **Step 2: OpenAI client**

In `tradingagents/llm_clients/openai_client.py`, find the line inside `get_llm` that reads `llm_kwargs = {"model": self.model}` (currently line 208) and change to:

```python
        llm_kwargs = {"model": self.model, "max_retries": 0}
```

- [ ] **Step 3: Anthropic client**

In `tradingagents/llm_clients/anthropic_client.py`, find the line inside `get_llm` that reads `llm_kwargs = {"model": self.model}` (currently line 52) and change to:

```python
        llm_kwargs = {"model": self.model, "max_retries": 0}
```

- [ ] **Step 4: Azure client**

In `tradingagents/llm_clients/azure_client.py`, find the block inside `get_llm` that reads:

```python
        llm_kwargs = {
            "model": self.model,
            "azure_deployment": os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", self.model),
        }
```

and change to:

```python
        llm_kwargs = {
            "model": self.model,
            "azure_deployment": os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", self.model),
            "max_retries": 0,
        }
```

- [ ] **Step 5: Run any LLM-client-related tests**

Run: `.venv\Scripts\python.exe -m pytest tests\ -k "llm or client" -v --no-header`
Expected: existing tests pass (or no tests exist — both are fine; the edit is mechanical and well-bounded by the LangChain `max_retries=0` kwarg).

- [ ] **Step 6: Commit**

```bash
git add tradingagents/llm_clients/google_client.py tradingagents/llm_clients/openai_client.py tradingagents/llm_clients/anthropic_client.py tradingagents/llm_clients/azure_client.py
git commit -m "feat(llm): disable LangChain internal retries so runner is single source of truth"
```

---

## Task 7: Final verification

- [ ] **Step 1: Run all backend tests**

Run: `.venv\Scripts\python.exe -m pytest web\server\tests\ -v`
Expected: all tests pass — 3 pre-existing runner tests + 2 new runner tests + 28 retry tests + anything else in the test directory.

- [ ] **Step 2: Run frontend tests (sanity check, no changes expected)**

Run: `cd web\frontend; .\node_modules\.bin\vitest.cmd run`
Expected: 17 passed (no changes in this plan affect the frontend).

- [ ] **Step 3: Final commit if any incidental changes**

If the working tree has uncommitted changes after steps 1–2, commit them with a clear message (e.g. `chore: post-implementation cleanup`). If clean, skip.

```bash
git status
# if dirty:
git add -p
git commit -m "chore: post-implementation cleanup"
```

---

## Self-review

**Spec coverage check** (each spec section → plan task):
- §1 Problem → all tasks; surfaced by Task 4's replacement.
- §2 Goals → Task 1 (detect), Task 2 (parse), Task 3 (backoff), Task 4 (4 attempts, cap=60s, event payload).
- §3 Architecture → file structure table at top.
- §4 retry.py API → Tasks 1, 2, 3.
- §5 runner.py loop → Task 4 (full code shown).
- §6 LLM client `max_retries=0` → Task 6 (all four files).
- §7 Event protocol → Task 4 (`retry_after_s` on `tool_call_warning`, `reason: "rate_limited"` on `run_failed`).
- §8 Testing → Task 1/2/3 unit tests, Task 5 runner integration tests.
- §9 Rollout & risk → covered in plan Task 7 verification.

**Placeholder scan:** No TBDs, no "implement later", every step has exact code or exact file paths.

**Type consistency:** All function signatures consistent — `detect_rate_limit(exc) -> bool`, `parse_retry_after(exc, *, now=None) -> Optional[float]`, `compute_backoff(attempt, exc, *, max_s=60.0) -> float`. Runner imports the same names from `web.server.retry`. Event payload keys (`retry_after_s`, `exception_class`, `reason`) are used consistently across runner.py, the new tests, and the spec.
