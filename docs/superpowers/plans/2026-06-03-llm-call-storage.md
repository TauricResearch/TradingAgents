# LLM Call Storage & Run History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist all LLM calls (full prompt→response) per trading run so users can browse historical runs per ticker and rerun analyses.

**Architecture:** Structured `llm_call` SQLite table written by a new `CaptureCallbackHandler` that runs alongside the existing `StreamingCallbackHandler`. New REST endpoints expose per-ticker run lists and per-run LLM call data. The frontend adds a per-ticker run selector dropdown and a rerun button.

**Tech Stack:** Python/SQLModel/SQLite, FastAPI, React/Zustand, LangChain callbacks

---

## File Structure

### New files:
- `web/server/llm_calls.py` — `save_llm_call()`, `llm_calls_for_run()`, `list_runs_for_ticker()` functions (keeps db.py focused)

### Modified files:
- `web/server/db.py` +44 lines — `LlmCall` SQLModel table, `create_run_forced()` for rerun
- `web/server/callbacks.py` +90 lines — `CaptureCallbackHandler` class
- `web/server/runner.py` +10 lines — wire in `CaptureCallbackHandler` + `current_node` tracking
- `web/server/app.py` +30 lines — two new endpoints + `force` param on POST runs
- `web/server/tests/test_callbacks.py` +60 lines — `CaptureCallbackHandler` tests
- `web/server/tests/test_db.py` +35 lines — LlmCall DB function tests
- `web/server/tests/test_app.py` +30 lines — new API endpoint tests
- `web/frontend/src/store/ui.ts` +10 lines — `historicalRunIdByTicker` field + actions
- `web/frontend/src/lib/api.ts` +25 lines — `fetchTickerRuns()`, update `startRun()` with force flag
- `web/frontend/src/hooks/useFocusedRunEvents.ts` +8 lines — honor historicalRunIdByTicker
- `web/frontend/src/components/TickerHeader.tsx` +70 lines — run selector dropdown + rerun button
- `web/frontend/src/__tests__/useFocusedRunEvents.test.ts` +20 lines — historical run tests

---

### Task 1: Add LlmCall model + DB layer

**Files:**
- Modify: `web/server/db.py` — add `LlmCall` model
- Create: `web/server/llm_calls.py` — DB access functions
- Test: `web/server/tests/test_db.py` — add LlmCall tests

- [ ] **Step 1: Add `LlmCall` SQLModel to db.py**

Append to `web/server/db.py` after the `Event` class:

```python
class LlmCall(SQLModel, table=True):
    __tablename__ = "llm_call"
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(index=True)
    ticker: str = Field(index=True)
    node_name: str = ""
    started_at: datetime
    model: str
    prompt_text: str
    response_text: str
    tool_calls_json: str = "[]"
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    duration_ms: int = 0
```

- [ ] **Step 2: Add `create_run` with force flag**

In `db.py`, modify `create_run` to accept a `force: bool = False` parameter:

```python
def create_run(ticker: str, idempotency_key: str, force: bool = False) -> Optional[int]:
    with get_session() as s:
        if not force:
            existing = s.exec(
                select(Run).where(Run.idempotency_key == idempotency_key, Run.status != "running")
            ).first()
            if existing is not None:
                return existing.id
        row = Run(
            ticker=ticker,
            started_at=datetime.now(timezone.utc),
            status="running",
            idempotency_key=idempotency_key,
        )
        s.add(row)
        s.commit()
        s.refresh(row)
        return row.id
```

- [ ] **Step 3: Create `web/server/llm_calls.py`**

