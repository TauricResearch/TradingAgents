# Inline Indicator Threshold + Countdown Timer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add inline threshold editing to each indicator card and a countdown timer showing time until the next scheduled indicator check, matching the Ticker Accuracy Agent pattern.

**Architecture:** Extend the FastAPI backend to track `last_check_at` in the indicator schedule storage and expose a `PATCH` endpoint for updating thresholds. Update the frontend indicator rail to render editable threshold inputs and a real-time countdown using the existing schedule data.

**Tech Stack:** FastAPI (Python), React + TanStack Query + Tailwind CSS (TypeScript), JSON file storage.

## Global Constraints
- Follow existing code style (black/ruff formatting, 4-space indent).
- No new dependencies.
- Maintain backward compatibility: `indicator_schedule.json` must gracefully handle missing `last_check_at`.
- Countdown must match the Ticker Agent Drawer pattern.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `web/server/storage.py` | Modify | Add `last_check_at` read/write to indicator schedule |
| `web/server/app.py` | Modify | Add `PATCH /api/indicators/{indicator_id}` endpoint; update schedule endpoint to include `last_check_at` |
| `web/server/indicators.py` | Modify | Add `update_indicator(indicator_id, body)` function to mutate threshold in stored indicators |
| `web/frontend/src/lib/api.ts` | Modify | Add `updateIndicator(id, body)` fetcher |
| `web/frontend/src/components/IndicatorRailView.tsx` | Modify | Inline threshold `<input>` on click; countdown `useEffect` below schedule selector |

---

## Task 1: Backend — Track `last_check_at` in Schedule Storage

**Files:**
- Modify: `web/server/storage.py` (lines ~589–614)

**Interfaces:**
- Consumes: Existing `indicator_schedule.json` shape `{"interval_ms": 3600000}`
- Produces: Extended shape `{"interval_ms": 3600000, "last_check_at": "2026-06-26T10:00:00Z"}`

- [ ] **Step 1: Extend `read_indicator_schedule` to include `last_check_at`**

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

- [ ] **Step 2: Extend `write_indicator_schedule` to persist `last_check_at`**

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

- [ ] **Step 3: Write the timestamp every time a scheduled check runs**

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

- [ ] **Step 4: Verify with existing tests**

Run: `pytest tests/ -v -k "indicator" --tb=short` (or equivalent)
Expected: PASS (no regressions)

---

## Task 2: Backend — Add `PATCH /api/indicators/{indicator_id}` Endpoint

**Files:**
- Modify: `web/server/indicators.py`
- Modify: `web/server/app.py`

**Interfaces:**
- Consumes: Existing `read_indicators()` and `write_indicators()`
- Produces: New `update_indicator(indicator_id, body)` function

- [ ] **Step 1: Add `update_indicator` in `indicators.py`**

Add this function to `indicators.py` after `remove_indicator`:

```python
def update_indicator(indicator_id: str, body: dict[str, Any]) -> IndicatorDefinition | None:
    rows = read_indicators()
    for i, row in enumerate(rows):
        if row.id == indicator_id:
            new_threshold = body.get("threshold")
            if new_threshold is not None:
                try:
                    new_threshold = float(new_threshold)
                except (TypeError, ValueError):
                    raise ValueError("threshold must be a number") from None
            new_enabled = body.get("enabled")
            if new_enabled is not None:
                new_enabled = bool(new_enabled)
            rows[i] = IndicatorDefinition(
                id=row.id,
                kind=row.kind,
                name=row.name,
                description=row.description,
                threshold=new_threshold if new_threshold is not None else row.threshold,
                comparator=row.comparator,
                unit=row.unit,
                enabled=new_enabled if new_enabled is not None else row.enabled,
                source=row.source,
            )
            write_indicators(rows)
            return rows[i]
    return None
```

- [ ] **Step 2: Register the PATCH endpoint in `app.py`**

Add after the existing `DELETE /api/indicators/{indicator_id}` endpoint:

```python
@app.patch("/api/indicators/{indicator_id}")
def patch_indicator(indicator_id: str, body: dict) -> dict:
    try:
        updated = indicators.update_indicator(indicator_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="indicator not found")
    return indicators._definition_to_dict(updated)
```

- [ ] **Step 3: Verify with a curl command**

```bash
curl -X PATCH http://localhost:8000/api/indicators/vix \
  -H "Content-Type: application/json" \
  -d '{"threshold": 25.0}'
```
Expected: `200` with indicator JSON including `"threshold": 25.0`

---

## Task 3: Backend — Verify Schedule Endpoint Includes `last_check_at`

**Files:**
- Modify: `web/server/app.py` (lines ~439–440)

- [ ] **Step 1: Confirm `GET /api/indicators/schedule` returns `last_check_at`**

The `read_indicator_schedule` already returns the extended shape. Verify the endpoint just passes through:

```bash
curl http://localhost:8000/api/indicators/schedule
```
Expected: `{"interval_ms": 3600000, "last_check_at": "2026-06-26T10:00:00Z"}` (or `null` if never run)

---

## Task 4: Frontend — Add `updateIndicator` API Fetcher

**Files:**
- Modify: `web/frontend/src/lib/api.ts`

- [ ] **Step 1: Add the `updateIndicator` function**

Add after the `removeIndicator` function (~line 221):

