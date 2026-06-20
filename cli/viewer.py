"""Localhost live report viewer for TradingAgents runs.

A tiny stdlib HTTP server (no Flask, no deps) that exposes:

* ``GET /``       — single-page HTML viewer
* ``GET /events`` — Server-Sent Events stream of per-ticker snapshots
* ``GET /state``  — current per-ticker snapshots as JSON (used on initial load)

The pipeline pushes a fresh snapshot per ticker after every streamed LangGraph
chunk via :meth:`Viewer.update`. Each snapshot is the merged status + report
content the terminal UI already renders — the viewer just makes it readable in
a browser tab, one stacked section per ticker, with greyed-out placeholders for
nodes that haven't run yet so progress is visible at a glance.

Local-only by design: binds to ``127.0.0.1`` on an OS-assigned port, no auth,
no persistence (all state is in-memory and dies with the process). Persistence
is a separate piece — this is purely a viewing layer over the live run.
"""

from __future__ import annotations

import contextlib
import json
import queue
import threading
import time
import webbrowser
from collections.abc import Iterable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

# Ordered list of report sections shown in the viewer per ticker, with the
# agent whose completion finalizes that section. Mirrors MessageBuffer's
# REPORT_SECTIONS but flattened into render order.
_SECTION_ORDER: list[tuple[str, str, str]] = [
    ("market_report",         "Market Analysis",          "Market Analyst"),
    ("sentiment_report",      "Social Sentiment",         "Sentiment Analyst"),
    ("news_report",           "News Analysis",            "News Analyst"),
    ("fundamentals_report",   "Fundamentals Analysis",    "Fundamentals Analyst"),
    ("investment_plan",       "Research Team Decision",   "Research Manager"),
    ("trader_investment_plan", "Trading Plan",            "Trader"),
    ("final_trade_decision",  "Portfolio Decision",       "Portfolio Manager"),
]

# Agent team grouping for the per-ticker status mini-table. Same shape the
# terminal grid uses, so the two views feel consistent.
_AGENT_TEAMS: list[tuple[str, list[str]]] = [
    ("Analyst",   ["Market Analyst", "Sentiment Analyst", "News Analyst", "Fundamentals Analyst"]),
    ("Research",  ["Bull Researcher", "Bear Researcher", "Research Manager"]),
    ("Trading",   ["Trader"]),
    ("Risk",      ["Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"]),
    ("Portfolio", ["Portfolio Manager"]),
]


def _snapshot_from_buffer(
    ticker: str,
    asset_type: str,
    position_size_gbp: float | None,
    stage: str,
    started_at: float | None,
    finished_at: float | None,
    error: str | None,
    buffer: Any,
) -> dict[str, Any]:
    """Freeze the buffer into a JSON-safe snapshot for the SSE stream."""
    agent_status: dict[str, str] = (buffer.agent_status if buffer else {}) or {}
    report_sections: dict[str, Any] = (buffer.report_sections if buffer else {}) or {}

    sections = []
    for key, title, finalizer in _SECTION_ORDER:
        if buffer is not None and key not in report_sections:
            # Section disabled for this ticker (analyst not selected).
            continue
        content = report_sections.get(key)
        if content is None:
            status = "pending"
            text = ""
        else:
            text = content if isinstance(content, str) else "\n".join(str(p) for p in content)
            status = "completed" if agent_status.get(finalizer) == "completed" else "in_progress"
        sections.append({
            "key": key,
            "title": title,
            "status": status,
            "content": text,
        })

    agents = []
    for team, names in _AGENT_TEAMS:
        for name in names:
            if name not in agent_status:
                continue
            agents.append({"team": team, "name": name, "status": agent_status[name]})

    elapsed = 0.0 if started_at is None else (finished_at or time.time()) - started_at

    return {
        "ticker": ticker,
        "asset_type": asset_type,
        "position_size_gbp": position_size_gbp,
        "stage": stage,
        "error": error,
        "finished": stage in ("done", "failed"),
        "elapsed": round(elapsed, 1),
        "sections": sections,
        "agents": agents,
    }