```python
"""Persistence functions for LlmCall records."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import select, desc

from web.server.db import get_session, LlmCall


def save_llm_call(
    *,
    run_id: int,
    ticker: str,
    node_name: str,
    started_at: datetime,
    model: str,
    prompt_text: str,
    response_text: str,
    tool_calls: list | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
    duration_ms: int = 0,
) -> int:
    with get_session() as s:
        row = LlmCall(
            run_id=run_id,
            ticker=ticker,
            node_name=node_name,
            started_at=started_at,
            model=model,
            prompt_text=prompt_text,
            response_text=response_text,
            tool_calls_json=json.dumps(tool_calls or []),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
        )
        s.add(row)
        s.commit()
        s.refresh(row)
        return row.id


def llm_calls_for_run(run_id: int) -> list[LlmCall]:
    with get_session() as s:
        return list(
            s.exec(
                select(LlmCall)
                .where(LlmCall.run_id == run_id)
                .order_by(LlmCall.started_at)
            )
        )


def list_runs_for_ticker(ticker: str, limit: int = 50) -> list[dict]:
    """Return runs for a ticker as lightweight dicts (no events/llm_calls)."""
    from web.server.db import Run, get_session
    with get_session() as s:
        rows = s.exec(
            select(Run)
            .where(Run.ticker == ticker)
            .order_by(desc(Run.started_at))
            .limit(limit)
        )
        return [
            {
                "id": r.id,
                "ticker": r.ticker,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "status": r.status,
                "decision_action": r.decision_action,
                "decision_target": r.decision_target,
                "decision_rationale": r.decision_rationale,
                "decision_confidence": r.decision_confidence,
            }
            for r in rows
        ]
```

- [ ] **Step 4: Write LlmCall DB tests in `web/server/tests/test_db.py`**

Append after existing tests:

```python
def test_llm_call_crud(temp_db):
    from web.server.llm_calls import save_llm_call, llm_calls_for_run, list_runs_for_ticker

    rid = db.create_run(ticker="NVDA", idempotency_key="NVDA:2026-06-01")

    save_llm_call(
        run_id=rid,
        ticker="NVDA",
        node_name="Market Analyst",
        started_at=datetime.now(timezone.utc),
        model="gpt-4",
        prompt_text="user: hello",
        response_text="world",
        tool_calls=[{"name": "get_price"}],
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        duration_ms=1234,
    )

    calls = llm_calls_for_run(rid)
    assert len(calls) == 1
    c = calls[0]
    assert c.ticker == "NVDA"
    assert c.node_name == "Market Analyst"
    assert c.model == "gpt-4"
    assert c.prompt_text == "user: hello"
    assert c.response_text == "world"
    assert c.total_tokens == 15

    rows = list_runs_for_ticker("NVDA")
    assert len(rows) >= 1
    assert rows[0]["ticker"] == "NVDA"
```

- [ ] **Step 5: Run tests**

```
cd web
python -m pytest server/tests/test_db.py::test_llm_call_crud -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```
git add web/server/db.py web/server/llm_calls.py web/server/tests/test_db.py
git commit -m "feat: add LlmCall model and persistence layer"
```

---

### Task 2: Add CaptureCallbackHandler

**Files:**
- Modify: `web/server/callbacks.py` — add `CaptureCallbackHandler`
- Test: `web/server/tests/test_callbacks.py` — add tests

- [ ] **Step 1: Write failing tests in `test_callbacks.py`**

Append to file:

```python
from datetime import datetime, timezone
from web.server.callbacks import CaptureCallbackHandler


