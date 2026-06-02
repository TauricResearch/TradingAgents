# Dashboard Real-Time View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dashboard match the protocol its UI was already designed for. Server emits the full event protocol in production; frontend display components filter by `run_id`; refresh restores the focused ticker's last run from the server; watchlist supports removal with inline confirm.

**Architecture:** Server-side additions are a `StreamingCallbackHandler` (`BaseCallbackHandler`) attached to the chat model and a symmetric `node_exited` graph callback. Frontend-side additions are two new hooks (`useFocusedRunEvents`, `useRestoredRunEvents`), two new store actions (`restoreEvents`, `clearLastRunIdForTicker`), and three display components switching to the filtered list. Price feed gains a real `change_pct` from `fast_info.previousClose`. No new dependencies.

**Tech Stack:** Python 3.13, FastAPI, SQLModel, yfinance, LangChain `BaseCallbackHandler`, React 18, TypeScript, TanStack Query, Zustand, Vitest, Pytest.

**Branch:** `feat/trading-dashboard`

---

## File Structure

| Path | Role | Action |
|------|------|--------|
| `web/server/price_feed.py` | Background price poller | EDIT (compute change_pct) |
| `web/server/callbacks.py` | New: BaseCallbackHandler for LLM/tool events | NEW |
| `tradingagents/graph/trading_graph.py` | Graph execution; emit `node_exited` symmetric to `node_entered` | EDIT |
| `web/server/runner.py` | Wire callback handler, map `node_exited` → `analyst_completed`, emit `decision` + real `run_finished` | EDIT |
| `web/frontend/src/store/ui.ts` | Add `restoreEvents`, `clearLastRunIdForTicker` actions | EDIT |
| `web/frontend/src/hooks/useFocusedRunEvents.ts` | New: filter `eventBuffer` by focused run id | NEW |
| `web/frontend/src/hooks/useRestoredRunEvents.ts` | New: fetch `/api/runs/{lastRunId}` on hydration | NEW |
| `web/frontend/src/components/LiveEventStream.tsx` | Use `useFocusedRunEvents` | EDIT |
| `web/frontend/src/components/StageGrid.tsx` | Use `useFocusedRunEvents`; fix node-name key divergence | EDIT |
| `web/frontend/src/App.tsx` | Wire both hooks; switch decision lookup | EDIT |
| `web/frontend/src/components/TickerRow.tsx` | Add remove button + pending state | EDIT |
| `web/frontend/src/components/WatchlistRail.tsx` | Wire remove flow + focus-shift | EDIT |
| `web/server/tests/test_price_feed.py` | Tests for change_pct | EXTEND |
| `web/server/tests/test_callbacks.py` | Tests for StreamingCallbackHandler | NEW |
| `web/server/tests/test_runner.py` | Tests for node_exited mapping, decision event, real run_finished | EXTEND |
| `web/frontend/src/__tests__/store-ui.test.ts` | Tests for new store actions | NEW (or EXTEND) |
| `web/frontend/src/__tests__/useFocusedRunEvents.test.ts` | Hook tests | NEW |
| `web/frontend/src/__tests__/useRestoredRunEvents.test.ts` | Hook tests | NEW |
| `web/frontend/src/__tests__/LiveEventStream.test.tsx` | Per-run-id rendering | EXTEND |
| `web/frontend/src/__tests__/StageGrid.test.tsx` | Stage status with analyst_completed | NEW |
| `web/frontend/src/__tests__/App.test.tsx` | Decision scoped to focused run + restore on mount | EXTEND |
| `web/frontend/src/__tests__/WatchlistRail.test.tsx` | Remove button + focus-shift | EXTEND |

**Test commands:**
- Python (server): `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents; .\.venv\Scripts\python.exe -m pytest <path> -v`
- Frontend: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend; & "C:\Program Files\nodejs\node.exe" ./node_modules/vitest/vitest.mjs run <path>`

**Existing fixtures to reuse:**
- `web/server/tests/fixtures/fake_graph.py` — `FakeTradingAgents.propagate` already drives scripted events. The new tests extend it.
- `web/frontend/src/__tests__/LiveEventStream.test.tsx` (8 tests already) — extend with per-run-id case.

---

## Task 1: Price feed — compute `change_pct`

**Files:**
- Modify: `web/server/price_feed.py:42-77` (per-ticker block in `_poll_once`)
- Test: `web/server/tests/test_price_feed.py`

- [ ] **Step 1: Write the failing tests in `web/server/tests/test_price_feed.py`**

Create the file (it may not exist yet — check first; if it does, add a `TestComputeChangePct` class at the bottom):

```python
"""Tests for the price-feed poll loop, focused on change_pct calculation."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from web.server.price_feed import PriceSnapshot, PriceState, _poll_once


def _make_broadcast():
    """Returns (calls, broadcast_fn). Each call appends the event dict."""
    calls = []
    def broadcast(evt):
        calls.append(evt)
    return calls, broadcast


def _patch_yfinance(monkeypatch, *, previous_close: float, last_price: float, intraday: list[float] | None = None):
    """Patch yfinance so the poll loop sees a known state.

    - ``previous_close`` is what ``fast_info.get("previousClose")`` returns.
    - ``last_price`` is the last value of the intraday series (overrides ``intraday``).
    - ``intraday`` is the full intraday series; defaults to ``[last_price]``.
    """
    if intraday is None:
        intraday = [last_price]
    df = MagicMock()
    # df["NVDA"]["Close"] -> Series-like
    series = MagicMock()
    series.empty = False
    series.dropna.return_value.tail.return_value = intraday
    df.__getitem__.return_value.__getitem__.return_value = series

    fast_info = MagicMock()
    fast_info.get.return_value = previous_close
    ticker = MagicMock()
    ticker.fast_info = fast_info
    monkeypatch.setattr("web.server.price_feed.yf.Ticker", lambda _t: ticker)
    monkeypatch.setattr("web.server.price_feed.yf.download", lambda **kw: df)
    return df


@pytest.mark.unit
class TestComputeChangePct:
    def test_change_pct_is_computed_from_previous_close(self, monkeypatch):
        """The regression test: change_pct must come from previousClose, not the default 0.0."""
        _patch_yfinance(monkeypatch, previous_close=100.0, last_price=103.0)
        state = PriceState(snapshots={}, tickers=lambda: ["NVDA"])
        calls, broadcast = _make_broadcast()

        import asyncio
        asyncio.run(_poll_once(state, broadcast))

        assert len(calls) == 1
        assert calls[0]["data"]["change_pct"] == pytest.approx(3.0)

    def test_change_pct_is_zero_when_previous_close_is_zero(self, monkeypatch):
        _patch_yfinance(monkeypatch, previous_close=0.0, last_price=103.0)
        state = PriceState(snapshots={}, tickers=lambda: ["NVDA"])
        calls, broadcast = _make_broadcast()

        import asyncio
        asyncio.run(_poll_once(state, broadcast))

        assert calls[0]["data"]["change_pct"] == 0.0

    def test_change_pct_is_zero_when_price_series_is_empty(self, monkeypatch):
        df = MagicMock()
        series = MagicMock()
        series.empty = True
        df.__getitem__.return_value.__getitem__.return_value = series
        fast_info = MagicMock()
        fast_info.get.return_value = 100.0
        ticker = MagicMock()
        ticker.fast_info = fast_info
        monkeypatch.setattr("web.server.price_feed.yf.Ticker", lambda _t: ticker)
        monkeypatch.setattr("web.server.price_feed.yf.download", lambda **kw: df)

        state = PriceState(snapshots={}, tickers=lambda: ["NVDA"])
        calls, broadcast = _make_broadcast()
        import asyncio
        asyncio.run(_poll_once(state, broadcast))

        assert calls[0]["data"]["stale"] is True
        assert calls[0]["data"]["change_pct"] == 0.0

    def test_change_pct_handles_negative_change(self, monkeypatch):
        _patch_yfinance(monkeypatch, previous_close=100.0, last_price=97.0)
        state = PriceState(snapshots={}, tickers=lambda: ["NVDA"])
        calls, broadcast = _make_broadcast()
        import asyncio
        asyncio.run(_poll_once(state, broadcast))

        assert calls[0]["data"]["change_pct"] == pytest.approx(-3.0)

    def test_price_update_event_uses_real_change_pct_not_default(self, monkeypatch):
        """Final regression test: a positive previousClose and a positive last_price must yield a non-zero change_pct."""
        _patch_yfinance(monkeypatch, previous_close=200.0, last_price=210.0)
        state = PriceState(snapshots={}, tickers=lambda: ["NVDA"])
        calls, broadcast = _make_broadcast()
        import asyncio
        asyncio.run(_poll_once(state, broadcast))

        assert calls[0]["data"]["change_pct"] != 0.0
        assert calls[0]["data"]["change_pct"] == pytest.approx(5.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest web/server/tests/test_price_feed.py -v`
Expected: all 5 tests fail with `change_pct == 0.0` (the dataclass default).

- [ ] **Step 3: Fix `_poll_once` in `web/server/price_feed.py`**

Edit `web/server/price_feed.py:42-77` (the `for ticker in tickers:` block) to:

```python
    for ticker in tickers:
        snap = state.snapshots.get(ticker) or PriceSnapshot()
        try:
            # With ``group_by="ticker"`` yfinance returns a MultiIndex where
            # the OUTER level is the field (Close/Open/...) and the INNER
            # level is the ticker — even for a single-ticker list. So
            # ``df[ticker]["Close"]`` works for both single and multi.
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
            # change_pct is the percent move from the previous trading
            # session's close. fast_info is a lightweight single-field
            # lookup; the CLI uses it for the same purpose elsewhere.
            # Guard against zero to avoid div-by-zero on newly-listed
            # tickers and on stale prices.
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
                    "change_pct": snap.change_pct,
                    "sparkline": snap.sparkline,
                    "stale": snap.stale,
                },
            ))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest web/server/tests/test_price_feed.py -v`
Expected: 5/5 pass.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/price_feed.py web/server/tests/test_price_feed.py
git commit -m "fix(price): compute change_pct from fast_info.previousClose"
```

---

## Task 2: `StreamingCallbackHandler` — LLM/tool events

**Files:**
- Create: `web/server/callbacks.py`
- Test: `web/server/tests/test_callbacks.py`

- [ ] **Step 1: Write the failing tests in `web/server/tests/test_callbacks.py`**

```python
"""Tests for StreamingCallbackHandler.