class Viewer:
    """Process-local live report viewer. Thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []
        self._subscribers: list[queue.Queue[str]] = []
        self._meta: dict[str, dict[str, Any]] = {}  # ticker -> {started_at, asset_type, position}
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._port: int | None = None
        self._browser_opened = False

    # --- public API --------------------------------------------------------

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._port}" if self._port else ""

    def start(self) -> str:
        """Start the HTTP server in a background thread; return the URL.

        Does NOT open the browser — call :meth:`open_browser` once the user
        has finished any interactive prompts so the tab opens onto a viewer
        that's about to receive data rather than a blank page that sits open
        through several minutes of model / analyst selection.
        """
        handler_cls = _make_handler(self)
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
        self._port = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="tradingagents-viewer",
            daemon=True,
        )
        self._thread.start()
        return self.url

    def open_browser(self) -> None:
        """Open the viewer URL in the user's default browser. Idempotent."""
        if self._browser_opened or not self._port:
            return
        self._browser_opened = True
        with contextlib.suppress(Exception):
            webbrowser.open(self.url)

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        # Wake any blocked SSE subscribers so their connections close.
        with self._lock:
            for q in self._subscribers:
                with contextlib.suppress(queue.Full):
                    q.put_nowait("")

    def register(
        self,
        ticker: str,
        asset_type: str,
        position_size_gbp: float | None,
        analysts: Iterable[str] | None = None,
    ) -> None:
        """Seed an empty entry so the ticker shows up in the viewer before the
        first chunk arrives. ``analysts`` is the effective per-ticker analyst
        key list (e.g. ``["market", "news"]``) used to pre-filter section rows.
        """
        with self._lock:
            if ticker not in self._snapshots:
                self._order.append(ticker)
            self._meta[ticker] = {
                "asset_type": asset_type,
                "position_size_gbp": position_size_gbp,
                "started_at": time.time(),
                "analyst_keys": list(analysts or []),
            }
            enabled = set(self._meta[ticker]["analyst_keys"]) or None
            sections = []
            for key, title, _ in _SECTION_ORDER:
                analyst_key = {
                    "market_report": "market",
                    "sentiment_report": "social",
                    "news_report": "news",
                    "fundamentals_report": "fundamentals",
                }.get(key)
                if analyst_key and enabled is not None and analyst_key not in enabled:
                    continue
                sections.append({"key": key, "title": title, "status": "pending", "content": ""})
            self._snapshots[ticker] = {
                "ticker": ticker,
                "asset_type": asset_type,
                "position_size_gbp": position_size_gbp,
                "stage": "queued",
                "error": None,
                "finished": False,
                "elapsed": 0.0,
                "sections": sections,
                "agents": [],
            }
        self._broadcast(ticker)

    def update(
        self,
        ticker: str,
        buffer: Any,
        stage: str,
        error: str | None = None,
        finished: bool = False,
    ) -> None:
        """Snapshot ``buffer`` for ``ticker`` and broadcast to subscribers."""
        meta = self._meta.get(ticker, {})
        snap = _snapshot_from_buffer(
            ticker=ticker,
            asset_type=meta.get("asset_type", "stock"),
            position_size_gbp=meta.get("position_size_gbp"),
            stage=stage,
            started_at=meta.get("started_at"),
            finished_at=time.time() if finished else None,
            error=error,
            buffer=buffer,
        )
        with self._lock:
            if ticker not in self._snapshots:
                self._order.append(ticker)
            self._snapshots[ticker] = snap
        self._broadcast(ticker)

    # --- internal ----------------------------------------------------------

    def _broadcast(self, ticker: str) -> None:
        with self._lock:
            payload = json.dumps(self._snapshots[ticker])
            dead: list[queue.Queue[str]] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                self._subscribers.remove(q)

    def _subscribe(self) -> queue.Queue[str]:
        q: queue.Queue[str] = queue.Queue(maxsize=256)
        with self._lock:
            self._subscribers.append(q)
            # Replay current state so a late connection sees everything.
            for ticker in self._order:
                try:
                    q.put_nowait(json.dumps(self._snapshots[ticker]))
                except queue.Full:
                    break
        return q

    def _unsubscribe(self, q: queue.Queue[str]) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def _state_payload(self) -> str:
        with self._lock:
            return json.dumps([self._snapshots[t] for t in self._order])


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