@pytest.mark.unit
class TestCaptureCallbackHandler:
    def test_captures_full_prompt_and_response(self):
        calls = []
        handler = CaptureCallbackHandler(run_id=42, ticker="NVDA", save_call=calls.append)

        from uuid import uuid4
        rid = uuid4()
        handler.on_chat_model_start(
            {"name": "ChatOpenAI"},
            [[HumanMessage(content="What's the price?")]],
            run_id=rid,
        )
        # Simulate on_llm_end with a proper LLMResult
        from unittest.mock import MagicMock
        gen = MagicMock()
        chat = MagicMock()
        chat.message = AIMessage(content="The price is 900.", tool_calls=[])
        gen.__iter__ = lambda self: iter([chat])
        result = MagicMock()
        result.generations = [gen]
        result.llm_output = {"model_name": "gpt-4", "token_usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}}

        handler.on_llm_end(result, run_id=rid)

        assert len(calls) == 1
        call = calls[0]
        assert call["run_id"] == 42
        assert call["ticker"] == "NVDA"
        assert "What's the price?" in call["prompt_text"]
        assert call["response_text"] == "The price is 900."
        assert call["total_tokens"] == 8
        assert call["input_tokens"] == 5
        assert call["output_tokens"] == 3

    def test_multiple_llm_calls_tracked_independently(self):
        calls = []
        handler = CaptureCallbackHandler(run_id=42, ticker="NVDA", save_call=calls.append)
        from uuid import uuid4
        rid1, rid2 = uuid4(), uuid4()

        handler.on_chat_model_start({"name": "ChatOpenAI"}, [[HumanMessage(content="first call")]], run_id=rid1)
        handler.on_chat_model_start({"name": "ChatOpenAI"}, [[HumanMessage(content="second call")]], run_id=rid2)
        gen = MagicMock(); chat = MagicMock()
        chat.message = AIMessage(content="first response")
        gen.__iter__ = lambda self: iter([chat])
        r1 = MagicMock(); r1.generations = [gen]; r1.llm_output = {"token_usage": {"total_tokens": 1}}
        handler.on_llm_end(r1, run_id=rid1)

        chat2 = MagicMock()
        chat2.message = AIMessage(content="second response")
        gen2 = MagicMock()
        gen2.__iter__ = lambda self: iter([chat2])
        r2 = MagicMock(); r2.generations = [gen2]; r2.llm_output = {"token_usage": {"total_tokens": 2}}
        handler.on_llm_end(r2, run_id=rid2)

        assert len(calls) == 2
        assert calls[0]["response_text"] == "first response"
        assert calls[1]["response_text"] == "second response"

    def test_handles_tool_calls_in_response(self):
        calls = []
        handler = CaptureCallbackHandler(run_id=42, ticker="NVDA", save_call=calls.append)
        from uuid import uuid4
        rid = uuid4()
        handler.on_chat_model_start({"name": "ChatOpenAI"}, [[HumanMessage(content="check price")]], run_id=rid)
        gen = MagicMock(); chat = MagicMock()
        chat.message = AIMessage(content="", tool_calls=[{"name": "get_price", "args": {}, "id": "call_1"}])
        gen.__iter__ = lambda self: iter([chat])
        r = MagicMock(); r.generations = [gen]; r.llm_output = {}
        handler.on_llm_end(r, run_id=rid)
        assert len(calls) == 1
        assert '"get_price"' in calls[0]["tool_calls_json"]
```

- [ ] **Step 2: Run tests to confirm failure**

```
cd web
python -m pytest server/tests/test_callbacks.py::TestCaptureCallbackHandler -v
```
Expected: FAIL (CaptureCallbackHandler not defined)

- [ ] **Step 3: Implement CaptureCallbackHandler in `callbacks.py`**

Append to `callbacks.py`:

```python
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional


def _save_llm_call_default(**kw) -> None:
    """Production default: persist via the llm_calls module."""
    from web.server.llm_calls import save_llm_call
    save_llm_call(**kw)


class CaptureCallbackHandler(BaseCallbackHandler):
    """Accumulates full LLM prompt→response pairs and persists them.

    Attach alongside StreamingCallbackHandler in the graph's callbacks
    list. Uses ``run_id`` (LangChain's per-call UUID) to correlate
    ``on_chat_model_start`` with ``on_llm_end``.

    The handler does NOT emit dashboard events — it writes directly to
    the ``llm_call`` table via the injected ``save_call`` callable.
    """

    def __init__(
        self,
        *,
        run_id: int,
        ticker: str,
        save_call: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self.run_id = run_id
        self.ticker = ticker
        self._save_call = save_call or _save_llm_call_default
        # LangChain per-call run_id -> pending data
        self._pending: dict[uuid.UUID, dict[str, Any]] = {}
        # Set by the runner's event_callback before each node executes
        self.current_node: Optional[str] = None

    def on_chat_model_start(
        self,
        serialized: dict,
        messages: list,
        *,
        run_id: uuid.UUID,
        **kw: Any,
    ) -> None:
        prompt_parts: list[str] = []
        for batch in messages or []:
            for msg in batch or []:
                role = str(getattr(msg, "type", "unknown"))
                content = str(getattr(msg, "content", "") or "")
                prompt_parts.append(f"{role}: {content}")
        prompt_text = "\n\n".join(prompt_parts)

        self._pending[run_id] = {
            "model": serialized.get("name", "unknown"),
            "prompt_text": prompt_text,
            "started_at": datetime.now(timezone.utc),
        }

    def on_llm_end(self, response: Any, *, run_id: uuid.UUID, **kw: Any) -> None:
        pending = self._pending.pop(run_id, None)
        if pending is None:
            return

        # Extract response text + tool calls
        response_text = ""
        tool_calls: list = []
        try:
            for gen in response.generations:
                for chat in gen:
                    msg = getattr(chat, "message", None)
                    if msg is None:
                        text = str(getattr(chat, "text", "") or "")
                        response_text += text
                        continue
                    content = str(getattr(msg, "content", "") or "")
                    response_text += content
                    tool_calls.extend(getattr(msg, "tool_calls", None) or [])
        except Exception:
            pass

        # Extract token usage (handle both older and newer LLM result shapes)
        input_tokens = output_tokens = total_tokens = 0
        model = pending["model"]
        try:
            llm_output = getattr(response, "llm_output", None) or {}
            model = llm_output.get("model_name", model)
            usage = llm_output.get("token_usage", None) or {}
            input_tokens = usage.get("prompt_tokens", usage.get("input_tokens", 0))
            output_tokens = usage.get("completion_tokens", usage.get("output_tokens", 0))
            total_tokens = usage.get("total_tokens", 0)
        except Exception:
            pass

        started_at: datetime = pending["started_at"]
        duration_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)

        self._save_call({
            "run_id": self.run_id,
            "ticker": self.ticker,
            "node_name": self.current_node or "",
            "started_at": started_at,
            "model": model,
            "prompt_text": pending["prompt_text"],
            "response_text": response_text,
            "tool_calls": tool_calls,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "duration_ms": duration_ms,
        })
```

- [ ] **Step 4: Run tests to confirm they pass**

```
cd web
python -m pytest server/tests/test_callbacks.py::TestCaptureCallbackHandler -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```
git add web/server/callbacks.py web/server/tests/test_callbacks.py
git commit -m "feat: add CaptureCallbackHandler for LLM call persistence"
```

---

### Task 3: Wire CaptureCallbackHandler into the runner

**Files:**
- Modify: `web/server/runner.py`

- [ ] **Step 1: Edit `runner.py` — create both handlers and track current_node**

In `_run_one`, replace the single handler with both handlers and add `current_node` tracking:

```python
# In _run_one, replace:
from web.server.callbacks import StreamingCallbackHandler
handler = StreamingCallbackHandler(run_id=rid)
graph = build_graph(callbacks=[handler])

# With:
from web.server.callbacks import StreamingCallbackHandler, CaptureCallbackHandler
handler = StreamingCallbackHandler(run_id=rid)
capture = CaptureCallbackHandler(run_id=rid, ticker=run.ticker)
graph = build_graph(callbacks=[handler, capture])
```

Then in the `cb` function, add node tracking at the top:

```python
def cb(node_name: str, payload: dict) -> None:
    if db.get_run(rid).cancel_requested:
        raise _CancelSentinel()
    if node_name == "node_entered":
        capture.current_node = payload.get("node", "")
    elif node_name == "node_exited":
        # ... rest unchanged
```

- [ ] **Step 2: Run existing runner tests**

```
cd web
python -m pytest server/tests/test_runner.py -v
```
Expected: PASS (no behavior change, just new side-effect handler)

- [ ] **Step 3: Commit**

```
git add web/server/runner.py
git commit -m "feat: wire CaptureCallbackHandler into runner with node tracking"
```

---

### Task 4: Add new API endpoints

**Files:**
- Modify: `web/server/app.py`
- Test: `web/server/tests/test_app.py`

- [ ] **Step 1: Write API tests in `test_app.py`**

Append to file:

```python
from datetime import datetime, timezone


def test_ticker_runs_endpoint(client, temp_db):
    """GET /api/tickers/{ticker}/runs returns runs for that ticker."""
    rid = db.create_run(ticker="NVDA", idempotency_key="NVDA:2026-06-01")
    db.mark_run_done(rid, decision_action="BUY", decision_target=260.0, decision_rationale="good", decision_confidence=0.8)
    rid2 = db.create_run(ticker="AAPL", idempotency_key="AAPL:2026-06-01")
    db.mark_run_done(rid2, decision_action="HOLD", decision_target=None, decision_rationale="", decision_confidence=0.5)

    r = client.get("/api/tickers/NVDA/runs")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1
    assert rows[0]["ticker"] == "NVDA"

    r = client.get("/api/tickers/AAPL/runs")
    rows = r.json()
    assert rows[0]["ticker"] == "AAPL"

    r = client.get("/api/tickers/UNKNOWN/runs")
    assert r.status_code == 200
    assert r.json() == []


def test_force_run_creates_new_run(client, temp_db, monkeypatch):
    """POST /api/runs with force=true bypasses idempotency."""
    from web.server import runner
    monkeypatch.setattr(
        runner,
        "enqueue",
        lambda ticker, *, idempotency_key, force: db.create_run(ticker=ticker, idempotency_key=idempotency_key, force=force),
    )
    r1 = client.post("/api/runs", json={"ticker": "NVDA", "force": True})
    assert r1.status_code == 201
    rid1 = r1.json()["run_id"]

    r2 = client.post("/api/runs", json={"ticker": "NVDA", "force": True})
    assert r2.status_code == 201
    rid2 = r2.json()["run_id"]

    assert rid1 != rid2  # force=true means new run every time
```

- [ ] **Step 2: Implement endpoints in `app.py`**

Add new import at top:

```python
from web.server.llm_calls import llm_calls_for_run, list_runs_for_ticker
```

Update `RunIn` model to accept optional force:

```python
class RunIn(BaseModel):
    ticker: str
    force: bool = False
```

Replace the existing `create_run` endpoint:

```python
@app.post("/api/runs", status_code=201)
def create_run(row: RunIn):
    from datetime import date
    rid = runner.enqueue(
        row.ticker.upper(),
        idempotency_key=f"{row.ticker.upper()}:{date.today().isoformat()}",
        force=row.force,
    )
    return {"run_id": rid}
```

Add new endpoints (before the WebSocket routes):

```python
@app.get("/api/tickers/{ticker}/runs")
def ticker_runs(ticker: str):
    return list_runs_for_ticker(ticker.upper())
```

Update `get_run` to include `llm_calls`:

```python
@app.get("/api/runs/{run_id}")
def get_run(run_id: int):
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    llm_calls = llm_calls_for_run(run_id)
    return {
        "run": _run_to_dict(run),
        "events": [_event_to_dict(e) for e in db.events_for_run(run_id)],
        "llm_calls": [
            {
                "id": c.id,
                "node_name": c.node_name,
                "model": c.model,
                "prompt_text": c.prompt_text,
                "response_text": c.response_text,
                "tool_calls": json.loads(c.tool_calls_json),
                "input_tokens": c.input_tokens,
                "output_tokens": c.output_tokens,
                "total_tokens": c.total_tokens,
                "duration_ms": c.duration_ms,
                "started_at": c.started_at.isoformat() if c.started_at else None,
            }
            for c in llm_calls
        ],
    }
```

Add `force` param to `runner.enqueue` signature in `runner.py`:

```python
def enqueue(ticker: str, *, idempotency_key: str, force: bool = False) -> int:
    if _queue is None:
        raise RuntimeError("runner.start() must be called before enqueue()")
    rid = db.create_run(ticker=ticker, idempotency_key=idempotency_key, force=force)
    _queue.put_nowait(rid)
    return rid
```

- [ ] **Step 3: Run tests**

```
cd web
python -m pytest server/tests/test_app.py::test_ticker_runs_endpoint server/tests/test_app.py::test_force_run_creates_new_run -v
```
Expected: PASS. Also run full suite: `python -m pytest server/tests/test_app.py -v` — all PASS.

- [ ] **Step 4: Commit**

```
git add web/server/app.py web/server/runner.py web/server/tests/test_app.py
git commit -m "feat: add per-ticker runs endpoint + force run support"
```

---

### Task 5: Frontend store + API additions

**Files:**
- Modify: `web/frontend/src/store/ui.ts`
- Modify: `web/frontend/src/lib/api.ts`
- Modify: `web/frontend/src/hooks/useFocusedRunEvents.ts`
- Test: `web/frontend/src/__tests__/useFocusedRunEvents.test.ts`

- [ ] **Step 1: Update `api.ts` — add `fetchTickerRuns()`, update `startRun()`**

Add new interfaces and functions:

```typescript
export interface RunRow {
  // ... existing fields plus:
}

export interface LlmCallRow {
  id: number;
  node_name: string;
  model: string;
  prompt_text: string;
  response_text: string;
  tool_calls: unknown[];
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  duration_ms: number;
  started_at: string | null;
}

export interface RunDetail {
  run: RunRow;
  events: Array<{ id: number; type: string; ts: string | null; data: unknown }>;
  llm_calls: LlmCallRow[];
}

export async function startRun(ticker: string, force = false): Promise<{ run_id: number }> {
  const r = await fetch(`${base}/api/runs`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ticker, force }),
  });
  if (!r.ok) throw new Error(`start ${r.status}`);
  return r.json();
}

export async function fetchTickerRuns(ticker: string): Promise<RunRow[]> {
  const r = await fetch(`${base}/api/tickers/${encodeURIComponent(ticker)}/runs`);
  if (!r.ok) throw new Error(`ticker runs ${r.status}`);
  return r.json();
}

export async function fetchRunDetail(runId: number): Promise<RunDetail> {
  const r = await fetch(`${base}/api/runs/${runId}`);
  if (!r.ok) throw new Error(`run ${r.status}`);
  return r.json();
}
```

- [ ] **Step 2: Update `store/ui.ts` — add `historicalRunIdByTicker`**

Add to the `UiState` interface:

```typescript
// Run id the user explicitly selected from the run history dropdown.
// When set, overrides `lastRunIdByTicker` for event filtering.
historicalRunIdByTicker: Record<string, number | null>;
```

Add state + actions in the store creator:

```typescript
historicalRunIdByTicker: {},

setHistoricalRunForTicker: (ticker, runId) =>
  set((s) => ({ historicalRunIdByTicker: { ...s.historicalRunIdByTicker, [ticker]: runId } })),
clearHistoricalRun: (ticker) =>
  set((s) => ({ historicalRunIdByTicker: { ...s.historicalRunIdByTicker, [ticker]: null } })),
```

- [ ] **Step 3: Update `useFocusedRunEvents.ts`**

Change to check `historicalRunIdByTicker` first, fall back to `lastRunIdByTicker`:

```typescript
export function useFocusedRunEvents(): WsEvent[] {
  const focused = useUi((s) => s.focusedTicker);
  const lastRunId = useUi((s) =>
    focused ? s.lastRunIdByTicker[focused] ?? null : null
  );
  const historicalRunId = useUi((s) =>
    focused ? s.historicalRunIdByTicker[focused] ?? null : null
  );
  const events = useUi((s) => s.eventBuffer);
  const runId = historicalRunId ?? lastRunId;
  return useMemo(() => {
    if (focused == null || runId == null) return [];
    return events.filter((e) => e.run_id === runId);
  }, [focused, runId, events]);
}
```

- [ ] **Step 4: Update frontend tests in `useFocusedRunEvents.test.ts`**

Add to the test file:

```typescript
it("prefers historicalRunIdByTicker over lastRunIdByTicker", () => {
  useUi.setState({
    focusedTicker: "NVDA",
    lastRunIdByTicker: { NVDA: 1 },
    historicalRunIdByTicker: { NVDA: 3 },
    eventBuffer: [evt(1, "analyst_started", 1), evt(3, "analyst_started", 3)],
  });
  const { result } = renderHook(() => useFocusedRunEvents());
  expect(result.current).toHaveLength(1);
  expect(result.current[0].run_id).toBe(3);
});

it("falls back to lastRunIdByTicker when historicalRunIdByTicker is null", () => {
  useUi.setState({
    focusedTicker: "NVDA",
    lastRunIdByTicker: { NVDA: 1 },
    historicalRunIdByTicker: { NVDA: null },
    eventBuffer: [evt(1, "analyst_started", 1), evt(3, "analyst_started", 3)],
  });
  const { result } = renderHook(() => useFocusedRunEvents());
  expect(result.current).toHaveLength(1);
  expect(result.current[0].run_id).toBe(1);
});
```

- [ ] **Step 5: Run frontend tests**

```
cd web/frontend
npx vitest run src/__tests__/useFocusedRunEvents.test.ts
```
Expected: PASS

- [ ] **Step 6: Commit**

```
git add web/frontend/src/store/ui.ts web/frontend/src/lib/api.ts web/frontend/src/hooks/useFocusedRunEvents.ts web/frontend/src/__tests__/useFocusedRunEvents.test.ts
git commit -m "feat: add historical run support to frontend store and hooks"
```

---

### Task 6: Per-ticker run selector + rerun button

**Files:**
- Modify: `web/frontend/src/components/TickerHeader.tsx`
- Create: `web/frontend/src/__tests__/TickerHeader.test.tsx`

- [ ] **Step 1: Rewrite `TickerHeader.tsx` to add run selector + rerun**

Full replacement (preserves existing cancel/live-run behavior, adds dropdown and rerun):

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { startRun, cancelRun, fetchTickerRuns, fetchRunDetail } from "../lib/api";
import { useUi } from "../store/ui";
import type { RunRow } from "../lib/api";

interface Props { ticker: string; price?: number; changePct?: number; }

export function TickerHeader({ ticker, price, changePct }: Props) {
  const qc = useQueryClient();
  const activeRunId = useUi((s) => s.activeRunIdByTicker[ticker] ?? null);
  const historicalRunId = useUi((s) => s.historicalRunIdByTicker[ticker] ?? null);
  const setActiveRunIdForTicker = useUi((s) => s.setActiveRunIdForTicker);
  const setLastRunIdForTicker = useUi((s) => s.setLastRunIdForTicker);
  const clearActiveRunForTicker = useUi((s) => s.clearActiveRunForTicker);
  const clearBuffer = useUi((s) => s.clearBuffer);
  const setHistoricalRunForTicker = useUi((s) => s.setHistoricalRunForTicker);
  const clearHistoricalRun = useUi((s) => s.clearHistoricalRun);
  const restoreEvents = useUi((s) => s.restoreEvents);

  // Fetch runs for this ticker
  const { data: tickerRuns = [] } = useQuery({
    queryKey: ["ticker-runs", ticker],
    queryFn: () => fetchTickerRuns(ticker),
  });

  const start = useMutation({
    mutationFn: () => startRun(ticker, true), // force=true for rerun
    onSuccess: ({ run_id }) => {
      clearBuffer();
      clearHistoricalRun(ticker);
      setActiveRunIdForTicker(ticker, run_id);
      setLastRunIdForTicker(ticker, run_id);
      qc.invalidateQueries({ queryKey: ["runs", "list"] });
      qc.invalidateQueries({ queryKey: ["ticker-runs", ticker] });
    },
  });

  const cancel = useMutation({
    mutationFn: () => cancelRun(activeRunId!),
    onSuccess: () => clearActiveRunForTicker(ticker),
  });

  const isRunning = !!activeRunId;

  const handleRunSelect = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    if (!val) return;
    const runId = Number(val);
    const detail = await fetchRunDetail(runId);
    clearBuffer();
    clearHistoricalRun(ticker);
    // Clear active run if we're switching away from it
    if (activeRunId && activeRunId !== runId) {
      clearActiveRunForTicker(ticker);
    }
    setHistoricalRunForTicker(ticker, runId);
    restoreEvents(runId, detail.events.map((ev) => ({
      v: 1,
      type: ev.type as any,
      ts: ev.ts ?? "",
      run_id: runId,
      data: ev.data,
      id: ev.id,
    })));
    setLastRunIdForTicker(ticker, runId);
  };

  return (
    <div className="flex items-center justify-between mb-4">
      <div className="flex items-center gap-4">
        <div>
          <h2 className="text-2xl font-semibold">{ticker}</h2>
          <p className="text-sm text-slate-500">
            {price != null ? `$${price.toFixed(2)}` : "—"}
            {changePct != null && (
              <span className={changePct >= 0 ? "text-emerald-600 ml-2" : "text-rose-600 ml-2"}>
                {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
              </span>
            )}
          </p>
        </div>
        {tickerRuns.length > 0 && (
          <select
            value={historicalRunId ?? ""}
            onChange={handleRunSelect}
            className="text-sm border border-slate-300 rounded px-2 py-1"
          >
            <option value="">Latest run</option>
            {tickerRuns.map((r: RunRow) => (
              <option key={r.id} value={r.id}>
                #{r.id} · {r.started_at?.slice(0, 10) ?? "?"} · {r.status}
                {r.decision_action ? ` · ${r.decision_action}` : ""}
              </option>
            ))}
          </select>
        )}
      </div>
      <div className="flex gap-2">
        <button
          disabled={isRunning || start.isPending}
          onClick={() => start.mutate()}
          className="px-3 py-1.5 text-sm font-medium rounded-md bg-blue-600 text-white disabled:opacity-50"
        >
          {start.isPending ? "Starting…" : "Run analysis"}
        </button>
        {isRunning && (
          <button
            onClick={() => cancel.mutate()}
            className="px-3 py-1.5 text-sm font-medium rounded-md border border-slate-300"
          >
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Write component test in `__tests__/TickerHeader.test.tsx`**

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TickerHeader } from "../components/TickerHeader";
import { useUi } from "../store/ui";

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("TickerHeader", () => {
  beforeEach(() => {
    useUi.setState({
      activeRunIdByTicker: {},
      lastRunIdByTicker: {},
      historicalRunIdByTicker: {},
      eventBuffer: [],
      focusedTicker: null,
    });
  });

  it("renders ticker name and price", () => {
    render(<Wrapper><TickerHeader ticker="NVDA" price={150} changePct={2.5} /></Wrapper>);
    expect(screen.getByText("NVDA")).toBeDefined();
    expect(screen.getByText("$150.00")).toBeDefined();
  });

  it("renders Run analysis button", () => {
    render(<Wrapper><TickerHeader ticker="NVDA" /></Wrapper>);
    expect(screen.getByText("Run analysis")).toBeDefined();
  });

  it("shows run selector dropdown when runs exist", async () => {
    // Mock fetch to return runs
    const origFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([{ id: 1, ticker: "NVDA", started_at: "2026-06-03T00:00:00Z", status: "done", decision_action: "BUY" }]),
    });
    render(<Wrapper><TickerHeader ticker="NVDA" /></Wrapper>);
    // Wait for query to settle
    await screen.findByText("Latest run");
    globalThis.fetch = origFetch;
  });
});
```

- [ ] **Step 3: Run test**

```
cd web/frontend
npx vitest run src/__tests__/TickerHeader.test.tsx
```
Expected: PASS

- [ ] **Step 4: Commit**

```
git add web/frontend/src/components/TickerHeader.tsx web/frontend/src/__tests__/TickerHeader.test.tsx
git commit -m "feat: add per-ticker run selector and rerun button to TickerHeader"
```

---

## Self-Review Checklist

1. **Spec coverage:** Every spec requirement has a task:
   - LlmCall table → Task 1
   - CaptureCallbackHandler → Task 2
   - Wire into runner → Task 3
   - New API endpoints → Task 4
   - Frontend store/hooks → Task 5
   - Run selector UI + rerun → Task 6
   - Tests for each → embedded in every task

2. **Placeholder scan:** No TBDs, TODOs, "implement later", or "add error handling". Every code block is complete.

3. **Type consistency:** `save_llm_call` kwargs match in llm_calls.py and capture handler. `list_runs_for_ticker` returns dicts matching the frontend `RunRow` interface. `fetchRunDetail` returns `llm_calls` array. `force` param flows through all layers.