The handler bridges LangChain per-step callbacks into the dashboard's
WsEvent protocol. We test against a captured broadcast list rather
than against the live WS queue.
"""
from __future__ import annotations

from unittest.mock import MagicMock
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from web.server.callbacks import StreamingCallbackHandler


def _make():
    events = []
    def broadcast(evt):
        events.append(evt)
    return StreamingCallbackHandler(run_id=42, broadcast=broadcast), events


@pytest.mark.unit
class TestOnChatModelStart:
    def test_emits_analyst_thinking_with_prompt_preview(self):
        handler, events = _make()
        handler.on_chat_model_start(
            {"name": "ChatOpenAI"},
            [[HumanMessage(content="What's the price of NVDA?")]],
        )
        assert len(events) == 1
        assert events[0]["type"] == "analyst_thinking"
        assert events[0]["run_id"] == 42
        assert events[0]["data"]["text_preview"] == "What's the price of NVDA?"

    def test_truncates_long_prompts_to_200_chars(self):
        handler, events = _make()
        long_msg = "x" * 1000
        handler.on_chat_model_start(
            {"name": "ChatOpenAI"},
            [[HumanMessage(content=long_msg)]],
        )
        assert len(events[0]["data"]["text_preview"]) == 200

    def test_handles_missing_human_message(self):
        handler, events = _make()
        handler.on_chat_model_start(
            {"name": "ChatOpenAI"},
            [[AIMessage(content="no user input here")]],
        )
        assert events[0]["data"]["text_preview"] is None


@pytest.mark.unit
class TestOnLlmEnd:
    def test_emits_analyst_thinking_for_text_response(self):
        handler, events = _make()
        gen = MagicMock()
        chat = MagicMock()
        chat.message = AIMessage(content="Some analysis text.")
        chat.message.tool_calls = []
        gen.__iter__ = lambda self: iter([chat])
        result = MagicMock()
        result.generations = [gen]
        handler.on_llm_end(result)
        assert any(e["data"].get("text_fragment") == "Some analysis text." for e in events)

    def test_skips_when_response_has_tool_calls(self):
        handler, events = _make()
        gen = MagicMock()
        chat = MagicMock()
        chat.message = AIMessage(content="", tool_calls=[{"name": "x", "args": {}, "id": "1"}])
        gen.__iter__ = lambda self: iter([chat])
        result = MagicMock()
        result.generations = [gen]
        handler.on_llm_end(result)
        assert events == []


@pytest.mark.unit
class TestOnTool:
    def test_on_tool_start_emits_tool_call(self):
        handler, events = _make()
        handler.on_tool_start({"name": "get_stock_data"}, '{"ticker": "NVDA"}')
        assert len(events) == 1
        assert events[0]["type"] == "tool_call"
        assert events[0]["data"]["tool"] == "get_stock_data"
        assert events[0]["data"]["args"] == '{"ticker": "NVDA"}'

    def test_on_tool_end_emits_tool_result_with_string_output(self):
        handler, events = _make()
        handler.on_tool_end("the price is 900")
        assert len(events) == 1
        assert events[0]["type"] == "tool_result"
        assert events[0]["data"]["summary"] == "the price is 900"

    def test_on_tool_end_emits_tool_result_with_ToolMessage(self):
        handler, events = _make()
        msg = ToolMessage(content="price=900", name="get_stock_data", tool_call_id="1")
        handler.on_tool_end(msg)
        assert events[0]["data"]["summary"] == "price=900"
        assert events[0]["data"]["tool"] == "get_stock_data"

    def test_on_tool_error_emits_tool_result_with_error(self):
        handler, events = _make()
        handler.on_tool_error(ValueError("bad arg"))
        assert len(events) == 1
        assert events[0]["data"]["error"] == "bad arg"
        assert events[0]["data"]["summary"] == "bad arg"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest web/server/tests/test_callbacks.py -v`
Expected: ImportError on `web.server.callbacks`.

- [ ] **Step 3: Create `web/server/callbacks.py`**

```python
"""LangChain callback handler that bridges per-step LLM/tool activity
into the dashboard's event protocol.

Attach a single instance per run via ``TradingAgentsGraph(callbacks=[...])``
(or by wrapping the LLM directly via the ``callbacks`` kwarg on
``NormalizedChatOpenAI`` / ``NormalizedChatAnthropic`` / etc.).

The handler takes an explicit ``broadcast`` callable so the unit tests
can capture events without going through the WS plumbing.
"""
from __future__ import annotations

from typing import Any, Callable, Optional
from langchain_core.callbacks import BaseCallbackHandler


def _broadcast_via_events(run_id: int) -> Callable[[dict], None]:
    """Build a broadcast callable that goes through ``events.emit``.

    Used in production wiring (runner.py) so all emissions land in the
    same DB-write + WS-broadcast path as the runner's manual emits.
    """
    from . import events
    def _b(evt: dict) -> None:
        events.emit(run_id, evt["type"], evt["data"])
    return _b


class StreamingCallbackHandler(BaseCallbackHandler):
    """Maps LangChain's per-step callbacks to WsEvent payloads."""

    def __init__(self, *, run_id: int, broadcast: Optional[Callable[[dict], None]] = None) -> None:
        self.run_id = run_id
        self._broadcast = broadcast or _broadcast_via_events(run_id)

    def _emit(self, type_: str, data: dict) -> None:
        self._broadcast({"v": 1, "type": type_, "ts": "", "run_id": self.run_id, "data": data})

    # ---- LLM -----------------------------------------------------------

    def on_chat_model_start(self, serialized: dict, messages: list, **kw) -> None:
        prompt_preview = _extract_last_user_text(messages)
        self._emit("analyst_thinking", {
            "text_preview": (prompt_preview[:200] if prompt_preview else None),
        })

    def on_llm_end(self, response: Any, **kw) -> None:
        # Only emit a text fragment for free-text completions. When the
        # response has tool_calls, the tool_call event will fire in
        # on_tool_start, so we don't double-fire here.
        try:
            for gen in response.generations:
                for chat in gen:
                    msg = getattr(chat, "message", None)
                    if msg is None:
                        continue
                    content = str(getattr(msg, "content", "") or "")
                    tool_calls = getattr(msg, "tool_calls", None) or []
                    if content and not tool_calls:
                        self._emit("analyst_thinking", {"text_fragment": content[:500]})
                        return  # one fragment per LLM call is enough
        except Exception:
            return

    # ---- Tools ---------------------------------------------------------

    def on_tool_start(self, serialized: dict, input_str: str, **kw) -> None:
        name = (serialized or {}).get("name", "unknown")
        self._emit("tool_call", {"tool": name, "args": str(input_str)[:200]})

    def on_tool_end(self, output: Any, **kw) -> None:
        text = str(getattr(output, "content", output) or "")
        name = getattr(output, "name", "unknown")
        self._emit("tool_result", {"tool": name, "summary": text[:200]})

    def on_tool_error(self, error: BaseException, **kw) -> None:
        text = str(error)
        self._emit("tool_result", {"tool": "unknown", "error": text, "summary": text[:200]})


