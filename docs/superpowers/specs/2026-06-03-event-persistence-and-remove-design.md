# Event Persistence Across Refresh + Watchlist Removal — Design

**Date:** 2026-06-03
**Status:** Draft (pending user review of this doc)
**Scope:** Restore the event buffer from the server on page load so a refresh no longer wipes the user's view of the focused ticker's last run, and add a "remove" affordance to the watchlist rail.

## 1. Problem

Two related UX gaps in the dashboard:

1. **Refresh wipes the live view.** `useUi.eventBuffer` (the source of the `LiveEventStream` and the basis for the `DecisionPanel` lookup) is empty after a page refresh, so the user sees "No events yet. Click 'Run analysis' to start." even though the server still has the full run history in the `Event` table. `lastRunIdByTicker` *is* persisted in localStorage, and the events *are* persisted on the server — the wire between them is missing.

2. **No way to remove a ticker from the rail.** The backend `DELETE /api/watchlist/{ticker}` endpoint and the frontend `removeFromWatchlist()` helper in `api.ts:44-47` both exist, but no component calls them. The only way to clean up the rail today is to delete rows from the SQLite file directly.

The watchlist itself is already persisted server-side (`Watchlist` table) and re-ordered by `added_at` on every list call, so the "watchlist in order to restore it" half of the user's request is already met by the existing `GET /api/watchlist` endpoint and the existing `useQuery({ queryKey: ["watchlist"], queryFn: fetchWatchlist })` in `App.tsx:22-25`. This design does not change the watchlist's persistence model.

## 2. Goals & non-goals

**Goals**
- On hydration (and on every focused-ticker change), fetch the focused ticker's last run's events from `GET /api/runs/{id}` and seed `eventBuffer` so the user sees the full event log immediately after a refresh.
- If the last run is still active (`status` is `running` or `queued`), skip the HTTP fetch — the existing `useRunStream` opens a WS at `/ws/runs/{id}?since=0` which replays the same events then continues streaming. This avoids a duplicate fetch for the common "refresh during a live run" case.
- If the persisted run id is stale (404), silently clear the stale pointer so the next focus doesn't repeat the failing fetch.
- Add a remove button to each `TickerRow` with a per-row inline confirm step ("Remove NVDA? [Remove] [Cancel]"). On confirm: delete from server, invalidate the watchlist query, clean up the persisted `lastRunIdByTicker`, and if the removed ticker was focused, focus the next ticker in the rail (or fall through to the empty state if the rail is now empty).
- Keep the backend unchanged — all required endpoints already exist.

**Non-goals**
- Persisting `eventBuffer` to localStorage. The deliberate comment at `ui.ts:50-55` explains the perf cost; the server is the source of truth and the per-ticker `lastRunIdByTicker` pointer is the small piece that survives.
- Eagerly restoring events for *every* ticker in the watchlist on load (would be wasteful for users with many tickers). The restore is lazy: only the focused ticker is fetched until the user clicks a different one.
- Bulk operations (multi-select delete, clear-all, etc.). YAGNI for now.
- Confirmation of the action's destructive side effects (cancellation of any in-progress run for the removed ticker). The DELETE endpoint does not cascade to `Run` rows, so past runs remain queryable via the History drawer even after a ticker is removed.

## 3. Architecture

One new hook, three small changes to existing files, two new store actions. No backend changes.

```
web/frontend/src/hooks/useRestoredRunEvents.ts   NEW   fetches /api/runs/{lastRunId} and dispatches
web/frontend/src/store/ui.ts                     EDIT  add restoreEvents(runId, events); clearLastRunIdForTicker(t)
web/frontend/src/components/TickerRow.tsx        EDIT  add remove button + per-row pending state
web/frontend/src/components/WatchlistRail.tsx    EDIT  wire remove flow, focus-shift on removal
web/frontend/src/App.tsx                         EDIT  call useRestoredRunEvents(focused)
```

**Why a new hook, not a query in `App.tsx`:** the restore action is small and tightly coupled to the focused-ticker + `lastRunIdByTicker` pair, both of which are store state. A dedicated hook isolates the data flow and makes the App component easier to read. It also reuses the same TanStack Query instance the rest of the app already runs.

**Why not just rely on `useRunStream`'s WS replay for *all* runs:** the WS path is conditional on a `runId` being present in `activeRunIdByTicker`, which is only set for currently-running streams. A finished run is not in `activeRunIdByTicker`, so there is no WS to open. The HTTP path is the only way to reconstruct a finished run's events client-side.