def _make_handler(viewer: Viewer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A002 — base-class signature
            return  # Silence the default stderr access log; CLI owns the screen.

        def do_GET(self):  # noqa: N802 — http.server convention
            if self.path == "/" or self.path.startswith("/?"):
                body = _PAGE_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/state":
                body = viewer._state_payload().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "keep-alive")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                q = viewer._subscribe()
                try:
                    while True:
                        try:
                            payload = q.get(timeout=15.0)
                        except queue.Empty:
                            # SSE comment keeps the connection warm.
                            self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                            continue
                        if not payload:
                            break
                        self.wfile.write(b"data: ")
                        self.wfile.write(payload.encode("utf-8"))
                        self.wfile.write(b"\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    viewer._unsubscribe(q)
                return

            self.send_response(404)
            self.end_headers()

    return Handler


# ---------------------------------------------------------------------------
# Frontend (single self-contained HTML page)
# ---------------------------------------------------------------------------

_PAGE_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>TradingAgents — Live Report Viewer</title>
<style>
  :root {
    --bg: #0f1115; --panel: #161a22; --muted: #8a93a6; --text: #e6e8ee;
    --pending: #3a3f4b; --inprog: #d29922; --done: #2ea043; --error: #f85149;
    --border: #262b36; --accent: #58a6ff;
    --code-bg: #0b0d12;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 14px; line-height: 1.5;
  }
  header {
    position: sticky; top: 0; z-index: 10; background: var(--panel);
    border-bottom: 1px solid var(--border); padding: 10px 16px;
    display: flex; align-items: center; gap: 16px;
  }
  header h1 { font-size: 14px; margin: 0; font-weight: 600; }
  header .meta { color: var(--muted); font-size: 12px; }
  main { max-width: 1100px; margin: 0 auto; padding: 16px; }
  .ticker {
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 8px; margin-bottom: 20px; overflow: hidden;
  }
  .ticker-head {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 16px; border-bottom: 1px solid var(--border);
    cursor: pointer; user-select: none;
  }
  .ticker-head h2 { margin: 0; font-size: 16px; font-weight: 600; }
  .ticker-head h2 .sub { color: var(--muted); font-weight: 400; font-size: 13px; margin-left: 8px; }
  .ticker-head .stage {
    font-size: 12px; padding: 3px 8px; border-radius: 999px;
    background: var(--pending); color: var(--text);
  }
  .stage.queued { background: var(--pending); color: var(--muted); }
  .stage.analysts, .stage.research_debate, .stage.trader, .stage.risk_debate, .stage.portfolio {
    background: rgba(88, 166, 255, 0.15); color: var(--accent);
  }
  .stage.done { background: rgba(46, 160, 67, 0.15); color: var(--done); }
  .stage.failed { background: rgba(248, 81, 73, 0.15); color: var(--error); }
  .ticker-body { padding: 12px 16px 16px; }
  .ticker.collapsed .ticker-body { display: none; }
  .agents {
    display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px;
  }
  .agent {
    font-size: 11px; padding: 3px 7px; border-radius: 4px;
    background: var(--bg); border: 1px solid var(--border); color: var(--muted);
  }
  .agent.pending { opacity: 0.5; }
  .agent.in_progress { color: var(--inprog); border-color: var(--inprog); }
  .agent.completed { color: var(--done); border-color: rgba(46, 160, 67, 0.4); }
  .agent.error { color: var(--error); border-color: var(--error); }
  .section {
    border-top: 1px solid var(--border); padding: 10px 0 4px;
  }
  .section:first-of-type { border-top: none; padding-top: 4px; }
  .section-head {
    display: flex; align-items: center; gap: 10px; cursor: pointer;
    user-select: none;
  }
  .section-head .dot {
    width: 8px; height: 8px; border-radius: 50%; background: var(--pending);
    flex-shrink: 0;
  }
  .section.in_progress .dot { background: var(--inprog); animation: pulse 1.2s ease-in-out infinite; }
  .section.completed .dot { background: var(--done); }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
  .section-head .title { font-weight: 500; flex: 1; }
  .section.pending .title { color: var(--muted); }
  .section-head .status { font-size: 11px; color: var(--muted); }
  .section-body {
    margin-top: 8px; background: var(--code-bg); border: 1px solid var(--border);
    border-radius: 6px; padding: 14px 18px;
    word-wrap: break-word; font-size: 13.5px; line-height: 1.6;
    max-height: 600px; overflow-y: auto;
  }
  .section-body.plain { white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; }
  .section-body h1, .section-body h2, .section-body h3, .section-body h4 {
    margin: 16px 0 8px; line-height: 1.3; font-weight: 600; color: #f0f3fa;
  }
  .section-body h1 { font-size: 1.5em; border-bottom: 1px solid var(--border); padding-bottom: 6px; }
  .section-body h2 { font-size: 1.25em; border-bottom: 1px solid var(--border); padding-bottom: 4px; }
  .section-body h3 { font-size: 1.1em; }
  .section-body h4 { font-size: 1em; color: var(--accent); }
  .section-body p { margin: 8px 0; }
  .section-body ul, .section-body ol { margin: 8px 0; padding-left: 24px; }
  .section-body li { margin: 4px 0; }
  .section-body strong { color: #f0f3fa; font-weight: 600; }
  .section-body em { color: #cdd3e0; }
  .section-body hr { border: none; border-top: 1px solid var(--border); margin: 16px 0; }
  .section-body code {
    background: #1a1f2b; padding: 1px 5px; border-radius: 3px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.9em;
  }
  .section-body pre {
    background: #1a1f2b; padding: 10px 12px; border-radius: 4px;
    overflow-x: auto; font-size: 0.9em;
  }
  .section-body pre code { background: none; padding: 0; }
  .section-body blockquote {
    border-left: 3px solid var(--accent); margin: 8px 0; padding: 4px 12px;
    color: var(--muted); background: rgba(88, 166, 255, 0.05);
  }
  .section-body table {
    border-collapse: collapse; margin: 10px 0; width: 100%;
    font-size: 0.95em;
  }
  .section-body th, .section-body td {
    border: 1px solid var(--border); padding: 6px 10px; text-align: left;
  }
  .section-body th { background: #1a1f2b; font-weight: 600; color: #f0f3fa; }
  .section-body tr:nth-child(even) td { background: rgba(255, 255, 255, 0.02); }
  .section-body a { color: var(--accent); text-decoration: none; }
  .section-body a:hover { text-decoration: underline; }
  .section.pending .section-body { display: none; }
  .section.collapsed .section-body { display: none; }
  .empty { color: var(--muted); padding: 40px 0; text-align: center; font-style: italic; }
  .error-banner {
    background: rgba(248, 81, 73, 0.15); border: 1px solid var(--error);
    color: var(--error); padding: 8px 12px; border-radius: 6px;
    margin-bottom: 12px; font-size: 13px;
  }
</style>
</head>
<body>
<header>
  <h1>TradingAgents — Live Report Viewer</h1>
  <span class="meta" id="conn">connecting…</span>
</header>
<main>
  <div id="root"><div class="empty">Waiting for the run to start…</div></div>
</main>
<script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/dompurify@3.0.9/dist/purify.min.js"></script>
<script>
  const STAGE_LABEL = {
    queued: "queued", analysts: "analysts", research_debate: "research debate",
    trader: "trader", risk_debate: "risk debate", portfolio: "portfolio mgr",
    done: "done", failed: "failed",
  };
  const ORDER = [];
  const STATE = {};
  // Track collapsed sections by ticker+key so updates don't re-open the user's view.
  const COLLAPSED = new Set();

  function fmtElapsed(sec) {
    const s = Math.max(0, Math.round(sec));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
  }

  function renderTicker(snap) {
    const wrap = document.createElement("div");
    wrap.className = "ticker";
    wrap.id = `t-${snap.ticker}`;
    if (COLLAPSED.has(`ticker:${snap.ticker}`)) wrap.classList.add("collapsed");

    const head = document.createElement("div");
    head.className = "ticker-head";
    const pos = snap.position_size_gbp ? ` · £${Math.round(snap.position_size_gbp).toLocaleString()}` : "";
    head.innerHTML = `
      <h2>${snap.ticker}<span class="sub">${snap.asset_type}${pos} · ${fmtElapsed(snap.elapsed)}</span></h2>
      <span class="stage ${snap.stage}">${STAGE_LABEL[snap.stage] || snap.stage}</span>
    `;
    head.addEventListener("click", () => {
      const key = `ticker:${snap.ticker}`;
      if (wrap.classList.toggle("collapsed")) COLLAPSED.add(key); else COLLAPSED.delete(key);
    });
    wrap.appendChild(head);

    const body = document.createElement("div");
    body.className = "ticker-body";

    if (snap.error) {
      const eb = document.createElement("div");
      eb.className = "error-banner";
      eb.textContent = snap.error;
      body.appendChild(eb);
    }

    if (snap.agents.length) {
      const agents = document.createElement("div");
      agents.className = "agents";
      for (const a of snap.agents) {
        const chip = document.createElement("span");
        chip.className = `agent ${a.status}`;
        chip.textContent = a.name;
        chip.title = `${a.team} — ${a.status}`;
        agents.appendChild(chip);
      }
      body.appendChild(agents);
    }

    for (const sec of snap.sections) {
      const s = document.createElement("div");
      s.className = `section ${sec.status}`;
      const sKey = `${snap.ticker}:${sec.key}`;
      if (COLLAPSED.has(sKey)) s.classList.add("collapsed");
      const sHead = document.createElement("div");
      sHead.className = "section-head";
      sHead.innerHTML = `
        <span class="dot"></span>
        <span class="title">${sec.title}</span>
        <span class="status">${sec.status}</span>
      `;
      sHead.addEventListener("click", () => {
        if (s.classList.toggle("collapsed")) COLLAPSED.add(sKey); else COLLAPSED.delete(sKey);
      });
      s.appendChild(sHead);
      if (sec.content) {
        const sBody = document.createElement("div");
        sBody.className = "section-body";
        // Render markdown via marked + sanitize via DOMPurify. If either CDN
        // failed to load (offline, blocked), fall back to plaintext.
        if (window.marked && window.DOMPurify) {
          try {
            const html = window.marked.parse(sec.content, { gfm: true, breaks: true });
            sBody.innerHTML = window.DOMPurify.sanitize(html);
          } catch (err) {
            sBody.classList.add("plain");
            sBody.textContent = sec.content;
          }
        } else {
          sBody.classList.add("plain");
          sBody.textContent = sec.content;
        }
        s.appendChild(sBody);
      }
      body.appendChild(s);
    }
    wrap.appendChild(body);
    return wrap;
  }

  function renderAll() {
    const root = document.getElementById("root");
    if (ORDER.length === 0) {
      root.innerHTML = '<div class="empty">Waiting for the run to start…</div>';
      return;
    }
    root.innerHTML = "";
    for (const t of ORDER) root.appendChild(renderTicker(STATE[t]));
  }

  function ingest(snap) {
    if (!(snap.ticker in STATE)) ORDER.push(snap.ticker);
    STATE[snap.ticker] = snap;
  }

  fetch("/state").then(r => r.json()).then(arr => {
    for (const snap of arr) ingest(snap);
    renderAll();
  }).catch(() => {});

  const es = new EventSource("/events");
  es.onopen = () => { document.getElementById("conn").textContent = "live"; };
  es.onerror = () => { document.getElementById("conn").textContent = "disconnected"; };
  es.onmessage = (e) => {
    try {
      const snap = JSON.parse(e.data);
      ingest(snap);
      renderAll();
    } catch (err) { /* ignore */ }
  };

  // Local elapsed tick — the server only pushes on chunk boundaries, so
  // bump the elapsed display in between to keep it from looking frozen.
  setInterval(() => {
    let dirty = false;
    for (const t of ORDER) {
      const s = STATE[t];
      if (!s.finished) { s.elapsed += 1; dirty = true; }
    }
    if (dirty) renderAll();
  }, 1000);
</script>
</body>
</html>
"""