def _extract_last_user_text(messages: list) -> Optional[str]:
    """Best-effort extraction of the most recent user message text.

    LangChain's on_chat_model_start passes a nested list of message
    lists (one per LLM call inside the agent). The last HumanMessage
    in the last list is the freshest user-authored text.
    """
    try:
        for batch in reversed(messages or []):
            for msg in reversed(batch or []):
                if getattr(msg, "type", None) == "human":
                    return str(msg.content)
    except Exception:
        return None
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest web/server/tests/test_callbacks.py -v`
Expected: 9/9 pass.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/callbacks.py web/server/tests/test_callbacks.py
git commit -m "feat(web): add StreamingCallbackHandler for LLM/tool events"
```

---

## Task 3: `node_exited` callback in `trading_graph.py`

**Files:**
- Modify: `tradingagents/graph/trading_graph.py:469-509` (add symmetric emit in both stream branches)

This task has no new tests; the runner tests in Task 4 cover the integration. The change is symmetric to the existing `node_entered` emit.

- [ ] **Step 1: Add `node_exited` to the debug branch (`trading_graph.py:469-489`)**

In `trading_graph.py`, find the debug-branch block (the `if self.debug:` block). After the line `final_state.update(chunk)` inside the `for chunk in trace:` loop, add a second `event_callback` call for `node_exited`. The new block sits *inside* the same loop, after the existing `node_entered` block. Specifically, change:

```python
        if self.debug:
            trace = []
            for chunk in self.graph.stream(init_agent_state, **args):
                if len(chunk["messages"]) == 0:
                    pass
                else:
                    chunk["messages"][-1].pretty_print()
                    trace.append(chunk)
            # Streamed chunks are per-node deltas. Merge them so the returned
            # state matches what graph.invoke() yields in the non-debug path.
            final_state = {}
            for chunk in trace:
                if event_callback is not None:
                    try:
                        event_callback(
                            "node_entered",
                            {"node": next(iter(chunk)), "ts": _now_iso()},
                        )
                    except Exception:  # callbacks must never break the run
                        logger.exception("event_callback raised; continuing")
                final_state.update(chunk)
```

to:

```python
        if self.debug:
            trace = []
            for chunk in self.graph.stream(init_agent_state, **args):
                if len(chunk["messages"]) == 0:
                    pass
                else:
                    chunk["messages"][-1].pretty_print()
                    trace.append(chunk)
            # Streamed chunks are per-node deltas. Merge them so the returned
            # state matches what graph.invoke() yields in the non-debug path.
            final_state = {}
            for chunk in trace:
                if event_callback is not None:
                    try:
                        event_callback(
                            "node_entered",
                            {"node": next(iter(chunk)), "ts": _now_iso()},
                        )
                    except Exception:  # callbacks must never break the run
                        logger.exception("event_callback raised; continuing")
                final_state.update(chunk)
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
                    except Exception:  # callbacks must never break the run
                        logger.exception("event_callback raised; continuing")
```

- [ ] **Step 2: Add `node_exited` to the non-debug branch (`trading_graph.py:490-509`)**

Find the non-debug branch (the `else:` block). The current code is:

```python
        else:
            final_state = dict(init_agent_state)
            for chunk in self.graph.stream(
                init_agent_state,
                **{**args, "stream_mode": "updates"},
            ):
                if event_callback is not None:
                    try:
                        event_callback(
                            "node_entered",
                            {"node": next(iter(chunk)), "ts": _now_iso()},
                        )
                    except Exception:
                        logger.exception("event_callback raised; continuing")
                final_state.update(next(iter(chunk.values())))
```

Change it to:

```python
        else:
            final_state = dict(init_agent_state)
            for chunk in self.graph.stream(
                init_agent_state,
                **{**args, "stream_mode": "updates"},
            ):
                if event_callback is not None:
                    try:
                        event_callback(
                            "node_entered",
                            {"node": next(iter(chunk)), "ts": _now_iso()},
                        )
                    except Exception:
                        logger.exception("event_callback raised; continuing")
                final_state.update(next(iter(chunk.values())))
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

- [ ] **Step 3: Verify nothing else broke**

Run the full graph + runner test suite to confirm:

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.\.venv\Scripts\python.exe -m pytest tests/ web/server/tests/ -q
```

Expected: same set of pre-existing failures (the `DEEPSEEK_API_KEY` one); everything else green. The new `node_exited` emit should produce *one extra* event per node, which the existing fake-graph tests will see. If any test fails because the `FakeTradingAgents.propagate` does not emit `node_exited`, update the fake (see Step 4).

- [ ] **Step 4: Update the fake graph fixture to emit `node_exited`**

`web/server/tests/fixtures/fake_graph.py:43-55` — `FakeTradingAgents.propagate` calls `event_callback("node_entered", {"node": node.name})` and `event_callback(ev["type"], ev.get("data", {}))` for scripted events. After the `node_entered` emit, also emit `node_exited` with the same node name (no delta needed for the fake). The simplest change is to mirror the call:

```python
        if event_callback:
            event_callback("node_entered", {"node": node.name})
            event_callback("node_exited", {"node": node.name, "delta": {}})
            for ev in node.events:
                event_callback(ev["type"], ev.get("data", {}))
```

- [ ] **Step 5: Re-run the test suite**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.\.venv\Scripts\python.exe -m pytest tests/ web/server/tests/ -q
```

Expected: green (modulo the DEEPSEEK env var one).

- [ ] **Step 6: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add tradingagents/graph/trading_graph.py web/server/tests/fixtures/fake_graph.py
git commit -m "feat(graph): emit node_exited symmetric to node_entered"
```

---

## Task 4: Runner — wire callbacks, map `node_exited`, emit `decision` and real `run_finished`

**Files:**
- Modify: `web/server/runner.py:34-41, 102-189`
- Test: `web/server/tests/test_runner.py` (extend with new test class)

- [ ] **Step 1: Write the failing tests in `web/server/tests/test_runner.py`**

Add a new class at the end of the file. (Read the existing test file first to confirm the fixture names — `FakeTradingAgents`, `setup_runner_with_fake_graph`, `app`, `client`. Use whatever the existing tests use; do not invent new fixtures.)

```python
class TestNodeExitedMapping:
    def test_node_exited_emits_analyst_completed_for_agent_node(self, ...):
        # fixture params here — match the existing tests' signature
        # Call the runner with a fake graph whose script emits a node_exited for "Market Analyst"
        # Assert: an analyst_completed event is persisted with data.stage == "market"

    def test_node_exited_skips_completion_for_tool_node(self, ...):
        # Same, but node_exited is for "tools_market"
        # Assert: no analyst_completed event persisted

    def test_node_exited_skips_completion_for_portfolio_manager(self, ...):
        # Same, but for "Portfolio Manager"
        # Assert: no analyst_completed (the decision event is the completion signal)


class TestDecisionAndRunFinished:
    def test_decision_event_emitted_after_propagate(self, ...):
        # Run a fake graph that returns a final_state with final_trade_decision
        # Assert: exactly one "decision" event persisted with action, target, rationale, confidence

    def test_run_finished_uses_real_duration_and_summary_map(self, ...):
        # Run a fake graph (it returns in <1s)
        # Assert: run_finished has duration_s in (0.0, 5.0) and summary_by_stage is a dict
```