## 4. `useRestoredRunEvents` — public API

`web/frontend/src/hooks/useRestoredRunEvents.ts`:

```ts
import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { useUi } from "../store/ui";
import { fetchRunDetail, type RunDetail } from "../lib/api";

/**
 * On every change to `focused`, fetch the focused ticker's last run
 * from the server and seed the store's event buffer with its events.
 *
 * If the run is still active (status === "running" or "queued"), the
 * useRunStream WS will replay the same events; skip the HTTP fetch in
 * that case so we don't double-load.
 *
 * If the persisted run id is stale (404), clear the stale pointer
 * so the next focus doesn't re-trigger the failing fetch.
 */
export function useRestoredRunEvents(focused: string | null): void {
  const lastRunId = useUi((s) => (focused ? s.lastRunIdByTicker[focused] ?? null : null));
  const restoreEvents = useUi((s) => s.restoreEvents);
  const clearLast = useUi((s) => s.clearLastRunIdForTicker);
  const lastFetchedRunIdRef = useRef<number | null>(null);

  const { data } = useQuery<RunDetail | null>({
    queryKey: ["run-detail", focused, lastRunId],
    queryFn: async () => {
      if (focused == null || lastRunId == null) return null;
      try {
        return await fetchRunDetail(lastRunId);
      } catch (e) {
        if (e instanceof Error && /run 404/.test(e.message)) {
          clearLast(focused);
          return null;
        }
        throw e;
      }
    },
    enabled: focused != null && lastRunId != null,
    staleTime: Infinity,
  });

  useEffect(() => {
    if (!data || !focused) return;
    // Skip the restore for active runs — useRunStream's WS will replay.
    if (data.run.status === "running" || data.run.status === "queued") return;
    // Avoid re-dispatching the same run's events if the hook re-runs
    // for an unrelated reason (parent re-render, query refetch, etc.).
    if (lastFetchedRunIdRef.current === data.run.id) return;
    lastFetchedRunIdRef.current = data.run.id;
    restoreEvents(data.run.id, data.events);
  }, [data, focused, restoreEvents]);
}
```

**Why `staleTime: Infinity`:** the persisted `lastRunId` for a finished run doesn't change unless the user starts a new run, which the existing `setLastRunIdForTicker` action handles. Refetching a finished run on every focus change would be wasteful and would risk overwriting a fresh live stream's events with stale data.

**Why the `lastFetchedRunIdRef` dedupe:** TanStack Query may re-emit the cached `data` on parent re-renders. The ref ensures we only dispatch into the buffer once per run id.

## 5. `useUi` store changes

Two new actions on `UiState`:

```ts
// New: replace the buffer with the events of a single historical run.
// Used by useRestoredRunEvents on hydration / focus change. Distinct
// from appendEvent (which is for live streaming) because restoring
// shouldn't mix with in-flight WS appends.
restoreEvents: (runId: number, events: WsEvent[]) => void;

// New: drop the persisted pointer to a ticker's last run. Called when
// the server returns 404 (stale id) and when a ticker is removed from
// the watchlist.
clearLastRunIdForTicker: (ticker: string) => void;
```

Implementations:

```ts
restoreEvents: (runId, events) => set((s) => {
  // Replace any events for the same run id; preserve events from
  // other runs that may be streaming in the same global buffer.
  const others = s.eventBuffer.filter((e) => e.run_id !== runId);
  const restored = events.map((e) => ({ ...e, run_id: runId }));
  return { eventBuffer: [...others, ...restored].slice(-1000) };
}),

clearLastRunIdForTicker: (ticker) => set((s) => {
  const next = { ...s.lastRunIdByTicker };
  delete next[ticker];
  return { lastRunIdByTicker: next };
}),
```

`restoreEvents` is intentionally **not** persisted (`partialize` already excludes `eventBuffer`; the existing comment about main-thread cost remains accurate). The action is also not in `partialize` because `eventBuffer` itself is the omitted field.

`clearLastRunIdForTicker` is naturally persisted — `lastRunIdByTicker` is in `partialize`, and `delete next[ticker]` is the same in-place mutation the existing `setLastRunIdForTicker` action performs.

## 6. `TickerRow` — remove button

`web/frontend/src/components/TickerRow.tsx` gets a remove button and a per-row `pending` state:

```tsx
const [pending, setPending] = useState(false);

// ...

return (
  <div className={`group relative flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-slate-50 ${
    isFocused ? "bg-blue-50 ring-1 ring-blue-200" : ""
  }`}>
    <button
      onClick={() => setFocused(ticker)}
      className="flex-1 flex items-center gap-3 text-left"
    >
      {/* ... existing row content (dot, ticker, company, sparkline) ... */}
    </button>
    {!pending ? (
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); setPending(true); }}
        aria-label={`Remove ${ticker} from watchlist`}
        className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-rose-600 text-sm px-1"
      >
        ×
      </button>
    ) : (
      <span className="flex items-center gap-1 text-xs">
        <button
          type="button"
          onClick={async (e) => { e.stopPropagation(); await onRemove?.(ticker); }}
          className="text-rose-600 hover:underline"
        >Remove</button>
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); setPending(false); }}
          className="text-slate-500 hover:underline"
        >Cancel</button>
      </span>
    )}
  </div>
);
```

- The `×` button is `opacity-0` by default and `group-hover:opacity-100` so the rail stays clean. The full inline confirm appears on click. No new component file.
- Both buttons `stopPropagation` so clicking them does not also focus the ticker.
- The row's outer click-to-focus is now on a child `<button>` so the click target is unchanged for screen-reader / keyboard users — the row stays a single focusable element.

## 7. `WatchlistRail` — remove flow

`web/frontend/src/components/WatchlistRail.tsx` orchestrates the actual delete and the focus-shift:

```tsx
const qc = useQueryClient();
const focused = useUi((s) => s.focusedTicker);
const setFocused = useUi((s) => s.setFocusedTicker);
const clearLast = useUi((s) => s.clearLastRunIdForTicker);

const handleRemove = useCallback(async (ticker: string) => {
  try {
    await removeFromWatchlist(ticker);
  } catch {
    // Re-throw? Toast? For now: silent fail matches existing addToWatchlist
    // (it surfaces an error string but no global toast system). The
    // invalidateQueries call below will at least re-render the rail.
    return;
  }
  clearLast(ticker);
  qc.invalidateQueries({ queryKey: ["watchlist"] });
  if (focused === ticker) {
    const next = watchlist.find((w) => w.ticker !== ticker);
    setFocused(next ? next.ticker : null);
  }
}, [focused, watchlist, qc, clearLast, setFocused]);

return (
  <aside>
    {/* ... */}
    {watchlist.map((row) => (
      <TickerRow
        key={row.ticker}
        {...row}
        onRemove={handleRemove}
        /* ... */
      />
    ))}
  </aside>
);
```

A real toast/undo layer is out of scope; the user-confirm step on the row itself is the safety net.

## 8. `App.tsx` — wire the hook

A single line at the top of `App()`:

```tsx
useRestoredRunEvents(focused);
```

This runs alongside the existing `useRunStream(runId)` so:
- For a **finished** run: `useRestoredRunEvents` fetches the events, `useRunStream` is a no-op (no active run id for a finished run).
- For an **active** run: `useRestoredRunEvents` sees `status === "running"`, skips the fetch; `useRunStream` opens the WS and replays from id=0, then continues streaming.
- For a **no-such-run** persisted id: `useRestoredRunEvents` clears the stale pointer and the empty state remains.

## 9. Data flow

```
Hydration (zustand persist reads localStorage)
  → focusedTicker, lastRunIdByTicker are restored; eventBuffer is empty
  → App renders; useRestoredRunEvents(focused) fires
    → if focused has a lastRunId, useQuery fetches /api/runs/{id}
      → on success, restoreEvents(runId, events) replaces buffer
        → LiveEventStream shows the full event history
        → DecisionPanel finds the decision event and renders
      → on 404, clearLastRunIdForTicker(focused) drops the stale id
    → if the run is active, skip — useRunStream's WS does the replay

User clicks another ticker
  → setFocusedTicker(other) — already in store
  → useRestoredRunEvents(other) fires the same flow for the new ticker
  → restoreEvents merges: events from the old focused ticker are
    replaced by events from the new one (others in the global buffer
    from concurrent runs are preserved by the runId filter)
```

## 10. Testing

### 10.1 `web/frontend/src/__tests__/store-ui.test.ts` (extend)

Three new tests for the store actions:

- `restoreEvents replaces existing events for the same runId`:
  - Seed buffer with two events for run 42; call `restoreEvents(42, [evt_a, evt_b, evt_c])`; assert buffer length is 3 and the new events all have `run_id: 42`.
- `restoreEvents preserves events from other runs`:
  - Seed buffer with `[evt(run 1), evt(run 2)]`; call `restoreEvents(1, [new_evt(run 1)])`; assert the run-2 event is still present.
