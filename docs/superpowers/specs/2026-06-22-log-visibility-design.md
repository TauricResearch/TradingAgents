# Full Log Visibility — Design Spec

**Date:** 2026-06-22
**Status:** Approved

---

## Overview

Add real-time log visibility to the dashboard, streaming both Python server logs and TypeScript client logs to a unified on-screen log panel via a dedicated WebSocket channel.

---

## Architecture

```
Python Backend                    Frontend (React)
─────────────────                  ─────────────────
logging module  ─────┐
                     │
                     ▼
              LogPublisher (log handler)
                     │
                     ▼
              /ws/logs WebSocket  ──────► useLogStream hook
                     │                       │
                     │                       ▼
                     │               Zustand logStore
                     │                       │
                     ▼                       ▼
              Console output         LogPanel component
```

---

## Backend Changes

### 1. New File: `web/server/log_publisher.py`

A custom Python `logging.Handler` that captures log records and broadcasts them to connected WebSocket clients.

**Classes:**
- `LogPublisher` — singleton handler. Maintains a set of connected WS clients. On `emit()`, serializes the record and fans out to all clients.
- `log_publisher` — module-level singleton instance, created and registered in `app.py` lifespan.

**Log record format (JSON over WS):**
```python
{
    "id": "<uuid>",
    "ts": "2026-06-22T10:30:00.123Z",
    "level": "INFO",          # DEBUG | INFO | WARNING | ERROR
    "logger": "web.server.runner",
    "message": "Run started for ticker AAPL",
    "source": "server",
}
```

**Environment variables:**
- `TRADINGAGENTS_LOG_LEVEL` — minimum level to broadcast (default: `"INFO"`). Maps directly to Python `logging` levels.

**Wiring:**
- Called from `app.py` lifespan startup: creates `LogPublisher`, attaches to root logger (`logging.getLogger()`).
- `app.py` lifespan shutdown: removes handler, waits briefly for pending broadcasts.

### 2. New WebSocket Endpoint: `/ws/logs`

**In `web/server/app.py`:**
- `WebSocket /ws/logs` — accepts log subscriptions.
- On connect: adds WS to `LogPublisher` subscriber set.
- On disconnect: removes WS from subscriber set.
- Sends a `{"type": "connected", "ts": "...", "id": "..."}` welcome message.

---

## Frontend Changes

### 1. New Hook: `web/frontend/src/hooks/useLogStream.ts`

Connects to `/ws/logs`, receives log events, and writes them into the Zustand store.

```typescript
interface LogEntry {
  id: string;
  ts: string;
  level: "DEBUG" | "INFO" | "WARNING" | "ERROR";
  logger: string;
  message: string;
  source: "server" | "client";
}

export function useLogStream() {
  // Returns { logs: LogEntry[], status: WsStatus, clearLogs: () => void }
}
```

### 2. New Store: `web/frontend/src/store/logs.ts`

Zustand store with persist middleware (session storage only).

```typescript
interface LogState {
  entries: LogEntry[];
  append: (entry: LogEntry) => void;
  clear: () => void;
}
```

- Max 1000 entries (oldest truncated on append).
- Persists to `sessionStorage` so logs survive hot-reloads but are cleared on page close.

### 3. Console Capture: `web/frontend/src/lib/console-capture.ts`

A module-level wrapper that intercepts `console.log`, `console.info`, `console.warn`, `console.error` and routes them through the same `logStore.append()`. Each entry is tagged `source: "client"`.

- Only wraps once on import; does not nest.
- Original methods are called after capture so devtools still work.

### 4. New Component: `web/frontend/src/components/LogPanel.tsx`

Collapsible log viewer panel.

**UI:**
- Toggle button (Lucide `Terminal` icon) in the top-right header bar — always visible.
- Panel opens as a slide-up drawer from the bottom, ~40vh height.
- Each log line: `[HH:MM:SS] [LEVEL] [source] logger: message`
- Color coding: DEBUG=gray, INFO=blue, WARNING=amber, ERROR=red. Server logs have a subtle left-border accent.
- Auto-scroll to bottom on new entries; pause auto-scroll if user scrolls up.
- Filter bar: level toggles (checkboxes), text search input.
- "Clear" button to wipe the in-memory log buffer.

---

## Event Flow

1. Python `logging.info(...)` call → `LogPublisher.emit()` → JSON broadcast to all `/ws/logs` clients.
2. Browser receives JSON on `/ws/logs` WebSocket → `useLogStream.onMessage()` → `logStore.append()`.
3. `LogPanel` React component re-renders with new entry, auto-scrolls if at bottom.

---

## Files to Create/Modify

### Backend
| File | Change |
|------|--------|
| `web/server/log_publisher.py` | New — `LogPublisher` class and module singleton |
| `web/server/app.py` | Add `/ws/logs` WS route; register log publisher in lifespan |
| `web/server/settings.py` | Add `TRADINGAGENTS_LOG_LEVEL` setting |

### Frontend
| File | Change |
|------|--------|
| `web/frontend/src/store/logs.ts` | New — Zustand store |
| `web/frontend/src/lib/console-capture.ts` | New — console wrapper |
| `web/frontend/src/hooks/useLogStream.ts` | New — WebSocket hook |
| `web/frontend/src/components/LogPanel.tsx` | New — Log panel component |
| `web/frontend/src/App.tsx` | Import and render `LogPanel` |
| `web/frontend/src/components/ui/drawer.tsx` | Reuse existing `Drawer` component if available, else create minimal one |
| `web/frontend/src/lib/ws.ts` | Add `buildLogsUrl()` helper alongside existing `buildRunUrl` / `buildGlobalUrl` |

---

## Testing Considerations

- Backend: unit test `LogPublisher` directly by emitting and checking subscriber fan-out.
- Backend: integration test WebSocket connection lifecycle.
- Frontend: unit test `logStore` append/clear/truncation logic.
- Frontend: e2e test verifying server log appears in panel after triggering a server-side log call.

---

## Out of Scope

- Persisting logs to disk (server-side log files already configured via uvicorn).
- Log aggregation across multiple server instances.
- Exporting/downloading logs.
- Log level filtering persisted in localStorage.