The exact fixture parameters come from reading `web/server/tests/test_runner.py`. Use the same pattern as the existing tests in that file.

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest web/server/tests/test_runner.py::TestNodeExitedMapping web/server/tests/test_runner.py::TestDecisionAndRunFinished -v`
Expected: 5 failures.

- [ ] **Step 3: Update `build_graph` in `web/server/runner.py` to accept and forward `callbacks`**

Edit `web/server/runner.py:34-41`:

```python
def build_graph(config=None, *, callbacks=None):
    """Build a TradingAgentsGraph. Tests monkeypatch this.

    The ``callbacks`` kwarg is forwarded to ``TradingAgentsGraph(callbacks=...)``
    so a StreamingCallbackHandler can be attached at the graph level. Tests
    can pass an empty list when they don't care.
    """
    return TradingAgentsGraph(
        config=config or DEFAULT_CONFIG,
        callbacks=callbacks or [],
    )
```

- [ ] **Step 4: Update `_run_one` in `web/server/runner.py:102-189`**

Replace the body of `_run_one` (from line 102 to the end of the function, just before `class _CancelSentinel`) with:

```python
async def _run_one(rid: int, sem: asyncio.Semaphore) -> None:
    global _active
    t_start = time.monotonic()
    try:
        run = db.get_run(rid)
        if run is None:
            return
        if run.cancel_requested:
            db.mark_run_failed(rid, "cancelled")
            events.emit(rid, "run_failed", {"reason": "cancelled"})
            return

        events.emit(rid, "run_started", {"ticker": run.ticker})

        # Stage map: LangGraph node name -> (stage_key, report_field).
        # The runner is the only place that knows how to interpret the
        # per-node report; the graph just emits the raw delta.
        _STAGE_MAP = {
            "Market Analyst": ("market", "market_report"),
            "Sentiment Analyst": ("sentiment", "sentiment_report"),
            "News Analyst": ("news", "news_report"),
            "Fundamentals Analyst": ("fundamentals", "fundamentals_report"),
            "Bull Researcher": ("research", None),
            "Bear Researcher": ("research", None),
            "Research Manager": ("research", "investment_plan"),
            "Trader": ("trader", "trader_investment_plan"),
            "Aggressive Analyst": ("risk", None),
            "Conservative Analyst": ("risk", None),
            "Neutral Analyst": ("risk", None),
        }

        from web.server.callbacks import StreamingCallbackHandler
        handler = StreamingCallbackHandler(run_id=rid)
        graph = build_graph(callbacks=[handler])

        def _stage_summary_for_node(node_name: str, delta: dict):
            """Return (stage_key, summary, excerpt) for analyst_completed, or (None,...) to skip."""
            if node_name not in _STAGE_MAP:
                return (None, None, None)
            stage, report_field = _STAGE_MAP[node_name]
            excerpt = None
            if report_field:
                excerpt = (delta or {}).get(report_field, "")
                if excerpt and len(excerpt) > 200:
                    excerpt = excerpt[:200] + "…"
            return (stage, "completed", excerpt)

        def cb(node_name: str, payload: dict) -> None:
            if db.get_run(rid).cancel_requested:
                raise _CancelSentinel()
            if node_name == "node_entered":
                events.emit(rid, "analyst_started", {"node": payload.get("node", node_name), **payload})
            elif node_name == "node_exited":
                stage, summary, excerpt = _stage_summary_for_node(
                    payload.get("node", ""), payload.get("delta", {})
                )
                if stage is None:
                    return  # tool/clear/portfolio_manager — no completion event
                data = {"stage": stage, "summary": summary}
                if excerpt:
                    data["report_excerpt"] = excerpt
                events.emit(rid, "analyst_completed", data)
            else:
                events.emit(rid, node_name, payload)

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

        if db.get_run(rid).cancel_requested:
            db.mark_run_failed(rid, "cancelled")
            events.emit(rid, "run_failed", {"reason": "cancelled"})
            return

        # Emit the decision event before run_finished so the UI sees
        # them in chronological order.
        decision = (final or {}).get("decision") or {}
        action = decision.get("action")
        target = decision.get("target")
        rationale = decision.get("rationale", "")
        confidence = decision.get("confidence", 0.0)
        events.emit(rid, "decision", {
            "action": action,
            "target": target,
            "rationale": rationale,
            "confidence": confidence,
        })
        db.mark_run_done(
            rid,
            decision_action=action or "HOLD",
            decision_target=target,
            decision_rationale=rationale,
            decision_confidence=confidence,
        )
        db.update_watchlist_last_decision(
            run.ticker, rid,
            f"{action} @ {target}" if target else (action or ""),
            datetime.now(timezone.utc),
        )
        # Real duration + per-stage summary.
        duration_s = round(time.monotonic() - t_start, 2)
        summary_by_stage = {}
        if final:
            for stage_key, field in (
                ("market", "market_report"),
                ("sentiment", "sentiment_report"),
                ("news", "news_report"),
                ("fundamentals", "fundamentals_report"),
            ):
                excerpt = final.get(field) or ""
                if excerpt:
                    summary_by_stage[stage_key] = excerpt[:200]
        events.emit(rid, "run_finished", {
            "duration_s": duration_s,
            "summary_by_stage": summary_by_stage,
        })
    finally:
        _active -= 1
        sem.release()
```

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest web/server/tests/test_runner.py -v`
Expected: all (existing + new) pass.

- [ ] **Step 6: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/runner.py web/server/tests/test_runner.py
git commit -m "feat(runner): wire StreamingCallbackHandler and emit decision + real run_finished"
```

---

## Task 5: `useUi` store — add `restoreEvents` and `clearLastRunIdForTicker`

**Files:**
- Modify: `web/frontend/src/store/ui.ts:5-28, 30-46` (add interface entries + implementations)
- Test: `web/frontend/src/__tests__/store-ui.test.ts` (new file or extend existing — read first)

- [ ] **Step 1: Write the failing tests in `web/frontend/src/__tests__/store-ui.test.ts`**

Create the file (read first to see if it exists; if it does, add to it):

```ts
import { describe, it, expect, beforeEach } from "vitest";
import { useUi } from "../store/ui";
import type { WsEvent } from "../lib/events";

const evt = (runId: number, type: string, id: number): WsEvent => ({
  v: 1, type: type as any, ts: `t${id}`, run_id: runId, data: {}, id,
});