```typescript
export async function updateIndicator(
  id: string,
  body: Partial<{ threshold: number; enabled: boolean }>
): Promise<IndicatorDefinition> {
  const r = await fetch(`${base}/api/indicators/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new ApiError(`update-indicator ${r.status}`, r.status, await readJsonOrNull(r));
  return r.json();
}
```

- [ ] **Step 2: Verify TypeScript compilation**

Run: `cd web/frontend && npx tsc --noEmit`
Expected: No errors related to the new function

---

## Task 5: Frontend — Inline Threshold Editing in Indicator Cards

**Files:**
- Modify: `web/frontend/src/components/IndicatorRailView.tsx`

- [ ] **Step 1: Import `updateIndicator`**

In the import from `../lib/api`, add `updateIndicator` (keep existing imports).

- [ ] **Step 2: Add per-indicator edit state**

Add after the existing state declarations (~line 55):

```typescript
const [editingId, setEditingId] = useState<string | null>(null);
const [editValue, setEditValue] = useState<string>("");
```

- [ ] **Step 3: Add `useMutation` for updates**

Add after the existing `removeMutation`:

```typescript
const updateMutation = useMutation({
  mutationFn: ({ id, body }: { id: string; body: { threshold?: number; enabled?: boolean } }) =>
    updateIndicator(id, body),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["indicators"] });
    setReply("Threshold updated.");
  },
  onError: (err: Error) => {
    const apiErr = err as { detail?: string };
    setReply(apiErr.detail || err.message);
  },
});
```

- [ ] **Step 4: Replace static threshold badge with editable input**

In the indicators map (~line 351), find:

```jsx
<span className="rounded border border-slate-700/60 bg-slate-900/40 px-1.5 py-0.5">
  {indicator.comparator} {formatThreshold(indicator)}
</span>
```

Replace with:

```jsx
{editingId === indicator.id ? (
  <input
    type="number"
    value={editValue}
    onChange={(e) => setEditValue(e.target.value)}
    onBlur={() => {
      const newThreshold = parseFloat(editValue);
      if (!isNaN(newThreshold)) {
        updateMutation.mutate({ id: indicator.id, body: { threshold: newThreshold } });
      }
      setEditingId(null);
    }}
    onKeyDown={(e) => {
      if (e.key === "Enter") {
        const newThreshold = parseFloat(editValue);
        if (!isNaN(newThreshold)) {
          updateMutation.mutate({ id: indicator.id, body: { threshold: newThreshold } });
        }
        setEditingId(null);
      } else if (e.key === "Escape") {
        setEditingId(null);
      }
    }}
    autoFocus
    className="w-20 rounded border border-sky-500 bg-slate-900 px-1.5 py-0.5 text-xs text-sky-300 outline-none"
  />
) : (
  <span
    onClick={() => {
      setEditingId(indicator.id);
      setEditValue(indicator.threshold.toString());
    }}
    className="cursor-pointer rounded border border-slate-700/60 bg-slate-900/40 px-1.5 py-0.5 text-xs text-slate-300 hover:border-slate-500"
  >
    {indicator.comparator} {formatThreshold(indicator)}
  </span>
)}
```

- [ ] **Step 5: Verify with build**

Run: `cd web/frontend && npm run build` (or equivalent)
Expected: Clean build with no TypeScript errors

---

## Task 6: Frontend — Countdown Timer for Next Indicator Check

**Files:**
- Modify: `web/frontend/src/components/IndicatorRailView.tsx`

- [ ] **Step 1: Update the countdown `useEffect` to use `last_check_at`**

Replace the existing countdown `useEffect` (lines 127–147) with:

```typescript
useEffect(() => {
  const intervalMs = scheduleQuery.data?.interval_ms;
  const lastCheckAt = scheduleQuery.data?.last_check_at;
  if (!intervalMs || intervalMs === 0) {
    setCountdown("");
    return;
  }
  const tick = () => {
    if (!lastCheckAt) {
      setCountdown("waiting...");
      return;
    }
    const nextCheck = new Date(lastCheckAt).getTime() + intervalMs;
    const diff = nextCheck - Date.now();
    if (diff <= 0) {
      setCountdown("now");
      return;
    }
    const h = Math.floor(diff / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    const s = Math.floor((diff % 60000) / 1000);
    setCountdown(h > 0 ? `${h}h ${m}m ${s}s` : `${m}m ${s}s`);
  };
  tick();
  const id = setInterval(tick, 1000);
  return () => clearInterval(id);
}, [scheduleQuery.data]);
```

- [ ] **Step 2: Add countdown display below the schedule dropdown**

Find the schedule area in the JSX (~line 261), after the `<button type="button" onClick={() => checksMutation.mutate()}>` button, add:

```jsx
{countdown && (
  <span className="ml-2 text-[10px] text-slate-500">
    Next check in: <span className={`font-mono ${countdown === "now" ? "text-emerald-400" : "text-sky-400"}`}>{countdown}</span>
  </span>
)}
```

- [ ] **Step 3: Verify behavior**

Start the dev server and confirm:
1. Countdown shows "Next check in: 42m 15s" when schedule is active
2. Countdown shows "now" when interval has elapsed
3. Countdown shows "waiting..." when `last_check_at` is null

---

## Task 7: Integration Verification

- [ ] **Step 1: Full-stack smoke test**

1. Start the backend: `uv run python -m web.server.app` (or existing startup method)
2. Start the frontend: `cd web/frontend && npm run dev`
3. Open the dashboard, navigate to the Indicators rail
4. Verify the countdown appears below the schedule dropdown
5. Click a threshold badge, change the value, press Enter
6. Verify the indicator updates in the list

---

## Spec Coverage Check
- [x] Inline threshold editing → Task 5
- [x] Countdown timer → Task 6
- [x] Backend PATCH endpoint → Task 2
- [x] `last_check_at` tracking → Task 1
- [x] Frontend API update → Task 4
- [x] `last_check_at` in schedule response → Task 3

## Self-Review
- No placeholders (all code is concrete)
- All file paths are exact with line numbers where relevant
- Task boundaries are clean — each task is independently testable
- Type signatures match between frontend and backend

---

**Plan complete.** Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**