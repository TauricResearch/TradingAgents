---
id: 001
title: "Research: streaming LangGraph runs to a browser"
labels: [wayfinder:research]
status: closed
assignee: JMAN730
blocked-by: []
---

## Question

What is the current best-practice pattern (2026) for forwarding a LangGraph `graph.stream(...)` run from a Python backend to a browser live view? Specifically:

- SSE vs WebSocket for one-directional progress streams — which do FastAPI + LangGraph examples/docs favor, and why?
- Does LangGraph offer astream/event APIs better suited to progress UIs than raw chunk streaming (e.g. `astream_events`, `stream_mode` options in langgraph>=0.4)?
- How do existing projects bridge a long-running sync `graph.stream` loop into an async web server (thread + queue? `run_in_executor`? native async graph)?
- Any FastAPI-specific pitfalls: client disconnect handling, keep-alive, proxy buffering of SSE.

Findings feed the backend-stack decision (ticket 002). Capture findings as Markdown on a throwaway `research/web-streaming` branch; link the file here.

## Resolution

Findings: `.wayfinder/research/web-streaming.md` on branch `research/web-streaming` (commit `8d7c410`). Cited to primary sources (LangGraph docs/source, FastAPI/Starlette, sse-starlette, MDN); unverifiable claims flagged inline.

Summary:

1. **SSE over WebSockets** — LangGraph's own hosted API streams runs as `text/event-stream`; FastAPI 0.135+ has native `fastapi.sse.EventSourceResponse` (fallback: sse-starlette). WebSockets only if bidirectional needs appear.
2. **Don't forward raw `stream_mode="values"` chunks** — use `stream_mode=["updates", "custom"]` (plus `"messages"` for tokens), one SSE `event:` type per mode; `get_stream_writer()` in nodes emits app-level progress events.
3. **Minimal sync bridge** — hand the sync `graph.stream` generator to `EventSourceResponse`; Starlette iterates it via `iterate_in_threadpool`, no hand-rolled thread+queue.
4. **Better long-term** — `graph.astream` on the web path: sync node functions run in a thread pool automatically, and async generators get prompt cancellation on client disconnect (sync ones don't).
5. **Hygiene** — 15 s ping comments, `Cache-Control: no-cache`, `X-Accel-Buffering: no`, check `request.is_disconnected()` in manual loops, exclude SSE route from compression. Richest APIs (`version="v2"`, `tasks`/`checkpoints`) need langgraph >= 1.1 vs repo's `>=0.4.8` pin; core recommendation works today.