- `restoreEvents respects the 1000-event cap`:
  - Seed buffer with 998 events of various run ids; call `restoreEvents(99, [500 events])`; assert final length is 1000 (the 500 restored are kept, the 498 oldest from other runs are dropped).
- `clearLastRunIdForTicker drops only the named key`:
  - Seed `lastRunIdByTicker: { AAPL: 42, NVDA: 99 }`; call `clearLastRunIdForTicker("AAPL")`; assert result is `{ NVDA: 99 }`.

### 10.2 `web/frontend/src/__tests__/useRestoredRunEvents.test.ts` (new)

Hook tests using `@testing-library/react`'s `renderHook`:

- `hydrates event buffer from /api/runs/{id} on mount`:
  - Seed store with `focusedTicker: "NVDA", lastRunIdByTicker: { NVDA: 7 }`.
  - Mock `fetch` to return `{ run: {id: 7, status: "done"}, events: [...] }`.
  - Assert `eventBuffer` ends up containing the server's events for run 7.
- `skips the fetch for active runs`:
  - Same seed, mock `fetch` to return `{ run: {id: 7, status: "running"}, events: [...] }`.
  - Assert `eventBuffer` is empty (no fetch, or fetch discarded).
- `clears the stale run id on 404`:
  - Same seed, mock `fetch` to return 404.
  - Assert `lastRunIdByTicker.NVDA` is `null` after the hook settles.
- `refetches when focused changes`:
  - Seed store with two tickers. Render, change focus, assert the new ticker's events are in the buffer.

### 10.3 `web/frontend/src/__tests__/App.test.tsx` (extend)

Add one integration test:

- `App.test.tsx > restores past events into the buffer on mount`:
  - Mock `fetch` for `/api/watchlist` (returns `[{ ticker: "NVDA", ... }]`) and `/api/runs/7` (returns `{ run: {id: 7, status: "done"}, events: [...] }`).
  - Pre-seed `useUi` with `focusedTicker: "NVDA", lastRunIdByTicker: { NVDA: 7 }`.
  - Render `<App />`, await the events to land, assert the `LiveEventStream` bubble for the seeded event is in the document.

### 10.4 `web/frontend/src/__tests__/WatchlistRail.test.tsx` (extend)

Four new tests:

- `clicking the X shows the inline confirm; Cancel hides it`:
  - Render with two rows; click the X on NVDA; assert "Remove" and "Cancel" appear; click Cancel; assert they're gone.
- `clicking Remove calls the API and invalidates the watchlist query`:
  - Mock `fetch` to spy on the DELETE call. Click X then Remove. Assert fetch was called with `method: "DELETE"` and the right URL. Assert the watchlist query is invalidated (next refetch returns the post-delete list).
- `removing the focused ticker focuses the next row`:
  - Seed focusedTicker = "NVDA"; click X then Remove on NVDA; assert focusedTicker becomes "AAPL".
- `removing the last ticker clears focus`:
  - Seed focusedTicker = "NVDA" with only NVDA in the watchlist; click X then Remove on NVDA; assert focusedTicker is `null` and the empty-state text appears.

## 11. Rollout & risk

- **No backend changes.** The DELETE endpoint, the GET /api/runs/{id} endpoint, the Event table, and the `last_run_id` column on Watchlist all already exist.
- **No new dependencies.** TanStack Query and zustand are already in the bundle.
- **Backwards compatibility:** `restoreEvents` and `clearLastRunIdForTicker` are additive store actions; existing code paths (`appendEvent`, `setLastRunIdForTicker`) are untouched. `TickerRow` adds a child element so the parent's layout is unchanged.
- **Risk: a busy server or a long past run could return a large event payload.** A 1000-event payload is ~100-200 KB of JSON; well within what TanStack Query and the buffer cap can handle. The 1000-event cap in `restoreEvents` is the same one `appendEvent` already uses, so the existing memory bounds hold.
- **Risk: re-dispatching the same run's events on every focus change.** Mitigated by the `lastFetchedRunIdRef` dedupe in the hook.
- **Risk: the 404 path clears a valid pointer if the server is briefly unavailable.** Acceptable — the user is no worse off than today (no auto-restore), and the next valid `setLastRunIdForTicker` call (a new run starting) will repopulate the pointer.

## 12. Open questions

None. The four questions raised in brainstorming (restoration trigger, active-run handling, remove confirmation, focus on removal) were answered by the user.