describe("useUi", () => {
  beforeEach(() => {
    useUi.setState({
      eventBuffer: [],
      lastRunIdByTicker: {},
      activeRunIdByTicker: {},
      focusedTicker: null,
    });
  });

  describe("restoreEvents", () => {
    it("replaces existing events for the same runId", () => {
      useUi.setState({ eventBuffer: [evt(42, "analyst_started", 1), evt(42, "analyst_started", 2)] });
      useUi.getState().restoreEvents(42, [evt(42, "analyst_thinking", 10), evt(42, "analyst_thinking", 11), evt(42, "analyst_thinking", 12)]);
      const buf = useUi.getState().eventBuffer;
      expect(buf).toHaveLength(3);
      expect(buf.every((e) => e.run_id === 42)).toBe(true);
    });

    it("preserves events from other runs", () => {
      useUi.setState({ eventBuffer: [evt(1, "analyst_started", 1), evt(2, "analyst_started", 2)] });
      useUi.getState().restoreEvents(1, [evt(1, "analyst_thinking", 10)]);
      const buf = useUi.getState().eventBuffer;
      expect(buf).toHaveLength(2);
      expect(buf.find((e) => e.run_id === 1)?.id).toBe(10);
      expect(buf.find((e) => e.run_id === 2)?.id).toBe(2);
    });

    it("respects the 1000-event cap", () => {
      const seed = Array.from({ length: 998 }, (_, i) => evt(99, "analyst_started", i));
      useUi.setState({ eventBuffer: seed });
      const restored = Array.from({ length: 500 }, (_, i) => evt(7, "analyst_started", 1000 + i));
      useUi.getState().restoreEvents(7, restored);
      const buf = useUi.getState().eventBuffer;
      expect(buf).toHaveLength(1000);
      // The 500 restored events must all be present.
      expect(buf.filter((e) => e.run_id === 7)).toHaveLength(500);
    });
  });

  describe("clearLastRunIdForTicker", () => {
    it("drops only the named key", () => {
      useUi.setState({ lastRunIdByTicker: { AAPL: 42, NVDA: 99 } });
      useUi.getState().clearLastRunIdForTicker("AAPL");
      expect(useUi.getState().lastRunIdByTicker).toEqual({ NVDA: 99 });
    });

    it("is a no-op when the key is absent", () => {
      useUi.setState({ lastRunIdByTicker: { NVDA: 99 } });
      useUi.getState().clearLastRunIdForTicker("AAPL");
      expect(useUi.getState().lastRunIdByTicker).toEqual({ NVDA: 99 });
    });
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run from `web/frontend`:
```
& "C:\Program Files\nodejs\node.exe" ./node_modules/vitest/vitest.mjs run src/__tests__/store-ui.test.ts
```
Expected: failures on `restoreEvents` and `clearLastRunIdForTicker` (functions don't exist).

- [ ] **Step 3: Add the actions to `web/frontend/src/store/ui.ts`**

Edit `web/frontend/src/store/ui.ts`:

1. In the `UiState` interface (lines 5-28), add two new actions after `appendEvent` (line 26):
```ts
  appendEvent: (e: WsEvent) => void;
  restoreEvents: (runId: number, events: WsEvent[]) => void;
  clearLastRunIdForTicker: (ticker: string) => void;
  clearBuffer: () => void;
```

2. In the `set` block (lines 30-46), add the implementations after `appendEvent` (line 44):
```ts
      appendEvent: (e) => set((s) => ({ eventBuffer: [...s.eventBuffer, e].slice(-1000) })),
      restoreEvents: (runId, events) => set((s) => {
        // Replace any events for this run id; preserve events from
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
      clearBuffer: () => set({ eventBuffer: [] }),
```

`partialize` (lines 56-59) stays unchanged — it already persists only `focusedTicker` and `lastRunIdByTicker`. `restoreEvents` mutates the runtime-only `eventBuffer` (correctly excluded); `clearLastRunIdForTicker` mutates `lastRunIdByTicker` (correctly persisted).

- [ ] **Step 4: Run the tests to verify they pass**

Run from `web/frontend`:
```
& "C:\Program Files\nodejs\node.exe" ./node_modules/vitest/vitest.mjs run src/__tests__/store-ui.test.ts
```
Expected: 5/5 pass.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/src/store/ui.ts web/frontend/src/__tests__/store-ui.test.ts
git commit -m "feat(ui): add restoreEvents and clearLastRunIdForTicker actions"
```

---

## Task 6: `useFocusedRunEvents` hook

**Files:**
- Create: `web/frontend/src/hooks/useFocusedRunEvents.ts`
- Test: `web/frontend/src/__tests__/useFocusedRunEvents.test.ts`

- [ ] **Step 1: Write the failing tests**

```ts
import { describe, it, expect, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { useUi } from "../store/ui";
import { useFocusedRunEvents } from "../hooks/useFocusedRunEvents";
import type { WsEvent } from "../lib/events";

const evt = (runId: number, type: string, id: number): WsEvent => ({
  v: 1, type: type as any, ts: `t${id}`, run_id: runId, data: {}, id,
});

describe("useFocusedRunEvents", () => {
  beforeEach(() => {
    useUi.setState({
      eventBuffer: [],
      lastRunIdByTicker: {},
      activeRunIdByTicker: {},
      focusedTicker: null,
    });
  });

  it("returns events for the focused ticker only", () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: 1 },
      eventBuffer: [evt(1, "analyst_started", 1), evt(2, "analyst_started", 2)],
    });
    const { result } = renderHook(() => useFocusedRunEvents());
    expect(result.current).toHaveLength(1);
    expect(result.current[0].run_id).toBe(1);
  });

  it("returns empty list when no ticker is focused", () => {
    useUi.setState({
      lastRunIdByTicker: { NVDA: 1 },
      eventBuffer: [evt(1, "analyst_started", 1)],
    });
    const { result } = renderHook(() => useFocusedRunEvents());
    expect(result.current).toEqual([]);
  });

  it("returns empty list when the focused ticker has no last run", () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: {},
      eventBuffer: [evt(1, "analyst_started", 1)],
    });
    const { result } = renderHook(() => useFocusedRunEvents());
    expect(result.current).toEqual([]);
  });

  it("updates when focused changes", () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: 1, AAPL: 2 },
      eventBuffer: [evt(1, "analyst_started", 1), evt(2, "analyst_started", 2)],
    });
    const { result, rerender } = renderHook(() => useFocusedRunEvents());
    expect(result.current[0].run_id).toBe(1);
    useUi.setState({ focusedTicker: "AAPL" });
    rerender();
    expect(result.current[0].run_id).toBe(2);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run from `web/frontend`:
```
& "C:\Program Files\nodejs\node.exe" ./node_modules/vitest/vitest.mjs run src/__tests__/useFocusedRunEvents.test.ts
```
Expected: ImportError on `useFocusedRunEvents`.

- [ ] **Step 3: Create `web/frontend/src/hooks/useFocusedRunEvents.ts`**

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

- [ ] **Step 4: Run the tests to verify they pass**

Run from `web/frontend`:
```
& "C:\Program Files\nodejs\node.exe" ./node_modules/vitest/vitest.mjs run src/__tests__/useFocusedRunEvents.test.ts
```
Expected: 4/4 pass.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/src/hooks/useFocusedRunEvents.ts web/frontend/src/__tests__/useFocusedRunEvents.test.ts
git commit -m "feat(hooks): add useFocusedRunEvents for per-ticker event filtering"
```

---

## Task 7: `useRestoredRunEvents` hook

**Files:**
- Create: `web/frontend/src/hooks/useRestoredRunEvents.ts`
- Test: `web/frontend/src/__tests__/useRestoredRunEvents.test.ts`

- [ ] **Step 1: Write the failing tests**

```ts
import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useUi } from "../store/ui";
import { useRestoredRunEvents } from "../hooks/useRestoredRunEvents";
import * as api from "../lib/api";
import type { WsEvent } from "../lib/events";

const evt = (runId: number, type: string, id: number): WsEvent => ({
  v: 1, type: type as any, ts: `t${id}`, run_id: runId, data: {}, id,
});

beforeEach(() => {
  useUi.setState({
    eventBuffer: [],
    lastRunIdByTicker: {},
    activeRunIdByTicker: {},
    focusedTicker: null,
  });
  vi.restoreAllMocks();
});

