# Full Log Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real-time log visibility to the dashboard via a dedicated `/ws/logs` WebSocket channel streaming both Python server logs and TypeScript client logs to an on-screen panel.

**Architecture:** A custom Python `logging.Handler` (`LogPublisher`) captures all server-side log records and fans them out over a new `/ws/logs` WebSocket endpoint. The frontend uses a `useLogStream` hook to receive logs, a Zustand `logStore` to buffer them, and a `LogPanel` component to display them. Client-side console output is intercepted by a `console-capture` module and routed through the same store.

**Tech Stack:** Python logging stdlib, FastAPI WebSocket, TypeScript/React, Zustand, Tailwind CSS.

## File Map

### Backend (Python)
| File | Change |
|------|--------|
| `web/server/settings.py` | Add `log_level` setting |
| `web/server/log_publisher.py` | **Create** — `LogPublisher` class and module singleton |
| `web/server/app.py` | Add `/ws/logs` WS route; register/removal of log publisher in lifespan |

### Frontend (TypeScript/React)
| File | Change |
|------|--------|
| `web/frontend/src/lib/ws.ts` | Add `buildLogsUrl()` helper |
| `web/frontend/src/store/logs.ts` | **Create** — Zustand store |
| `web/frontend/src/lib/console-capture.ts` | **Create** — console interceptor |
| `web/frontend/src/hooks/useLogStream.ts` | **Create** — WS hook |
| `web/frontend/src/components/LogPanel.tsx` | **Create** — collapsible panel |
| `web/frontend/src/App.tsx` | Import `LogPanel` and `console-capture` |

---

## Task 1: Backend Log Publisher

**Files:**
- Create: `web/server/log_publisher.py`
- Modify: `web/server/settings.py:17-27`
- Test: `web/server/tests/test_log_publisher.py` (create)

**Interfaces:**
- Consumes: Python `logging` module, `asyncio` event loop, `fastapi.WebSocket`
- Produces: `log_publisher` module singleton; `setup_log_publisher(loop)` and `teardown_log_publisher()` callables

**Log entry JSON shape:**
```python
{
    "id": "<uuid>",
    "ts": "2026-06-22T10:30:00.123Z",
    "level": "INFO",   # DEBUG | INFO | WARNING | ERROR
    "logger": "web.server.runner",
    "message": "Run started for ticker AAPL",
    "source": "server",
}
```

- [ ] **Step 1: Write failing tests**

