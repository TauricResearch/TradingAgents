# Dashboard Real-Time View: Server Event Protocol, Per-Ticker Filtering, Refresh Persistence, and Watchlist Removal

**Date:** 2026-06-03
**Status:** Draft (pending user review of this doc)
**Scope:** Make the dashboard match the protocol its UI was already designed for. Today the server emits only ~6 of the 14 declared event types in production, so the dashboard's `LiveEventStream` is sparse, `StageGrid` stages never mark "done", `DecisionPanel` shows another ticker's decision when the buffer mixes runs, and the logs don't change on ticker switch. Additionally, refresh wipes the event buffer (no auto-restore from the server) and there's no way to remove a ticker from the rail.

## 1. Problem

Four related UX gaps that all trace back to a single root cause: the **server-side event protocol is mostly aspirational**, and the display components were built for the full protocol but never got the events to render.

| # | Symptom | Root cause |
|---|---------|-----------|
| 1 | `StageGrid` shows every stage as "running…" forever (e.g. Market is always running) | The server never emits `analyst_completed` events; `statusFor` looks for `data.stage === key` with no fallback to "done" when missing |
| 2 | `LiveEventStream` is sparse — only `analyst_started: Market Analyst` and `analyst_started: tools_market` show, no reasoning, no tool calls, no debate, no decision | The runner discards the rich per-node delta at `trading_graph.py:483/503`; no `BaseCallbackHandler` is attached server-side; the CLI's `StatsCallbackHandler` (`cli/stats_handler.py`) is the only one in the repo |
| 3 | Logs don't change on ticker switch | `LiveEventStream` and `StageGrid` both render the unfiltered global `eventBuffer`; `App.tsx:44-45` looks for the first `decision` event regardless of `run_id`; the store comment at `ui.ts:50-55` notes "events are already tagged with `run_id` by the server" but no display component actually filters on it |
| 4 | `run_finished` is sent with `duration_s: 0` (a placeholder) and no report summary | `runner.py:186` is a stub; the real `final_state` is in scope but discarded |

| 7 | Watchlist shows `+0.00%` for the change_pct on every ticker, even during market hours | `price_feed.py:32-77` sends `change_pct: snap.change_pct` in every `price_update` event, but `snap.change_pct` is the dataclass default (`0.0`, `price_feed.py:21`) and is never assigned. The price value itself updates correctly (the sparkline moves), but the percent change is permanently `0.0`. |

Plus two orthogonal issues from earlier brainstorming:

| # | Symptom | Root cause |
|---|---------|-----------|
| 5 | Refresh wipes the event buffer → "No events yet" | `useUi.eventBuffer` is intentionally not persisted (correctly — 1000 events re-stringified on every WS append dominates the main thread); the persisted `lastRunIdByTicker[focused]` pointer exists but no hook re-fetches from the server on hydration |
| 6 | No way to remove a ticker from the rail | `DELETE /api/watchlist/{ticker}` and `removeFromWatchlist()` (`api.ts:44-47`) both exist; no component calls them |

The watchlist's *order* is already preserved server-side (the `Watchlist` table is ordered by `added_at` on every list call), so the "save in cache … in order to restore it" half of the user's request is already met by the existing `GET /api/watchlist` endpoint and the existing `useQuery({ queryKey: ["watchlist"], queryFn: fetchWatchlist })` in `App.tsx:22-25`. This design does not change the watchlist's persistence model.

**Out of scope of this spec (but related):** the watchlist-on-load empty state the user reported separately. That is a TanStack Query stale-cache issue plus a Vite proxy IPv6 binding mismatch (`localhost` → `::1` while the proxy target is `localhost:8000` which can fail on IPv4-only systems). The uncommitted `vite.config.ts` fix to use `127.0.0.1:8000` resolves the proxy issue; the stale cache clears on hard refresh. No design changes are needed for it.

## 2. Goals & non-goals

**Goals**

- **Server emits the full event protocol in production**, not just the subset it emits today. Specifically, in addition to what already fires (`run_started`, `analyst_started`, `tool_call_warning`, `run_finished`, `run_failed`, `price_update`):
  - `analyst_thinking` — per agent LLM call, with the assembled `prompt` (truncated) and any `tool_calls` returned
  - `analyst_completed` — per agent node, when the node exits, with `{stage, summary, report_excerpt?}`
  - `tool_call` — when a tool is invoked, with `{tool, args}`
  - `tool_result` — when a tool returns, with `{tool, summary, error?}`
  - `debate_message` — per researcher/debator speech, with `{side, text}`
  - `risk_message` — per risk-debate speech, with `{side, text}`
  - `decision` — at the end, with the full `{action, target, rationale, confidence}`
  - `run_finished` with real `duration_s` and a per-analyst summary map