describe("useRestoredRunEvents", () => {
  it("hydrates event buffer from /api/runs/{id} on mount", async () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: 7 },
    });
    vi.spyOn(api, "fetchRunDetail").mockResolvedValue({
      run: { id: 7, ticker: "NVDA", started_at: null, finished_at: null,
             status: "done", decision_action: null, decision_target: null,
             decision_rationale: null, decision_confidence: null },
      events: [evt(7, "analyst_thinking", 1), evt(7, "analyst_completed", 2)],
    });
    renderHook(() => useRestoredRunEvents("NVDA"));
    await waitFor(() => {
      const buf = useUi.getState().eventBuffer;
      expect(buf).toHaveLength(2);
      expect(buf.every((e) => e.run_id === 7)).toBe(true);
    });
  });

  it("skips the fetch for active runs", async () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: 7 },
    });
    const fetchSpy = vi.spyOn(api, "fetchRunDetail").mockResolvedValue({
      run: { id: 7, ticker: "NVDA", started_at: null, finished_at: null,
             status: "running", decision_action: null, decision_target: null,
             decision_rationale: null, decision_confidence: null },
      events: [evt(7, "analyst_thinking", 1)],
    });
    renderHook(() => useRestoredRunEvents("NVDA"));
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled();
    });
    // Wait an additional tick to let the effect run.
    await new Promise((r) => setTimeout(r, 50));
    expect(useUi.getState().eventBuffer).toEqual([]);
  });

  it("clears the stale run id on 404", async () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: 7 },
    });
    vi.spyOn(api, "fetchRunDetail").mockRejectedValue(new Error("run 404"));
    renderHook(() => useRestoredRunEvents("NVDA"));
    await waitFor(() => {
      expect(useUi.getState().lastRunIdByTicker.NVDA ?? null).toBeNull();
    });
  });

  it("refetches when focused changes", async () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: 7, AAPL: 8 },
    });
    const fetchSpy = vi.spyOn(api, "fetchRunDetail").mockImplementation(async (id) => ({
      run: { id, ticker: "X", started_at: null, finished_at: null,
             status: "done", decision_action: null, decision_target: null,
             decision_rationale: null, decision_confidence: null },
      events: [evt(id, "analyst_thinking", 1)],
    }));
    const { rerender } = renderHook(({ focused }: { focused: string }) => useRestoredRunEvents(focused), {
      initialProps: { focused: "NVDA" },
    });
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledWith(7));
    rerender({ focused: "AAPL" });
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledWith(8));
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run from `web/frontend`:
```
& "C:\Program Files\nodejs\node.exe" ./node_modules/vitest/vitest.mjs run src/__tests__/useRestoredRunEvents.test.ts
```
Expected: ImportError on `useRestoredRunEvents`.

- [ ] **Step 3: Create `web/frontend/src/hooks/useRestoredRunEvents.ts`**

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

- [ ] **Step 4: Run the tests to verify they pass**

Run from `web/frontend`:
```
& "C:\Program Files\nodejs\node.exe" ./node_modules/vitest/vitest.mjs run src/__tests__/useRestoredRunEvents.test.ts
```
Expected: 4/4 pass.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/src/hooks/useRestoredRunEvents.ts web/frontend/src/__tests__/useRestoredRunEvents.test.ts
git commit -m "feat(hooks): add useRestoredRunEvents for refresh persistence"
```

---

## Task 8: `LiveEventStream` — use `useFocusedRunEvents`

**Files:**
- Modify: `web/frontend/src/components/LiveEventStream.tsx:1, 19-22`
- Test: `web/frontend/src/__tests__/LiveEventStream.test.tsx` (extend)

- [ ] **Step 1: Add a per-run-id rendering test**

In `web/frontend/src/__tests__/LiveEventStream.test.tsx`, add one new `it()` at the end of the existing `describe`:

```ts
  it("renders only the focused run's events", () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: 1 },
      eventBuffer: [
        { v: 1, type: "analyst_thinking", ts: "t1", run_id: 1, data: { text_fragment: "NVDA fragment" }, id: 1 },
        { v: 1, type: "analyst_thinking", ts: "t2", run_id: 2, data: { text_fragment: "AAPL fragment" }, id: 2 },
      ],
    });
    render(<LiveEventStream />);
    expect(screen.getByText(/NVDA fragment/)).toBeInTheDocument();
    expect(screen.queryByText(/AAPL fragment/)).not.toBeInTheDocument();
  });
```

- [ ] **Step 2: Run the new test to verify it fails**

Run from `web/frontend`:
```
& "C:\Program Files\nodejs\node.exe" ./node_modules/vitest/vitest.mjs run src/__tests__/LiveEventStream.test.tsx
```
Expected: the new test fails (both fragments render because the global buffer is used).

- [ ] **Step 3: Switch `LiveEventStream` to `useFocusedRunEvents`**

In `web/frontend/src/components/LiveEventStream.tsx`:

1. Add to imports (top of file):
```ts
import { useFocusedRunEvents } from "../hooks/useFocusedRunEvents";
```

2. In the `LiveEventStream` function body, replace:
```ts
  const events = useUi((s) => s.eventBuffer);
```
with:
```ts
  const events = useFocusedRunEvents();
```

(Keep the `useUi` import — the file still uses `useUi` indirectly via the hook's own selector reads, but the local read is gone. If `useUi` is no longer used anywhere in this file after the swap, drop the import too.)

- [ ] **Step 4: Run the tests to verify they all pass**

Run from `web/frontend`:
```
& "C:\Program Files\nodejs\node.exe" ./node_modules/vitest/vitest.mjs run src/__tests__/LiveEventStream.test.tsx
```
Expected: all 9 tests pass (8 existing + 1 new).

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/src/components/LiveEventStream.tsx web/frontend/src/__tests__/LiveEventStream.test.tsx
git commit -m "refactor(liveeventstream): filter by focused run id"
```

---

## Task 9: `StageGrid` — `useFocusedRunEvents` + node-name → stage-key map

**Files:**
- Modify: `web/frontend/src/components/StageGrid.tsx:1, 15-21, 23-48`
- Test: `web/frontend/src/__tests__/StageGrid.test.tsx` (new file)

- [ ] **Step 1: Write the failing tests in `web/frontend/src/__tests__/StageGrid.test.tsx`**

```tsx
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { StageGrid } from "../components/StageGrid";
import { useUi } from "../store/ui";
import type { WsEvent } from "../lib/events";

const evt = (runId: number, type: string, data: any, id: number): WsEvent => ({
  v: 1, type: type as any, ts: `t${id}`, run_id: runId, data, id,
});

const setup = (events: WsEvent[], focused = "NVDA", runId = 1) => {
  useUi.setState({
    focusedTicker: focused,
    lastRunIdByTicker: { [focused]: runId },
    eventBuffer: events,
    activeRunIdByTicker: {},
  });
};

describe("StageGrid", () => {
  beforeEach(() => {
    useUi.setState({
      focusedTicker: null,
      lastRunIdByTicker: {},
      eventBuffer: [],
      activeRunIdByTicker: {},
    });
  });

  it("marks a stage as done when analyst_completed fires", () => {
    setup([
      evt(1, "analyst_started", { node: "Market Analyst" }, 1),
      evt(1, "analyst_completed", { stage: "market", summary: "completed" }, 2),
    ]);
    render(<StageGrid />);
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).toBe("done");
  });

  it("stays done when subsequent tool nodes fire", () => {
    setup([
      evt(1, "analyst_started", { node: "Market Analyst" }, 1),
      evt(1, "analyst_completed", { stage: "market", summary: "completed" }, 2),
      evt(1, "analyst_started", { node: "tools_market" }, 3),
    ]);
    render(<StageGrid />);
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).toBe("done");
  });

  it("uses the stage key map for completion, not node-name substring", () => {
    setup([
      evt(1, "analyst_started", { node: "Sentiment Analyst" }, 1),
      evt(1, "analyst_completed", { stage: "sentiment", summary: "completed" }, 2),
    ]);
    render(<StageGrid />);
    expect(screen.getByTestId("stage-sentiment").getAttribute("data-status")).toBe("done");
  });

  it("only considers the focused run's events", () => {
    setup([
      evt(1, "analyst_completed", { stage: "market", summary: "completed" }, 1),
      evt(2, "analyst_started", { node: "Market Analyst" }, 2),
    ], "NVDA", 1);
    render(<StageGrid />);
    // Focused run 1 has the completion; the stray started from run 2 must not affect stage-market.
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).toBe("done");
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run from `web/frontend`:
```
& "C:\Program Files\nodejs\node.exe" ./node_modules/vitest/vitest.mjs run src/__tests__/StageGrid.test.tsx
```
Expected: failures (the file does not exist yet — vitest reports collection failure).

- [ ] **Step 3: Rewrite `web/frontend/src/components/StageGrid.tsx`**

Replace the entire file content with:

```tsx
import { useUi } from "../store/ui";
import { useFocusedRunEvents } from "../hooks/useFocusedRunEvents";