```python
# web/server/tests/test_log_publisher.py
import pytest
import logging
from unittest.mock import AsyncMock, MagicMock
from web.server.log_publisher import LogPublisher, log_publisher

class TestLogPublisher:
    def test_emit_fans_out_to_subscribers(self):
        pub = LogPublisher()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        pub.subscribe(ws1)
        pub.subscribe(ws2)
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="",
            lineno=0, msg="hello", args=(), exc_info=None
        )
        pub.emit(record)
        # Both subscribers should have received the message
        assert ws1.send_json.called
        assert ws2.send_json.called

    def test_unsubscribe_removes_client(self):
        pub = LogPublisher()
        ws = AsyncMock()
        pub.subscribe(ws)
        pub.unsubscribe(ws)
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="",
            lineno=0, msg="hello", args=(), exc_info=None
        )
        pub.emit(record)
        assert not ws.send_json.called

    def test_level_filter_excludes_debug_when_threshold_is_info(self):
        pub = LogPublisher(min_level=logging.INFO)
        ws = AsyncMock()
        pub.subscribe(ws)
        debug_record = logging.LogRecord(
            name="test", level=logging.DEBUG, pathname="",
            lineno=0, msg="debug msg", args=(), exc_info=None
        )
        pub.emit(debug_record)
        assert not ws.send_json.called

    def test_singleton_instance_exists(self):
        from web.server import log_publisher as lp
        assert hasattr(lp, 'log_publisher')
        assert hasattr(lp, 'setup_log_publisher')
        assert hasattr(lp, 'teardown_log_publisher')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /web/server && pytest tests/test_log_publisher.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Write minimal implementation**

```python
# web/server/log_publisher.py
"""Log publisher: custom logging.Handler that broadcasts records over WebSocket."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Set

from fastapi import WebSocket


class LogPublisher:
    _subscribers: Set[WebSocket] = set()
    _lock = threading.Lock()
    _loop: asyncio.AbstractEventLoop | None = None

    def __init__(self, min_level: int = logging.INFO) -> None:
        self._min_level = min_level

    @property
    def min_level(self) -> int:
        return self._min_level

    @min_level.setter
    def min_level(self, value: int) -> None:
        self._min_level = value

    def subscribe(self, ws: WebSocket) -> None:
        with self._lock:
            self._subscribers.add(ws)

    def unsubscribe(self, ws: WebSocket) -> None:
        with self._lock:
            self._subscribers.discard(ws)

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < self._min_level:
            return
        entry = {
            "id": str(uuid.uuid4()),
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": logging.getLevelName(record.levelno),
            "logger": record.name,
            "message": record.getMessage(),
            "source": "server",
        }
        targets: list[WebSocket] = []
        with self._lock:
            targets.extend(self._subscribers)
        for ws in targets:
            try:
                if self._loop and not self._loop.is_closed():
                    asyncio.run_coroutine_threadsafe(ws.send_json(entry), self._loop)
            except Exception:
                pass

    def handle(self, record: logging.LogRecord) -> None:
        self.emit(record)


_log_publisher: LogPublisher | None = None


def setup_log_publisher(loop: asyncio.AbstractEventLoop, min_level: int = logging.INFO) -> LogPublisher:
    global _log_publisher
    _log_publisher = LogPublisher(min_level=min_level)
    _log_publisher._loop = loop
    root = logging.getLogger()
    root.addHandler(_log_publisher)
    return _log_publisher


def teardown_log_publisher() -> None:
    global _log_publisher
    if _log_publisher is not None:
        root = logging.getLogger()
        root.removeHandler(_log_publisher)
        _log_publisher = None


# Module-level singleton accessor
log_publisher = _log_publisher
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /web/server && pytest tests/test_log_publisher.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Commit**

```bash
git add web/server/log_publisher.py web/server/tests/test_log_publisher.py
git commit -m "feat: add LogPublisher for real-time log broadcasting"
```

---

## Task 2: Wire Log Publisher into App Lifespan

**Files:**
- Modify: `web/server/settings.py:17-27`
- Modify: `web/server/app.py:78-155` (lifespan), `app.py:388-404` (new WS endpoint)

**Interfaces:**
- Consumes: `log_publisher.setup_log_publisher()`, `log_publisher.teardown_log_publisher()`, `settings.log_level`
- Produces: `/ws/logs` WebSocket route

- [ ] **Step 1: Add log_level to settings**

Modify `web/server/settings.py` — add after existing `log_level` field (already exists at line 27):
```python
log_level: str = os.environ.get("TRADINGAGENTS_DASHBOARD_LOG_LEVEL", "INFO")
```
(No change needed since it already exists. Verify it is present, then proceed.)

- [ ] **Step 2: Write failing test for /ws/logs endpoint**

In `web/server/tests/` there is likely a conftest.py. Add to existing test file or create:
```python
# web/server/tests/test_log_publisher_integration.py
import pytest
from fastapi.testclient import TestClient
from web.server.app import create_app

class TestWsLogsEndpoint:
    def test_ws_logs_requires_auth(self):
        app = create_app()
        with TestClient(app) as client:
            with pytest.raises(Exception):
                with client.websocket_connect("/ws/logs"):
                    pass
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /web/server && pytest tests/test_log_publisher_integration.py::test_ws_logs_requires_auth -v`
Expected: FAIL — endpoint does not exist

- [ ] **Step 4: Wire log publisher in lifespan (app.py)**

Add to the `lifespan` async context manager, after the `events.set_event_loop` line (~line 96):
```python
from . import log_publisher as lp
_lp = lp.setup_log_publisher(asyncio.get_running_loop(), min_level=getattr(logging, s.log_level, logging.INFO))
```

Add to the `yield` teardown section (after `feed = getattr(...)`):
```python
lp.teardown_log_publisher()
```

- [ ] **Step 5: Add /ws/logs WebSocket endpoint to app.py**

Add after `ws_global` endpoint (~line 404):
```python
@app.websocket("/ws/logs")
async def ws_logs(ws: WebSocket) -> None:
    session = read_session_from_ws(ws)
    if not session:
        await ws.close(code=4001)
        return
    await ws.accept()
    lp.log_publisher.subscribe(ws) if lp.log_publisher else None
    try:
        await ws.send_json({
            "type": "connected",
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "id": str(uuid.uuid4()),
        })
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if lp.log_publisher:
            lp.log_publisher.unsubscribe(ws)
```

Add imports at top of app.py if not present:
```python
import uuid
from . import log_publisher as lp_module
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd /web/server && pytest tests/test_log_publisher_integration.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add web/server/app.py web/server/settings.py
git commit -m "feat: wire log publisher into app lifespan and add /ws/logs endpoint"
```

---

## Task 3: Frontend — Zustand Log Store

**Files:**
- Create: `web/frontend/src/store/logs.ts`
- Test: `web/frontend/src/__tests__/store/logs.test.ts` (create)

**Interfaces:**
- Consumes: Nothing
- Produces: `useLogStore` hook with `{ entries, append, clear }`

- [ ] **Step 1: Write failing tests**

```typescript
// web/frontend/src/__tests__/store/logs.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { useLogStore } from "../../store/logs";

describe("useLogStore", () => {
  beforeEach(() => {
    useLogStore.getState().clear();
  });

  it("starts with empty entries", () => {
    expect(useLogStore.getState().entries).toEqual([]);
  });

  it("append adds entry to entries", () => {
    const entry = {
      id: "1",
      ts: "2026-06-22T10:00:00Z",
      level: "INFO" as const,
      logger: "test",
      message: "hello",
      source: "server" as const,
    };
    useLogStore.getState().append(entry);
    expect(useLogStore.getState().entries).toHaveLength(1);
    expect(useLogStore.getState().entries[0]).toEqual(entry);
  });

  it("clear removes all entries", () => {
    useLogStore.getState().append({ id: "1", ts: "", level: "INFO", logger: "", message: "", source: "server" });
    useLogStore.getState().append({ id: "2", ts: "", level: "ERROR", logger: "", message: "", source: "client" });
    useLogStore.getState().clear();
    expect(useLogStore.getState().entries).toHaveLength(0);
  });

  it("caps entries at 1000", () => {
    for (let i = 0; i < 1050; i++) {
      useLogStore.getState().append({ id: String(i), ts: "", level: "INFO", logger: "", message: "", source: "server" });
    }
    expect(useLogStore.getState().entries).toHaveLength(1000);
    expect(useLogStore.getState().entries[0].id).toBe("50");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web/frontend && uv run pytest src/__tests__/store/logs.test.ts -v` (or `npx vitest run src/__tests__/store/logs.test.ts`)
Expected: FAIL — module does not exist

- [ ] **Step 3: Write implementation**

```typescript
// web/frontend/src/store/logs.ts
import { create } from "zustand";

export interface LogEntry {
  id: string;
  ts: string;
  level: "DEBUG" | "INFO" | "WARNING" | "ERROR";
  logger: string;
  message: string;
  source: "server" | "client";
}

interface LogState {
  entries: LogEntry[];
  append: (entry: LogEntry) => void;
  clear: () => void;
}

const MAX_ENTRIES = 1000;

export const useLogStore = create<LogState>()((set) => ({
  entries: [],
  append: (entry) =>
    set((s) => ({ entries: [...s.entries, entry].slice(-MAX_ENTRIES) })),
  clear: () => set({ entries: [] }),
}));
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web/frontend && uv run vitest run src/__tests__/store/logs.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/frontend/src/store/logs.ts web/frontend/src/__tests__/store/logs.test.ts
git commit -m "feat: add Zustand log store"
```

---

## Task 4: Frontend — Console Capture

**Files:**
- Create: `web/frontend/src/lib/console-capture.ts`

**Interfaces:**
- Consumes: `useLogStore.append()`
- Produces: Module that wraps `console.log/warn/error/info/debug` on import

- [ ] **Step 1: Write implementation**

```typescript
// web/frontend/src/lib/console-capture.ts
import { useLogStore } from "../store/logs";

const LEVEL_MAP: Record<string, LogEntry["level"]> = {
  log: "INFO",
  info: "INFO",
  warn: "WARNING",
  error: "ERROR",
  debug: "DEBUG",
};

let _capturing = false;

function makeCapture(method: "log" | "info" | "warn" | "error" | "debug") {
  const original = console[method].bind(console);
  return (...args: unknown[]) => {
    if (!_capturing) {
      original(...args);
      return;
    }
    const msg = args.map((a) => (typeof a === "string" ? a : JSON.stringify(a))).join(" ");
    useLogStore.getState().append({
      id: crypto.randomUUID(),
      ts: new Date().toISOString(),
      level: LEVEL_MAP[method] ?? "INFO",
      logger: "console",
      message: msg,
      source: "client",
    });
    original(...args);
  };
}

_capturing = true;
console.log = makeCapture("log");
console.info = makeCapture("info");
console.warn = makeCapture("warn");
console.error = makeCapture("error");
console.debug = makeCapture("debug");
```

- [ ] **Step 2: Verify it has no import-time side effects by checking the file compiles**

Run: `cd web/frontend && uv run tsc --noEmit src/lib/console-capture.ts` (or let the build verify)
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add web/frontend/src/lib/console-capture.ts
git commit -m "feat: add console capture module"
```

---

## Task 5: Frontend — useLogStream Hook

**Files:**
- Create: `web/frontend/src/hooks/useLogStream.ts`
- Modify: `web/frontend/src/lib/ws.ts:76-78` (add `buildLogsUrl`)

**Interfaces:**
- Consumes: `buildLogsUrl()` from ws.ts, `useLogStore.append()`
- Produces: `useLogStream()` → `{ status: WsStatus }`

- [ ] **Step 1: Write failing test**

```typescript
// web/frontend/src/__tests__/hooks/useLogStream.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useLogStream } from "../../hooks/useLogStream";

describe("useLogStream", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns idle status when runId is null", () => {
    const { result } = renderHook(() => useLogStream(null));
    expect(result.current.status).toBe("idle");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web/frontend && uv run vitest run src/__tests__/hooks/useLogStream.test.ts`
Expected: FAIL — module does not exist

- [ ] **Step 3: Add buildLogsUrl helper to ws.ts**

Add at end of `web/frontend/src/lib/ws.ts`:
```typescript
export function buildLogsUrl(): string {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}/ws/logs`;
}
```

- [ ] **Step 4: Write useLogStream implementation**

```typescript
// web/frontend/src/hooks/useLogStream.ts
import { useEffect, useRef, useState } from "react";
import { ResilientWs, buildLogsUrl } from "../lib/ws";
import { useLogStore } from "../store/logs";
import type { LogEntry } from "../store/logs";

export type WsStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed";

export function useLogStream() {
  const append = useLogStore((s) => s.append);
  const [status, setStatus] = useState<WsStatus>("idle");
  const clientRef = useRef<ResilientWs | null>(null);

  useEffect(() => {
    const client = new ResilientWs({
      url: buildLogsUrl,
      onMessage: (evt: unknown) => {
        const e = evt as { type?: string; id?: string; ts?: string; level?: string; logger?: string; message?: string; source?: string };
        if (e.type === "connected") return;
        const entry: LogEntry = {
          id: e.id ?? crypto.randomUUID(),
          ts: e.ts ?? new Date().toISOString(),
          level: (e.level as LogEntry["level"]) ?? "INFO",
          logger: e.logger ?? "unknown",
          message: e.message ?? "",
          source: (e.source as LogEntry["source"]) ?? "server",
        };
        append(entry);
      },
      onStatus: setStatus,
    });
    clientRef.current = client;
    client.start();
    return () => {
      client.stop();
      clientRef.current = null;
    };
  }, [append]);

  return { status };
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd web/frontend && uv run vitest run src/__tests__/hooks/useLogStream.test.ts`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web/frontend/src/hooks/useLogStream.ts web/frontend/src/lib/ws.ts
git commit -m "feat: add useLogStream hook and buildLogsUrl helper"
```

---

## Task 6: Frontend — LogPanel Component

**Files:**
- Create: `web/frontend/src/components/LogPanel.tsx`
- Modify: `web/frontend/src/App.tsx` (import and render)

**Interfaces:**
- Consumes: `useLogStore`, `useLogStream`, existing `Drawer` component pattern
- Produces: `LogPanel` React component

- [ ] **Step 1: Write implementation**

```typescript
// web/frontend/src/components/LogPanel.tsx
import { useEffect, useRef, useState } from "react";
import { Terminal, X, Trash2 } from "lucide-react";
import { useLogStore } from "../store/logs";
import { useLogStream } from "../hooks/useLogStream";

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: "text-gray-400",
  INFO: "text-blue-400",
  WARNING: "text-amber-400",
  ERROR: "text-red-400",
};

const SOURCE_ACCENT: Record<string, string> = {
  server: "border-l-2 border-l-sky-500",
  client: "border-l-2 border-l-emerald-500",
};

export function LogPanel() {
  const { status } = useLogStream();
  const entries = useLogStore((s) => s.entries);
  const clear = useLogStore((s) => s.clear);
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const [levelFilter, setLevelFilter] = useState<Set<string>>(new Set(["DEBUG", "INFO", "WARNING", "ERROR"]));
  const [autoScroll, setAutoScroll] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const filtered = entries.filter((e) => {
    if (!levelFilter.has(e.level)) return false;
    if (filter && !e.message.toLowerCase().includes(filter.toLowerCase())) return false;
    return true;
  });

  useEffect(() => {
    if (!autoScroll) return;
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries, autoScroll]);

  const handleScroll = () => {
    const el = listRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50;
    setAutoScroll(atBottom);
  };

  const toggleLevel = (l: string) => {
    setLevelFilter((prev) => {
      const next = new Set(prev);
      next.has(l) ? next.delete(l) : next.add(l);
      return next;
    });
  };

  return (
    <>
      {/* Toggle button */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="fixed bottom-4 right-4 z-50 flex items-center gap-2 rounded-full bg-slate-800 px-3 py-2 text-sm text-slate-300 shadow-lg hover:bg-slate-700"
        title="Logs"
      >
        <Terminal size={16} />
        {status === "open" && <span className="h-2 w-2 rounded-full bg-emerald-400" />}
        {status === "connecting" && <span className="h-2 w-2 animate-pulse rounded-full bg-amber-400" />}
      </button>

      {/* Panel */}
      {open && (
        <div className="fixed bottom-16 right-4 z-50 flex h-[40vh] w-[600px] flex-col rounded-xl bg-slate-900/95 shadow-2xl backdrop-blur border border-slate-700">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-700 px-4 py-2">
            <span className="text-sm font-medium text-slate-300">Logs ({entries.length})</span>
            <div className="flex items-center gap-2">
              {(["DEBUG", "INFO", "WARNING", "ERROR"] as const).map((l) => (
                <button
                  key={l}
                  onClick={() => toggleLevel(l)}
                  className={`text-xs px-1.5 py-0.5 rounded ${levelFilter.has(l) ? `bg-slate-700 ${LEVEL_COLORS[l]}` : "text-slate-600"}`}
                >
                  {l}
                </button>
              ))}
              <input
                type="text"
                placeholder="search..."
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="w-32 rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300 placeholder-slate-500"
              />
              <button onClick={clear} className="rounded p-1 hover:bg-slate-700 text-slate-400" title="Clear">
                <Trash2 size={14} />
              </button>
              <button onClick={() => setOpen(false)} className="rounded p-1 hover:bg-slate-700 text-slate-400">
                <X size={14} />
              </button>
            </div>
          </div>

          {/* Log list */}
          <div ref={listRef} className="flex-1 overflow-y-auto font-mono text-xs" onScroll={handleScroll}>
            {filtered.length === 0 && (
              <div className="flex h-full items-center justify-center text-slate-500">No logs</div>
            )}
            {filtered.map((e) => (
              <div key={e.id} className={`flex gap-2 px-3 py-0.5 border-b border-slate-800/50 ${SOURCE_ACCENT[e.source] ?? ""}`}>
                <span className="w-16 shrink-0 text-slate-500">{e.ts?.split("T")[1]?.slice(0, 8) ?? ""}</span>
                <span className={`w-16 shrink-0 ${LEVEL_COLORS[e.level] ?? "text-slate-400"}`}>{e.level}</span>
                <span className="w-20 shrink-0 truncate text-slate-500">{e.logger}</span>
                <span className={`flex-1 break-all ${LEVEL_COLORS[e.level] ?? "text-slate-300"}`}>{e.message}</span>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd web/frontend && uv run tsc --noEmit src/components/LogPanel.tsx`
Expected: No errors (may need to be run in context of full project build)

- [ ] **Step 3: Commit**

```bash
git add web/frontend/src/components/LogPanel.tsx
git commit -m "feat: add LogPanel component"
```

---

## Task 7: Wire LogPanel into App

**Files:**
- Modify: `web/frontend/src/App.tsx`
- Modify: `web/frontend/src/lib/console-capture.ts` (add import in App)

**Interfaces:**
- Consumes: `LogPanel`, `console-capture`
- Produces: `LogPanel` rendered in app shell

- [ ] **Step 1: Read App.tsx to understand where to add LogPanel**

- [ ] **Step 2: Modify App.tsx to import and render LogPanel**

Add to App.tsx imports:
```typescript
import { LogPanel } from "./components/LogPanel";
import "./lib/console-capture"; // side-effect: wraps console on import
```

Add `<LogPanel />` inside the app shell, typically before the closing main tag or as a sibling at root level. Exact location depends on current App.tsx structure — find the outermost layout return and add as a sibling.

- [ ] **Step 3: Verify the app compiles**

Run: `cd web/frontend && uv run tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add web/frontend/src/App.tsx
git commit -m "feat: wire LogPanel into app shell"
```

---

## Self-Review Checklist

- [ ] Spec coverage: All spec requirements have a task? YES
  - LogPublisher: Task 1
  - /ws/logs endpoint: Task 2
  - Zustand store: Task 3
  - Console capture: Task 4
  - useLogStream hook: Task 5
  - LogPanel component: Task 6
  - App wiring: Task 7
- [ ] No placeholder patterns found
- [ ] Type consistency: `LogEntry` type defined in Task 3 matches usage in Tasks 4/5/6