# Task 1: Backend — Track `last_check_at` in Schedule Storage

## Task Description

**Files:**
- Modify: `web/server/storage.py` (lines ~589–614)
- Modify: `web/server/app.py` (lines ~141–179)

**Interfaces:**
- Consumes: Existing `indicator_schedule.json` shape `{"interval_ms": 3600000}`
- Produces: Extended shape `{"interval_ms": 3600000, "last_check_at": "2026-06-26T10:00:00Z"}`

## Requirements

### Step 1: Extend `read_indicator_schedule` to include `last_check_at`

In `web/server/storage.py`, update the function to return `last_check_at` (default `None`) from the stored JSON:

```python
def read_indicator_schedule() -> dict:
    """
    Return the indicator check schedule.

    Reads from .env first (TRADINGAGENTS_INDICATOR_CHECK_INTERVAL_MS),
    falls back to notifier.json, then to defaults.
    Returns ``{"interval_ms": 0, "last_check_at": null}``.
    """
    env = _read_env()
    val = os.environ.get(_IND_SCHEDULE_ENV) or env.get(_IND_SCHEDULE_ENV)
    if val:
        return {"interval_ms": int(val), "last_check_at": None}
    path = data_dir() / "indicator_schedule.json"
    payload = read_json(path)
    if payload:
        return {
            "interval_ms": int(payload.get("interval_ms", 0)),
            "last_check_at": payload.get("last_check_at"),
        }
    return {"interval_ms": 0, "last_check_at": None}
```

### Step 2: Extend `write_indicator_schedule` to persist `last_check_at`

```python
def write_indicator_schedule(cfg: dict) -> None:
    """Persist indicator schedule to .env (durable) and JSON (runtime)."""
    interval_ms = int(cfg.get("interval_ms", 0))
    last_check_at = cfg.get("last_check_at")
    _write_env({_IND_SCHEDULE_ENV: str(interval_ms)})
    path = data_dir() / "indicator_schedule.json"
    payload: dict[str, Any] = {"interval_ms": interval_ms}
    if last_check_at is not None:
        payload["last_check_at"] = last_check_at
    write_json_atomic(path, payload)
```

### Step 3: Write the timestamp every time a scheduled check runs

In `web/server/app.py`, in the `_run_indicator_check` function, after the check completes successfully, update `last_check_at`:

```python
# At the end of _run_indicator_check(), after the check logic completes:
try:
    _run_indicator_check()
except Exception:
    log.exception("Indicator background check error")
else:
    # Update last_check_at after a successful run
    current_schedule = storage.read_indicator_schedule()
    if current_schedule.get("interval_ms", 0) > 0:
        current_schedule["last_check_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        storage.write_indicator_schedule(current_schedule)
```

### Step 4: Verify with existing tests

Run: `pytest tests/ -v -k "indicator" --tb=short` (or equivalent)
Expected: PASS (no regressions)

## Report File

Write your full report to: `.superpowers/sdd/task-1-report.md`

After completing, report:
- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- Commits created (short SHA + subject)
- One-line test summary
- The report file path