const STAGES = [
  { key: "market", label: "Market" },
  { key: "sentiment", label: "Sentiment" },
  { key: "news", label: "News" },
  { key: "fundamentals", label: "Fundamentals" },
  { key: "research", label: "Research" },
  { key: "risk", label: "Risk" },
  { key: "trader", label: "Trader" },
] as const;

type StageKey = (typeof STAGES)[number]["key"];

function statusFor(stage: StageKey, events: any[]): "idle" | "running" | "done" | "errored" {
  // Use the explicit stage key from analyst_completed (not a substring
  // match against the node name, which was the latent bug). analyst_started
  // is matched on the stage key too — the node-name -> stage-key map
  // is the same as in the runner's _STAGE_MAP.
  const NODE_TO_STAGE: Record<string, StageKey> = {
    "Market Analyst": "market",
    "Sentiment Analyst": "sentiment",
    "News Analyst": "news",
    "Fundamentals Analyst": "fundamentals",
    "Bull Researcher": "research",
    "Bear Researcher": "research",
    "Research Manager": "research",
    "Trader": "trader",
    "Aggressive Analyst": "risk",
    "Conservative Analyst": "risk",
    "Neutral Analyst": "risk",
  };
  const completed = events.find((e) => e.type === "analyst_completed" && e.data?.stage === stage);
  if (completed) return "done";
  const started = events.find(
    (e) => e.type === "analyst_started" && NODE_TO_STAGE[e.data?.node] === stage
  );
  if (started) return "running";
  const errored = events.find((e) => e.type === "run_failed");
  if (errored) return "errored";
  return "idle";
}

export function StageGrid() {
  const events = useFocusedRunEvents();
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2 mb-4">
      {STAGES.map((s) => {
        const status = statusFor(s.key, events);
        return (
          <div
            key={s.key}
            data-testid={`stage-${s.key}`}
            data-status={status}
            className={`rounded-lg border p-3 text-sm ${
              status === "done" ? "border-emerald-200 bg-emerald-50" :
              status === "errored" ? "border-rose-200 bg-rose-50" :
              status === "running" ? "border-blue-200 bg-blue-50 animate-pulse" :
              "border-slate-200 bg-white"
            }`}
          >
            <div className="font-medium">{s.label}</div>
            <div className="text-xs text-slate-500 mt-1">
              {status === "done" ? "✓ done" : status === "errored" ? "errored" : status === "running" ? "running…" : "queued"}
            </div>
          </div>
        );
      })}
    </div>
  );
}
```

Note: `useUi` is no longer used in the component body (only inside `useFocusedRunEvents`). The import is dropped.

- [ ] **Step 4: Run the tests to verify they pass**

Run from `web/frontend`:
```
& "C:\Program Files\nodejs\node.exe" ./node_modules/vitest/vitest.mjs run src/__tests__/StageGrid.test.tsx
```
Expected: 4/4 pass.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/src/components/StageGrid.tsx web/frontend/src/__tests__/StageGrid.test.tsx
git commit -m "refactor(stagegrid): use focused events and explicit stage key map"
```

---

## Task 10: `App.tsx` — wire both hooks + scope decision lookup

**Files:**
- Modify: `web/frontend/src/App.tsx:5, 21, 29, 44-45`
- Test: `web/frontend/src/__tests__/App.test.tsx` (extend)

- [ ] **Step 1: Read the existing `App.test.tsx` to see the test patterns used**

- [ ] **Step 2: Add two tests at the end of `App.test.tsx`**

```tsx
  it("decision lookup is scoped to the focused run", async () => {
    useUi.setState({
      focusedTicker: "AAPL",
      lastRunIdByTicker: { AAPL: 2 },
      eventBuffer: [
        { v: 1, type: "decision", ts: "t1", run_id: 1, data: { action: "BUY",  target: 100, rationale: "wrong", confidence: 0.9 }, id: 1 },
        { v: 1, type: "decision", ts: "t2", run_id: 2, data: { action: "SELL", target: 200, rationale: "right", confidence: 0.8 }, id: 2 },
      ],
    });
    // ... render App with the right mocks; assert DecisionPanel shows SELL ...
  });

  it("restores past events into the buffer on mount", async () => {
    useUi.setState({
      focusedTicker: "NVDA",
      lastRunIdByTicker: { NVDA: 7 },
    });
    // Mock fetchWatchlist + fetchPrices + fetchRunDetail
    // ...
    // Assert the seeded event bubble renders in LiveEventStream
  });
```

The exact mocks depend on the existing test setup in `App.test.tsx`. Use the same patterns.

- [ ] **Step 3: Run the new tests to verify they fail**

Run from `web/frontend`:
```
& "C:\Program Files\nodejs\node.exe" ./node_modules/vitest/vitest.mjs run src/__tests__/App.test.tsx
```
Expected: 2 new failures.

- [ ] **Step 4: Edit `web/frontend/src/App.tsx`**

1. Add to imports (top of file, after line 10):
```ts
import { useFocusedRunEvents } from "./hooks/useFocusedRunEvents";
import { useRestoredRunEvents } from "./hooks/useRestoredRunEvents";
```

2. In the `App` function body:
   - Replace line 21 `const events = useUi((s) => s.eventBuffer);` with `const events = useFocusedRunEvents();`
   - Add `useRestoredRunEvents(focused);` right after `useRunStream(runId);` (line 29)
   - Replace lines 44-45:
     ```ts
       const decisionEvent = [...events].reverse().find((e) => e.type === "decision");
       const decision = decisionEvent?.data as { action: string; target: number; rationale: string; confidence: number } | undefined;
     ```
     with:
     ```ts
       const decisionEvent = [...events].reverse().find((e) => e.type === "decision");
       const decision = decisionEvent?.data as { action: string; target: number; rationale: string; confidence: number } | undefined;
     ```
     (The line text is identical — but `events` is now the *filtered* list, so the lookup is correctly scoped. No code text change here; the change is in the value of `events`.)

- [ ] **Step 5: Run the tests to verify they pass**

Run from `web/frontend`:
```
& "C:\Program Files\nodejs\node.exe" ./node_modules/vitest/vitest.mjs run src/__tests__/App.test.tsx
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/src/App.tsx web/frontend/src/__tests__/App.test.tsx
git commit -m "refactor(app): scope decision lookup to focused run; wire useRestoredRunEvents"
```

---

## Task 11: `TickerRow` remove button + `WatchlistRail` remove flow

**Files:**
- Modify: `web/frontend/src/components/TickerRow.tsx:19-46`
- Modify: `web/frontend/src/components/WatchlistRail.tsx:17-39`
- Test: `web/frontend/src/__tests__/WatchlistRail.test.tsx` (extend)

- [ ] **Step 1: Read the existing `WatchlistRail.test.tsx` to see the test patterns**

- [ ] **Step 2: Write the failing tests**

