---
type: decision
status: active
date: 2026-03-17
agent_author: "claude"
tags: [rate-limiting, alpha-vantage, threading]
related_files: [tradingagents/dataflows/alpha_vantage_common.py]
---

## Context

The Alpha Vantage rate limiter initially slept *inside* the lock when re-checking the rate window. This blocked all other threads from making API requests during the sleep period, serializing all AV calls.

## The Decision

Two-phase rate limiting:
1. Acquire lock, check timestamps, release lock, sleep if needed.
2. Re-check loop: acquire lock, re-check. If still over limit, release lock *before* sleeping, then retry. Only append timestamp and break when under the limit.

```python
while True:
    with _rate_lock:
        if len(_call_timestamps) < _RATE_LIMIT:
            _call_timestamps.append(_time.time())
            break
        extra_sleep = 60 - (now - _call_timestamps[0]) + 0.1
    _time.sleep(extra_sleep)  # outside lock
```

## Constraints

- Lock must never be held during `sleep()` or IO operations.

## Actionable Rules

- Never hold a lock during a sleep/IO operation. Always release, sleep, re-acquire.