- **Frontend display components filter by `run_id`** so the focused ticker is the only one rendered. `useUi.eventBuffer` stays the global store; a new `useFocusedRunEvents()` hook is the single source of truth for the filtered list.
- **Ticker switch is automatic and instant** — when `focusedTicker` changes, the three display components re-render against the new filter with no flicker because the new ticker's events were restored into the buffer by the existing WS (active run) or the new `useRestoredRunEvents` hook (finished run).
- **On hydration, fetch the focused ticker's last run's events** from `GET /api/runs/{id}` so a refresh no longer wipes the view. Skip the fetch if the run is still active (`useRunStream`'s WS does the replay). Clear the stale pointer on 404.
- **Each `TickerRow` gets a remove button with an inline confirm step.** On confirm: delete from server, invalidate the watchlist query, clean up the persisted `lastRunIdByTicker`, and if the removed ticker was focused, focus the next ticker in the rail (or fall through to empty state).

**Non-goals**

- Per-token LLM streaming. `on_llm_new_token` is **not** wired in this spec — it would bypass the response cache (`cache.py:18` says "Streaming is bypassed — only invoke hits the cache") and adds a 14th event type for marginal UX value. The callback handler design below has a place where a token handler could be slotted in if we revisit this.
- Persisting `eventBuffer` to localStorage. The existing comment at `ui.ts:50-55` is correct; the per-ticker `lastRunIdByTicker` pointer is the small piece that survives.
- Eagerly restoring events for *every* ticker in the watchlist on load. Lazy: only the focused ticker.
- Multi-select delete, undo toasts, or any other watchlist-management UX. The inline confirm is the safety net.
- A new `EventType` member for `LLM_TOKEN`. The enum stays at 14 entries.
- Changes to any agent file (`tradingagents/agents/**/*.py`). All new emissions come from a single `BaseCallbackHandler` in the server path and from the `node_exited` graph callback. No agent rewrite.
- Server-side rate limiting for the new events. They ride the existing WS broadcast (one queue per subscribed client) and DB write paths; the existing throughput bounds apply.

## 3. Architecture

Eight files touched across server and frontend, two new files. The server changes are the biggest impact (six new event types emitted in production); the frontend changes are a small refactor (one new hook, three display components switched to it).

```
web/server/callbacks.py                   NEW   StreamingCallbackHandler (BaseCallbackHandler)
web/server/runner.py                      EDIT  pass [StreamingCallbackHandler()] to build_graph;
                                                 emit decision + real run_finished;
                                                 wire node_exited → analyst_completed
tradingagents/graph/trading_graph.py      EDIT  emit event_callback("node_exited", {node, ts, delta}) after each node's delta is merged

web/frontend/src/hooks/useFocusedRunEvents.ts   NEW   returns the run_id-filtered event list for the focused ticker
web/frontend/src/hooks/useRestoredRunEvents.ts  NEW   (from previous spec) fetches /api/runs/{lastRunId} on hydration
web/frontend/src/store/ui.ts               EDIT  add restoreEvents, clearLastRunIdForTicker (from previous spec)
web/frontend/src/components/LiveEventStream.tsx  EDIT  use useFocusedRunEvents
web/frontend/src/components/StageGrid.tsx       EDIT  use useFocusedRunEvents; map node names → stage keys
web/frontend/src/App.tsx                    EDIT  decision lookup uses useFocusedRunEvents;
                                                 mount useRestoredRunEvents(focused)
web/frontend/src/components/TickerRow.tsx       EDIT  remove button + per-row pending state (from previous spec)
web/frontend/src/components/WatchlistRail.tsx   EDIT  wire remove flow + focus-shift (from previous spec)
```

`web/server/events.py` and `web/frontend/src/lib/events.ts` do **not** change — the 14 event types are already declared on both sides and validated by the `events-protocol.test.ts` test.

**Why a `BaseCallbackHandler` and not a LangGraph `event_callback` for the LLM-side events:** the existing `event_callback` in `trading_graph.py:483/503` only fires for `node_entered` (graph boundary). It cannot see what happens *inside* a node — the LLM call, the tool calls, the LLM response. To get the rich per-step data without rewriting any agent, we attach a LangChain `BaseCallbackHandler` to the chat model via the `callbacks` kwarg that `TradingAgentsGraph.__init__` already supports (`trading_graph.py:67-93, 92-93`); the runner just doesn't pass any today. The handler emits events with `events.emit(run_id, type, data)`, which uses the same wire format and DB persistence as the existing emissions.

**Why one new graph callback (`node_exited`) for `analyst_completed`:** the `BaseCallbackHandler` sees LLM boundaries (`on_llm_end`) but a single agent node may make multiple LLM calls (think: `agent → tool_call → on_tool_end → agent → final text`). The right "node done" signal is the LangGraph node boundary. The `event_callback` bridge in `trading_graph.py:469-509` is the only place that sees graph boundaries; we add a `node_exited` emit symmetric to the existing `node_entered` (one extra `event_callback` call after `final_state.update(...)`).

## 4. Server-side: rich event protocol

### 4.1 `StreamingCallbackHandler` — public API

`web/server/callbacks.py` (new file):

```python
"""LangChain callback handler that bridges per-step LLM/tool activity
into the dashboard's event protocol.

Attach a single instance per run via TradingAgentsGraph(callbacks=[...]).
The handler runs in the thread pool that propagates the graph; all
emissions go through events.emit which already uses
``loop.call_soon_threadsafe`` to reach the asyncio broadcast loop.
"""
from __future__ import annotations

from typing import Any
from langchain_core.callbacks import BaseCallbackHandler
from . import events


class StreamingCallbackHandler(BaseCallbackHandler):
    """Maps LangChain's per-step callbacks to WsEvent payloads.

    The mapping is intentionally narrow — every callback either
    produces exactly one WsEvent or none. We don't try to mirror
    the LangChain callback surface 1:1.
    """

    def __init__(self, run_id: int) -> None:
        self.run_id = run_id

    # ---- LLM -----------------------------------------------------------

    def on_chat_model_start(self, serialized: dict, messages: list, **kw) -> None:
        # Fires before each LLM call inside an agent node. The agent
        # name isn't on the LangChain callback surface (it lives on the
        # LangGraph node), so we let the runner's node_entered event
        # carry the node name; this event just announces "the model is
        # thinking" and surfaces a short prompt preview.
        prompt_preview = _extract_last_user_text(messages)
        events.emit(self.run_id, "analyst_thinking", {
            "text_preview": prompt_preview[:200] if prompt_preview else None,
        })

    def on_llm_end(self, response: Any, **kw) -> None:
        # If the response contains tool_calls, the agent is about to
        # invoke them — those get their own tool_call event in
        # on_tool_start, so we don't double-fire here. Only emit a
        # text fragment for free-text completions.
        for gen in response.generations:
            for chat in gen:
                if chat.message.content and not chat.message.tool_calls:
                    events.emit(self.run_id, "analyst_thinking", {
                        "text_fragment": str(chat.message.content)[:500],
                    })
                    break  # one per LLM call is enough

    # ---- Tools ---------------------------------------------------------

    def on_tool_start(self, serialized: dict, input_str: str, **kw) -> None:
        name = (serialized or {}).get("name", "unknown")
        events.emit(self.run_id, "tool_call", {"tool": name, "args": input_str[:200]})

    def on_tool_end(self, output: str, **kw) -> None:
        # ``output`` may be a ToolMessage object or a string depending on
        # the tool. Coerce defensively and cap the summary length.
        text = str(getattr(output, "content", output) or "")
        events.emit(self.run_id, "tool_result", {
            "tool": getattr(output, "name", "unknown"),
            "summary": text[:200],
        })

    def on_tool_error(self, error: BaseException, **kw) -> None:
        events.emit(self.run_id, "tool_result", {
            "tool": "unknown", "error": str(error), "summary": str(error)[:200],
        })


def _extract_last_user_text(messages: list) -> str | None:
    """Best-effort extraction of the most recent user message text.

    LangChain's on_chat_model_start passes a nested list of message
    lists (one per LLM call inside the agent). The last HumanMessage
    in the last list is the freshest user-authored text. System and
    tool messages are skipped — they're usually noise at this layer.
    """
    try:
        for batch in reversed(messages):
            for msg in reversed(batch):
                if getattr(msg, "type", None) == "human":
                    return str(msg.content)
    except Exception:
        return None
    return None
```

**Why a list of one (not one per node):** a single `StreamingCallbackHandler(run_id)` is enough because the handler holds no per-node state; all state lives in the `events.emit` payload.

**Why no per-token streaming:** token streaming (`on_llm_new_token`) is intentionally not wired — see Goals. The hook signature leaves room for it if we revisit.

### 4.2 `node_exited` — graph-side completion signal

`tradingagents/graph/trading_graph.py` adds a symmetric emit in both branches of the stream loop:

```python
# trading_graph.py:483, 503 — after final_state.update(...) in each branch
if event_callback is not None:
    try:
        event_callback(
            "node_exited",
            {
                "node": next(iter(chunk)),
                "ts": _now_iso(),
                "delta": next(iter(chunk.values())),
            },
        )
    except Exception:
        logger.exception("event_callback raised; continuing")
```

The runner's callback bridge maps `node_exited` to `analyst_completed` with the stage mapping below, using `delta` to extract the report excerpt.

**Stage map (lives in the runner, not the graph):**

| LangGraph node name | Stage key | Report field to excerpt |
|---|---|---|
| `Market Analyst` | `market` | `final_state["market_report"]` |
| `Sentiment Analyst` | `sentiment` | `final_state["sentiment_report"]` |
| `News Analyst` | `news` | `final_state["news_report"]` |
| `Fundamentals Analyst` | `fundamentals` | `final_state["fundamentals_report"]` |
| `Bull Researcher` | `research` | (no individual report; `summary` is the latest bull argument) |
| `Bear Researcher` | `research` | (same) |
| `Research Manager` | `research` | `final_state["investment_plan"]` excerpt |
| `Trader` | `trader` | `final_state["trader_investment_plan"]` excerpt |
| `Aggressive Analyst` | `risk` | (debatable) |
| `Conservative Analyst` | `risk` | (debatable) |
| `Neutral Analyst` | `risk` | (debatable) |
| `Portfolio Manager` | (no analyst_completed; fires `decision` instead) | — |
| `Msg Clear *` and `tools_*` | (no analyst_completed) | — |

**Why Portfolio Manager doesn't fire `analyst_completed`:** it's the terminal node; the meaningful "completion" is the `decision` event we emit from the runner after `propagate()` returns.

**Why tool/clear nodes don't fire `analyst_completed`:** they're sub-nodes of an agent's tool-use loop; firing one would mark the stage "done" prematurely while the agent is still iterating.

### 4.3 Runner wiring

`web/server/runner.py` changes in three places:

1. Pass the handler to the graph:
   ```python
   graph = build_graph(
       run_id=rid,
       callbacks=[StreamingCallbackHandler(run_id=rid)],
   )
   ```
   `build_graph()` either accepts a `callbacks` kwarg and forwards to `TradingAgentsGraph(callbacks=...)` (already supported at `trading_graph.py:67-93`), or we wrap the build step with a small helper. The former is one-line.

2. Update the `cb` bridge (currently `runner.py:115-123`) to also map `node_exited`:
   ```python
   def cb(node_name: str, payload: dict) -> None:
       if db.get_run(rid).cancel_requested:
           raise _CancelSentinel()
       if node_name == "node_entered":
           events.emit(rid, "analyst_started", {"node": payload.get("node", node_name), **payload})
       elif node_name == "node_exited":
           stage, summary, excerpt = _stage_summary_for_node(payload.get("node", ""), payload.get("delta", {}))
           if stage is None:
               return  # tool/clear/portfolio_manager — no completion event
           events.emit(rid, "analyst_completed", {"stage": stage, "summary": summary, "report_excerpt": excerpt})
       else:
           events.emit(rid, node_name, payload)  # passthrough
   ```

3. After `graph.propagate()` returns (and the decision is extracted), emit `decision` and the real `run_finished`:
   ```python
   decision_event = _extract_decision(final)  # action, target, rationale, confidence
   events.emit(rid, "decision", decision_event)
   events.emit(rid, "run_finished", {
       "duration_s": round(time.monotonic() - t_start, 2),
       "summary_by_stage": _summary_by_stage(final),
   })
   ```

The runner also already records `t_start = time.monotonic()` near line 126 in the exploration; we just need to use it.

**Cache caveat (documented, not solved):** because the cache wrapper only instruments `invoke`, `StreamingCallbackHandler.on_chat_model_start` and `on_llm_end` *do not fire on cache hits*. A cache hit produces an `analyst_started` for the node (from `node_entered`) but no `analyst_thinking` events and no `tool_call` / `tool_result` for the cached tool sequence. This is an acceptable trade-off (and one the user already made consciously in the LLM-cache spec): a cache hit is "the same answer as last time, instantly", and the missing thinking events accurately reflect that. A `server_notice` event in the runner — `"cache hit: skipped {n} LLM calls for {node}"` — would be a nice future addition but is not in this spec.

### 4.4 `PriceFeed` — compute `change_pct` from previous close

`web/server/price_feed.py:32-77` currently emits `change_pct: snap.change_pct` where `snap.change_pct` is the dataclass default (`0.0`) and is **never assigned** in the poll loop. The fix is to compute it from the ticker's previous close once per poll, then derive the percent change against the live price.

Change the per-ticker block in `_poll_once` to:

```python
for ticker in tickers:
    snap = state.snapshots.get(ticker) or PriceSnapshot()
    try:
        series = df[ticker]["Close"]
        if hasattr(series, "empty") and series.empty:
            snap.stale = True
        else:
            values = list(series.dropna().tail(30))
            if not values:
                snap.stale = True
            else:
                snap.price = float(values[-1])
                snap.sparkline = [float(v) for v in values]
                snap.stale = False
        # NEW: compute change_pct from the previous trading day's close.
        # yfinance's fast_info has previousClose (the close of the most
        # recent completed session, relative to the current bar). This is
        # the canonical "today's change" denominator. Guard against zero
        # to avoid div-by-zero on newly-listed tickers.
        prev_close = float(
            yf.Ticker(ticker).fast_info.get("previousClose", 0) or 0
        )
        if prev_close > 0 and snap.price > 0 and not snap.stale:
            snap.change_pct = (snap.price - prev_close) / prev_close * 100.0
        else:
            snap.change_pct = 0.0
    except Exception:
        log.exception("price lookup failed for %s; marking stale", ticker)
        snap.stale = True
        snap.change_pct = 0.0
    state.snapshots[ticker] = snap

    if broadcast is not None:
        broadcast(events.make_event(
            "price_update",
            run_id=0,
            data={
                "ticker": ticker,
                "price": snap.price,
                "change_pct": snap.change_pct,   # now real
                "sparkline": snap.sparkline,
                "stale": snap.stale,
            },
        ))
```

**Why `fast_info.previousClose` and not derived from `df`:** `period="1d", interval="1m"` returns today's intraday bars only. Yesterday's close is not in the same response. `fast_info` is a lightweight single-field lookup that yfinance has tuned for this exact access pattern (the CLI uses it elsewhere). It adds N yfinance calls per poll, one per ticker — for a watchlist of 10-20 tickers, that's 10-20 calls every 15 seconds, well within yfinance's published rate limits.

**Why guard against `prev_close == 0`:** newly-listed or split-adjusted tickers can briefly have a `previousClose` of 0 in fast_info. Showing `+inf%` is worse than showing `0.0%`, so we fall back to the latter.

**Why the `not snap.stale` gate:** if the price series was empty, the previous close is not meaningful against a stale price. Reset to 0 so the UI shows a neutral value rather than misleadingly green/red.

## 5. Frontend-side: per-run-id filtering

`useUi.eventBuffer` stays the global store. A new hook is the single source of truth for what the UI should render for the focused ticker.

`web/frontend/src/hooks/useFocusedRunEvents.ts` (new):

```ts
import { useMemo } from "react";
import { useUi } from "../store/ui";
import type { WsEvent } from "../lib/events";

/**
 * Returns the events that belong to the currently-focused ticker's
 * last run. Used by LiveEventStream, StageGrid, and App's decision
 * lookup so they all see the same filtered slice.
 *
 * - If no ticker is focused, returns [].
 * - If the focused ticker has no last run, returns [].
 * - Otherwise returns eventBuffer.filter(e => e.run_id === runId).
 *
 * Memoized on (focused, runId, eventBuffer reference) so the
 * reference is stable across unrelated re-renders.
 */
export function useFocusedRunEvents(): WsEvent[] {
  const focused = useUi((s) => s.focusedTicker);
  const runId = useUi((s) =>
    focused ? s.lastRunIdByTicker[focused] ?? null : null
  );
  const events = useUi((s) => s.eventBuffer);
  return useMemo(() => {
    if (focused == null || runId == null) return [];
    return events.filter((e) => e.run_id === runId);
  }, [focused, runId, events]);
}
```

Three components switch to this hook:

- `LiveEventStream` (lines 19-22): replace `useUi((s) => s.eventBuffer)` with `useFocusedRunEvents()`. The rest of the component is unchanged.
- `StageGrid` (line 24): same swap. Also fix the latent name/key divergence bug noted in the exploration: introduce a `NODE_NAME_TO_STAGE` map so `statusFor` always compares on the stage key, never on a node-name substring.
- `App.tsx:44-45`: replace `[...events].reverse().find(e => e.type === "decision")` with `useFocusedRunEvents()` reversed `.find(...)`. Same logic, scoped to the focused run.

**Why a hook and not a store selector:** the filter is a derivation of `(focused, runId, eventBuffer)`. A hook lets us use `useMemo` to keep the reference stable; a plain store selector recomputes on every store change including non-related events. The hook also gives a stable import name to test against.

## 6. `useRestoredRunEvents` — refresh persistence

Unchanged from the previous design (kept verbatim for clarity). The hook fetches the focused ticker's last finished run on hydration and on every focused-ticker change.

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
        // 404 surfaces as a thrown error from fetchRunDetail. Inspect
        // status via the Response if the api layer exposes it; until
        // then, match on the message.
        if (e instanceof Error && /404/.test(e.message)) {
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
    if (data.run.status === "running" || data.run.status === "queued") return;
    if (lastFetchedRunIdRef.current === data.run.id) return;
    lastFetchedRunIdRef.current = data.run.id;
    restoreEvents(data.run.id, data.events);
  }, [data, focused, restoreEvents]);
}
```

## 7. `useUi` store changes

Two new actions on `UiState` (from the previous design, unchanged):

```ts
restoreEvents: (runId: number, events: WsEvent[]) => void;
clearLastRunIdForTicker: (ticker: string) => void;
```

Implementations:

```ts
restoreEvents: (runId, events) => set((s) => {
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

`restoreEvents` is intentionally not persisted (`partialize` already excludes `eventBuffer`). `clearLastRunIdForTicker` is naturally persisted because `lastRunIdByTicker` is in `partialize`.

## 8. `TickerRow` — remove button

`web/frontend/src/components/TickerRow.tsx` gets a remove button and a per-row `pending` state:

```tsx
const [pending, setPending] = useState(false);

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

## 9. `WatchlistRail` — remove flow

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
    return;  // silent: matches existing addToWatchlist semantics
  }
  clearLast(ticker);
  qc.invalidateQueries({ queryKey: ["watchlist"] });
  if (focused === ticker) {
    const next = watchlist.find((w) => w.ticker !== ticker);
    setFocused(next ? next.ticker : null);
  }
}, [focused, watchlist, qc, clearLast, setFocused]);
```

## 10. `App.tsx` — wire everything

Three small changes to `App.tsx`:

```tsx
// 1. Replace the bare eventBuffer read with the filtered list.
const focusedEvents = useFocusedRunEvents();

// 2. Mount the restoration hook.
useRestoredRunEvents(focused);

// 3. Decision lookup now sees only the focused run.
const decisionEvent = [...focusedEvents].reverse().find((e) => e.type === "decision");
```

`useRunStream(runId)` is unchanged. The end-to-end flow on hydration:

- For a **finished** run: `useRestoredRunEvents` fetches `/api/runs/{id}` → `restoreEvents` seeds the buffer with the rich event list → `useFocusedRunEvents` returns that list → `LiveEventStream`, `StageGrid`, and `DecisionPanel` all render the focused run's events.
- For an **active** run: `useRestoredRunEvents` sees `status === "running"`, skips the fetch → `useRunStream` opens the WS at `/ws/runs/{id}?since=0` → WS replays the same events then continues streaming → the handler's per-step emissions flow through the WS and `appendEvent` populates the buffer.
- For a **stale** id: `useRestoredRunEvents` catches the 404, calls `clearLastRunIdForTicker(focused)`, and the user sees the empty state.

## 11. Data flow

```
Hydration (zustand persist reads localStorage)
  → focusedTicker, lastRunIdByTicker restored; eventBuffer empty
  → App renders
  → useRestoredRunEvents(focused) fires
    → if focused has a lastRunId, useQuery fetches /api/runs/{id}
      → on success, restoreEvents(runId, events) seeds the buffer
      → useFocusedRunEvents returns the new list
        → LiveEventStream shows the focused run's events
        → StageGrid shows per-stage status (now complete with analyst_completed)
        → DecisionPanel finds the decision event
      → on 404, clearLastRunIdForTicker(focused) drops the stale id
    → if the run is active, skip — useRunStream's WS does the replay

Live run
  → useRunStream opens WS to /ws/runs/{runId}?since=0
  → server replays persisted events, then emits new ones as they happen
  → on the server side, the graph's node_entered fires analyst_started;
    StreamingCallbackHandler fires analyst_thinking / tool_call /
    tool_result per LLM and tool boundary;
    the graph's node_exited fires analyst_completed per agent node
  → each WS message is appended to the global eventBuffer
  → useFocusedRunEvents filters and the three components re-render

User clicks another ticker
  → setFocusedTicker(other)
  → useFocusedRunEvents(other) recomputes the filter
  → if the other ticker has a finished run, useRestoredRunEvents fires
    a new useQuery for /api/runs/{other.lastRunId} and seeds the buffer
  → if the other ticker is active, useRunStream was already streaming;
    the WS appends into the buffer
  → components re-render against the new focused run
```

## 12. Testing

### 12.1 Server-side: `web/server/tests/test_price_feed.py` (extend)

- `test_change_pct_is_computed_from_previous_close`:
  - Mock `yf.Ticker(...).fast_info.get("previousClose", 0)` to return `100.0`; set the intraday series so the last value is `103.0`. Call `_poll_once`; assert the broadcast event has `change_pct ≈ 3.0`.
- `test_change_pct_is_zero_when_previous_close_is_zero`:
  - Mock `fast_info.get("previousClose", 0)` to return `0`. Assert the event has `change_pct == 0.0` (not `inf` or `NaN`).
- `test_change_pct_is_zero_when_price_series_is_empty`:
  - Mock an empty intraday series. Assert `stale == True` and `change_pct == 0.0`.
- `test_change_pct_is_zero_for_negative_change`:
  - Mock `previousClose=100`, last price `97.0`. Assert `change_pct ≈ -3.0`.
- `test_price_update_event_uses_real_change_pct_not_default`:
  - This is the regression test for the original bug. Run `_poll_once` with a known previous close and a known last price; assert the broadcast event's `data.change_pct` is the computed value, NOT the dataclass default `0.0`.

### 12.2 Server-side: `web/server/tests/test_callbacks.py` (new)

- `test_on_chat_model_start_emits_analyst_thinking`:
  - Build handler; call `on_chat_model_start({"name": "ChatOpenAI"}, [[HumanMessage(content="What's the price?")]])`; assert one `analyst_thinking` event with `text_preview == "What's the price?"`.
- `test_on_chat_model_start_truncates_long_prompts`:
  - Same with a 1000-char message; assert `text_preview` is ≤ 200 chars.
- `test_on_llm_end_emits_analyst_thinking_for_text_response`:
  - Build a synthetic `LLMResult` with a free-text generation; call `on_llm_end`; assert `analyst_thinking` with `text_fragment` fires.
- `test_on_llm_end_skips_when_response_has_tool_calls`:
  - Build a synthetic result with `tool_calls` set; assert no `analyst_thinking` fires (the `tool_call` event will fire in `on_tool_start` instead).
- `test_on_tool_start_emits_tool_call`:
  - Call `on_tool_start({"name": "get_stock_data"}, '{"ticker": "NVDA"}')`; assert `tool_call` event with `tool == "get_stock_data"`, `args == '{"ticker": "NVDA"}'`.
- `test_on_tool_end_emits_tool_result`:
  - Call `on_tool_end("some text output")`; assert `tool_result` event with `summary == "some text output"` (truncated as needed).
- `test_on_tool_error_emits_tool_result_with_error`:
  - Call `on_tool_error(ValueError("bad arg"))`; assert `tool_result` with `error` set and a non-empty `summary`.

### 12.2 Server-side: `web/server/tests/test_runner.py` (extend)

- `test_node_exited_emits_analyst_completed_for_agent_nodes`:
  - Use the existing fake graph; have the script emit `node_exited` for `Market Analyst`; assert `analyst_completed` is persisted with `data.stage == "market"`.
- `test_node_exited_skips_completion_for_tool_and_clear_nodes`:
  - Same, but emit `node_exited` for `tools_market`; assert no `analyst_completed` event is persisted.
- `test_node_exited_skips_completion_for_portfolio_manager`:
  - Same, but for `Portfolio Manager`; assert no `analyst_completed` (the `decision` event is what the runner fires).
- `test_run_finished_uses_real_duration_and_summary_map`:
  - Fake graph returns in 0.5s with `final_state` containing all four reports; assert the persisted `run_finished` has `duration_s` in `(0.4, 0.6)` and `summary_by_stage` contains all four stage keys.
- `test_decision_event_emitted_after_propagate`:
  - Fake graph; assert exactly one `decision` event with the expected payload is persisted at the end of the run.

### 12.3 Frontend: `web/frontend/src/__tests__/useFocusedRunEvents.test.ts` (new)

- `returns events for the focused ticker only`:
  - Seed buffer with `[evt(run 1), evt(run 2)]`, focused = "NVDA", `lastRunIdByTicker: { NVDA: 1 }`; assert hook returns only the run-1 events.
- `returns empty list when no ticker is focused`:
  - Same but focused = null; assert [].
- `returns empty list when the focused ticker has no last run`:
  - Same but `lastRunIdByTicker: {}`; assert [].
- `updates when focused changes`:
  - Render with focused = "NVDA", then `setState({ focusedTicker: "AAPL", lastRunIdByTicker: { AAPL: 2 } })`; assert the hook now returns run-2 events.

### 12.4 Frontend: `web/frontend/src/__tests__/LiveEventStream.test.tsx` (extend)

Add per-run-id coverage. The existing 8 tests already cover the rendering for the global buffer; new tests confirm the hook swaps cleanly.

- `renders only the focused run's events`:
  - Seed buffer with two runs' events; focused = "NVDA", run 1; assert only run-1 events render.

### 12.5 Frontend: `web/frontend/src/__tests__/StageGrid.test.tsx` (extend or new)

- `marks a stage as done when analyst_completed fires`:
  - Seed focused events with `analyst_started: Market Analyst` followed by `analyst_completed: {stage: "market"}`; assert the market tile has `data-status="done"`.
- `does not regress to running when subsequent tool nodes fire`:
  - Add `analyst_started: tools_market` after the completion; assert the tile stays `data-status="done"`.
- `shows errored when run_failed fires for the focused run`:
  - Seed focused events with `run_failed`; assert the relevant tile has `data-status="errored"`.
- `node name key divergence does not break status`:
  - Seed `analyst_started: Sentiment Analyst` + `analyst_completed: {stage: "sentiment"}`; assert the sentiment tile goes "done" (this is the case the existing substring match handled by luck; the new stage-key map makes it correct).

### 12.6 Frontend: `web/frontend/src/__tests__/App.test.tsx` (extend)

- `decision lookup is scoped to the focused run`:
  - Seed the buffer with a run-1 `decision` event (BUY) and a run-2 `decision` event (SELL). focused = ticker-of-run-2. Assert `DecisionPanel` shows SELL, not BUY.
- `restores past events into the buffer on mount`:
  - Mock `fetch` for `/api/watchlist` and `/api/runs/7`; pre-seed `focusedTicker: "NVDA", lastRunIdByTicker: { NVDA: 7 }`; assert the seeded event bubble renders.

### 12.7 Frontend: `web/frontend/src/__tests__/store-ui.test.ts` (extend)

- `restoreEvents replaces existing events for the same runId`.
- `restoreEvents preserves events from other runs`.
- `restoreEvents respects the 1000-event cap`.
- `clearLastRunIdForTicker drops only the named key`.

### 12.8 Frontend: `web/frontend/src/__tests__/WatchlistRail.test.tsx` (extend)

- `clicking the X shows the inline confirm; Cancel hides it`.
- `clicking Remove calls the API and invalidates the watchlist query`.
- `removing the focused ticker focuses the next row`.
- `removing the last ticker clears focus`.

### 12.9 Frontend: `web/frontend/src/__tests__/useRestoredRunEvents.test.ts` (new)

- `hydrates event buffer from /api/runs/{id} on mount`.
- `skips the fetch for active runs`.
- `clears the stale run id on 404`.
- `refetches when focused changes`.

## 13. Rollout & risk

- **No new dependencies.** LangChain's `BaseCallbackHandler` is already a transitive dep; TanStack Query and zustand are already in the bundle.
- **No changes to the event protocol or the storage schema.** The 14 event types stay the same. The `Event` table's open `payload_json` already accepts any JSON-serializable data dict.
- **Backwards compatibility:** `restoreEvents`, `clearLastRunIdForTicker`, and `useFocusedRunEvents` are additive. The existing `appendEvent` path stays the same — events still get pushed into the global buffer; only the *display* changes. `LiveEventStream` and `StageGrid` lose nothing because every event that used to be in the global buffer still is; they just see a filtered subset.
- **Risk: token cost of `analyst_thinking` text previews.** A 200-char preview per LLM call adds maybe 1-2 KB per call. Across a typical 8-node run, that's 8-16 KB total. Negligible.
- **Risk: `on_chat_model_start` fires per LLM call inside an agent node.** An agent that does `tool → tool → tool → final text` fires it four times. The `analyst_thinking` events will be four bubbles, in order. That's correct — the user *should* see the model's tool-use loop — but the test in 12.1 should assert the order, not just the count.
- **Risk: the `node_exited` callback is emitted from the same thread that runs `graph.stream()`.** The `event_callback` already handles thread-safety via `events.emit`'s `call_soon_threadsafe` path (`app.py:39-47`). No new threading concern.
- **Risk: the existing `test_runner.py:36-38` asserts that scripted `analyst_thinking`, `analyst_completed`, `debate_message`, `decision` events are persisted. After this change, production code now emits them too, so the test passes for a different reason.** Update the test name and docstring to reflect that this is a *fixture* script and the new production code paths are tested separately in 12.2.
- **Risk: the watchlist-on-load empty state is a separate, pre-existing issue not addressed by this spec.** The uncommitted `vite.config.ts` change (`localhost` → `127.0.0.1` for the proxy target) is the most likely fix; document this in the commit message.
- **Risk: a long past run with a large event payload.** Same 1000-event cap (`appendEvent` and `restoreEvents` both use it) bounds memory.

## 14. Open questions

None. The earlier spec's four questions (restoration trigger, active-run handling, remove confirmation, focus on removal) and the new "fold in the rich protocol + filtering" direction are all answered. The watchlist-on-load empty state is a separate debugging issue, not a design question.