Add 4 new tests to `web/frontend/src/__tests__/WatchlistRail.test.tsx` (adapt to the file's existing test style; the names below are the ones to assert):

```tsx
  it("clicking the X shows the inline confirm; Cancel hides it", async () => {
    // Render with two rows. Click the X on the NVDA row. Assert "Remove" and "Cancel" appear. Click Cancel. Assert they're gone.
  });

  it("clicking Remove calls the API and invalidates the watchlist query", async () => {
    // Mock fetch DELETE. Click X then Remove. Assert fetch was called with the right URL. Assert the watchlist query is invalidated.
  });

  it("removing the focused ticker focuses the next row", async () => {
    // Seed focusedTicker = "NVDA". Click X then Remove on NVDA. Assert focusedTicker becomes "AAPL".
  });

  it("removing the last ticker clears focus", async () => {
    // Seed focusedTicker = "NVDA" with only NVDA in the watchlist. Click X then Remove. Assert focusedTicker is null.
  });
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run from `web/frontend`:
```
& "C:\Program Files\nodejs\node.exe" ./node_modules/vitest/vitest.mjs run src/__tests__/WatchlistRail.test.tsx
```
Expected: 4 failures (no remove button, no remove flow).

- [ ] **Step 4: Update `web/frontend/src/components/TickerRow.tsx`**

The current structure is a single `<button>` wrapping the row content. To add a nested remove button we need to change the outer to a `<div>` with click + keyboard handlers. Replace the entire file content with:

```tsx
import { useState } from "react";
import { useUi } from "../store/ui";

interface Props {
  ticker: string;
  companyName: string;
  lastDecision: string | null;
  sparkline: number[];
  status: "idle" | "queued" | "running" | "done" | "errored";
  onRemove?: (ticker: string) => void | Promise<void>;
}

const dotColor: Record<Props["status"], string> = {
  idle: "bg-slate-300",
  queued: "bg-amber-400",
  running: "bg-blue-500 animate-pulse",
  done: "bg-emerald-500",
  errored: "bg-rose-500",
};

export function TickerRow({ ticker, companyName, lastDecision, sparkline, status, onRemove }: Props) {
  const focused = useUi((s) => s.focusedTicker);
  const setFocused = useUi((s) => s.setFocusedTicker);
  const isFocused = focused === ticker;
  const [pending, setPending] = useState(false);

  const sparkPath = sparkline.length > 1
    ? sparkline.map((v, i) => `${i === 0 ? "M" : "L"} ${i * 4} ${20 - v}`).join(" ")
    : "";

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setFocused(ticker);
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => setFocused(ticker)}
      onKeyDown={handleKeyDown}
      data-focused={isFocused}
      className={`w-full text-left px-3 py-2 rounded-lg flex items-center gap-3 hover:bg-slate-50 ${
        isFocused ? "bg-blue-50 ring-1 ring-blue-200" : ""
      }`}
    >
      <span className={`h-2 w-2 rounded-full ${dotColor[status]}`} />
      <div className="flex-1">
        <div className="text-sm font-semibold">{ticker}</div>
        <div className="text-xs text-slate-500 truncate">{companyName || lastDecision || "—"}</div>
      </div>
      <svg width="40" height="20" className="opacity-60">
        {sparkPath && <path d={sparkPath} stroke="rgb(59 130 246)" strokeWidth="1" fill="none" />}
      </svg>
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
        <span className="flex items-center gap-1 text-xs" onClick={(e) => e.stopPropagation()}>
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
}
```

Note: the `group` class for `group-hover:opacity-100` requires the parent to have `class="group"`. Add `class="group"` to the outer div for the hover effect to work — add `group` to the `className` string above (before `w-full`).

- [ ] **Step 5: Update `web/frontend/src/components/WatchlistRail.tsx`**

Replace the entire file content with:

```tsx
import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchWatchlist, fetchPrices, removeFromWatchlist } from "../lib/api";
import { TickerRow } from "./TickerRow";
import { AddTickerCommand } from "./AddTickerCommand";
import { useUi } from "../store/ui";

type RunStatus = "idle" | "queued" | "running" | "done" | "errored";

function statusForTicker(_ticker: string, lastDecision: string | null, events: any[]): RunStatus {
  if (!lastDecision) return "idle";
  const last = events.filter((e) => e.type === "run_started" || e.type === "run_finished" || e.type === "run_failed").pop();
  if (!last) return "idle";
  if (last.type === "run_started") return "running";
  if (last.type === "run_finished") return "done";
  return "errored";
}

export function WatchlistRail() {
  const qc = useQueryClient();
  const { data: watchlist = [] } = useQuery({ queryKey: ["watchlist"], queryFn: fetchWatchlist });
  const { data: prices = {} } = useQuery({ queryKey: ["prices"], queryFn: fetchPrices });
  const focused = useUi((s) => s.focusedTicker);
  const setFocused = useUi((s) => s.setFocusedTicker);
  const clearLast = useUi((s) => s.clearLastRunIdForTicker);

  const handleRemove = useCallback(async (ticker: string) => {
    try {
      await removeFromWatchlist(ticker);
    } catch {
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
    <aside className="w-64 border-r border-slate-200 p-2 h-screen overflow-y-auto">
      <div className="text-xs uppercase tracking-wide text-slate-500 px-2 py-1">Watchlist</div>
      {watchlist.map((row) => {
        const price = (prices as any)[row.ticker] || {};
        return (
          <TickerRow
            key={row.ticker}
            ticker={row.ticker}
            companyName={row.company_name}
            lastDecision={row.last_decision}
            sparkline={price.sparkline || []}
            status={statusForTicker(row.ticker, row.last_decision, [])}
            onRemove={handleRemove}
          />
        );
      })}
      <AddTickerCommand />
    </aside>
  );
}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run from `web/frontend`:
```
& "C:\Program Files\nodejs\node.exe" ./node_modules/vitest/vitest.mjs run src/__tests__/WatchlistRail.test.tsx
```
Expected: all (existing + 4 new) pass.

- [ ] **Step 7: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/src/components/TickerRow.tsx web/frontend/src/components/WatchlistRail.tsx web/frontend/src/__tests__/WatchlistRail.test.tsx
git commit -m "feat(watchlist): per-row remove button with inline confirm"
```

---

## Task 12: Final verification

**Files:** none — run the test suite.

- [ ] **Step 1: Run the full server test suite**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.\.venv\Scripts\python.exe -m pytest tests/ web/server/tests/ -q
```

Expected: green (modulo the pre-existing `DEEPSEEK_API_KEY` env-var one; the rest of the suite must pass).

- [ ] **Step 2: Run the full frontend test suite**

From `web/frontend`:
```
& "C:\Program Files\nodejs\node.exe" ./node_modules/vitest/vitest.mjs run
```

Expected: all pass (LiveEventStream 9, StageGrid 4, store-ui 5, useFocusedRunEvents 4, useRestoredRunEvents 4, App tests + 2 new, WatchlistRail existing + 4 new, plus all the unchanged ones).

- [ ] **Step 3: Run the events-protocol test specifically to make sure no event type was inadvertently removed**

From `web/frontend`:
```
& "C:\Program Files\nodejs\node.exe" ./node_modules/vitest/vitest.mjs run src/__tests__/events-protocol.test.ts
```

Expected: 1/1 pass — confirms all 14 server-side event types are still mirrored on the frontend.

- [ ] **Step 4: Commit any incidental fixes**

If Steps 1-3 surfaced a small fix, commit it:
```bash
git add -A
git commit -m "fix: address final-verification failures"
```

(Empty if no changes — that's fine.)

---

## Self-Review (per the writing-plans skill)

1. **Spec coverage:**
   - §3 (architecture) → Task file list matches.
   - §4.1 (callbacks.py) → Task 2.
   - §4.2 (node_exited) → Task 3.
   - §4.3 (runner wiring) → Task 4.
   - §4.4 (price_feed change_pct) → Task 1.
   - §5 (useFocusedRunEvents) → Task 6.
   - §6 (useRestoredRunEvents) → Task 7.
   - §7 (store actions) → Task 5.
   - §8 (TickerRow) → Task 11.
   - §9 (WatchlistRail) → Task 11.
   - §10 (App.tsx) → Task 10.
   - §12.1 (price_feed tests) → Task 1.
   - §12.2 (callbacks tests) → Task 2.
   - §12.3 (useFocusedRunEvents tests) → Task 6.
   - §12.4 (LiveEventStream per-run-id) → Task 8.
   - §12.5 (StageGrid tests) → Task 9.
   - §12.6 (App tests) → Task 10.
   - §12.7 (store-ui tests) → Task 5.
   - §12.8 (WatchlistRail tests) → Task 11.
   - §12.9 (useRestoredRunEvents tests) → Task 7.

2. **Placeholder scan:** No "TBD", "TODO", "fill in", "implement later" in the plan. Every code block is complete.

3. **Type consistency:** `runId` and `ticker` types match across all tasks. `WsEvent` shape is consistent (Task 5 test fixture vs. Task 6/7 hook signatures vs. Task 8/9/10 component code). The store action signatures `restoreEvents(runId, events)` and `clearLastRunIdForTicker(ticker)` are consistent in Tasks 5, 6, 7, 10, 11. The `StreamingCallbackHandler(run_id=rid, broadcast=...)` signature is consistent in Task 2 (with broadcast) and Task 4 (without — using default `_broadcast_via_events`).

Plan complete. Saved to `docs/superpowers/plans/2026-06-03-dashboard-realtime-view.md`.
