"""Local web dashboard mirroring the CLI's three panels.

The Rich ``Live`` view cannot do independent per-panel scrolling, so this
module exposes the same ``MessageBuffer`` state over HTTP (stdlib only, no
new dependencies) and serves a single self-contained page where each panel
scrolls natively and the report renders Markdown.

Started automatically by ``cli.main`` during analysis; open the printed URL
in a browser. Set ``TRADINGAGENTS_WEB=0`` to disable, or
``TRADINGAGENTS_WEB_PORT`` to change the port (default 8765).
"""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Cap payload size so a long run never ships megabytes per poll.
_MAX_MESSAGES = 300
_MAX_CONTENT_CHARS = 2000

SECTION_TITLES = {
    "market_report": "Market Analysis",
    "sentiment_report": "Social Sentiment",
    "news_report": "News Analysis",
    "fundamentals_report": "Fundamentals Analysis",
    "investment_plan": "Research Team Decision",
    "trader_investment_plan": "Trading Team Plan",
    "final_trade_decision": "Portfolio Management Decision",
}


def build_snapshot(message_buffer, stats_handler=None, start_time=None, meta=None):
    """Serialize live CLI state into JSON-safe dicts."""
    # Teams: selected analysts first (mapping order), then fixed teams.
    analyst_order = list(getattr(message_buffer, "ANALYST_MAPPING", {}).values())
    fixed = getattr(message_buffer, "FIXED_AGENTS", {})
    teams = []
    analyst_agents = [
        a for a in analyst_order if a in message_buffer.agent_status
    ]
    if analyst_agents:
        teams.append({"team": "Analyst Team", "agents": analyst_agents})
    for team, agents in fixed.items():
        active = [a for a in agents if a in message_buffer.agent_status]
        if active:
            teams.append({"team": team, "agents": active})

    def clip(text):
        text = "" if text is None else str(text)
        return text if len(text) <= _MAX_CONTENT_CHARS else text[:_MAX_CONTENT_CHARS] + "..."

    combined = []
    for timestamp, tool_name, args in list(message_buffer.tool_calls)[-_MAX_MESSAGES:]:
        try:
            args_str = ", ".join(f"{k}={v}" for k, v in dict(args).items())
        except Exception:
            args_str = str(args)
        combined.append(
            {"time": timestamp, "type": "Tool", "content": f"{tool_name}({args_str})"}
        )
    for timestamp, msg_type, content in list(message_buffer.messages)[-_MAX_MESSAGES:]:
        combined.append(
            {"time": timestamp, "type": str(msg_type), "content": clip(content)}
        )
    # Chronological for natural top-to-bottom reading with follow-scroll.
    messages = combined[-_MAX_MESSAGES:]

    statuses = dict(message_buffer.agent_status)
    sections = {
        name: (clip(message_buffer.report_sections.get(name)))
        for name in message_buffer.report_sections
    }
    try:
        reports_completed = message_buffer.get_completed_reports_count()
    except Exception:
        reports_completed = 0

    stats = {}
    if stats_handler is not None:
        try:
            stats = stats_handler.get_stats()
        except Exception:
            stats = {}

    elapsed = int(time.time() - start_time) if start_time else 0
    return {
        "meta": meta or {},
        "teams": teams,
        "statuses": statuses,
        "agents_completed": sum(1 for s in statuses.values() if s == "completed"),
        "agents_total": len(statuses),
        "reports_completed": reports_completed,
        "reports_total": len(message_buffer.report_sections),
        "messages": messages,
        "sections": sections,
        "section_titles": SECTION_TITLES,
        "current_report": clip(message_buffer.current_report),
        "final_report": clip(message_buffer.final_report),
        "stats": stats,
        "elapsed_seconds": elapsed,
    }


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TradingAgents Dashboard</title>
<style>
  :root { --bg:#0d1117; --panel:#161b22; --border:#2f6f4f; --border-blue:#1f6feb;
          --text:#e6edf3; --dim:#8b949e; --green:#3fb950; --yellow:#d29922;
          --red:#f85149; --cyan:#39c5cf; --pink:#ff7b72; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font-family:Consolas,Menlo,monospace; font-size:14px; }
  header { padding:10px 16px; border-bottom:1px solid var(--border); }
  header h1 { margin:0; font-size:16px; color:var(--green); }
  header .sub { color:var(--dim); font-size:12px; }
  #stats { padding:6px 16px; color:var(--dim); font-size:12px;
           border-bottom:1px solid #30363d; }
  main { display:flex; flex-direction:column; gap:10px; padding:10px 16px;
         height:calc(100vh - 110px); }
  .row { display:flex; gap:10px; min-height:0; flex:1.1; }
  .panel { background:var(--panel); border:1px solid var(--border);
           border-radius:6px; display:flex; flex-direction:column; min-width:0; }
  .panel.blue { border-color:var(--border-blue); }
  .panel.grow { flex:1.4; }
  .panel h2 { margin:0; padding:6px 12px; font-size:13px; font-weight:normal;
              color:var(--cyan); border-bottom:1px solid #30363d;
              display:flex; justify-content:space-between; align-items:center; }
  .panel h2 label { font-size:11px; color:var(--dim); }
  .scroll { overflow-y:auto; padding:8px 12px; min-height:0; }
  #report-panel { flex:1; }
  table { border-collapse:collapse; width:100%; }
  th { color:var(--pink); font-weight:normal; padding:4px 8px;
       border-bottom:1px solid #30363d; }
  td { padding:4px 8px; border-bottom:1px solid #21262d; vertical-align:top; }
  .st-completed { color:var(--green); } .st-pending { color:var(--yellow); }
  .st-in_progress { color:var(--cyan); } .st-error { color:var(--red); }
  .msg { border-bottom:1px solid #21262d; padding:6px 0; }
  .msg .meta { color:var(--dim); font-size:12px; }
  .msg .type { color:var(--green); }
  .msg pre { white-space:pre-wrap; word-break:break-word; margin:4px 0 0; }
  .md h1,.md h2,.md h3 { color:var(--pink); } .md hr { border-color:#30363d; }
  .md code { background:#0d1117; padding:0 4px; border-radius:3px; }
  .md pre { background:#0d1117; padding:8px; border-radius:4px;
            overflow-x:auto; white-space:pre-wrap; }
  details { margin:8px 0; border:1px solid #30363d; border-radius:4px; }
  summary { cursor:pointer; padding:6px 10px; color:var(--cyan); }
  details .body { padding:0 10px 10px; }
  .empty { color:var(--dim); font-style:italic; }
</style>
</head>
<body>
<header>
  <h1>TradingAgents Dashboard</h1>
  <div class="sub" id="meta">connecting…</div>
</header>
<div id="stats">connecting…</div>
<div id="promptbar" style="display:none;padding:8px 16px;border-bottom:1px solid var(--yellow);background:#241d08">
  <span id="promptq" style="color:var(--yellow)"></span>
  <input id="prompta" style="margin-left:8px;background:#0d1117;color:var(--text);border:1px solid #30363d;border-radius:4px;padding:4px 8px;width:40%">
  <button id="promptsb" style="margin-left:8px;background:var(--border-blue);color:#fff;border:0;border-radius:4px;padding:5px 14px;cursor:pointer">Send</button>
  <span style="color:var(--dim);font-size:11px"> — or answer in the terminal</span>
</div>
<main>
  <div class="row">
    <div class="panel" style="flex:1">
      <h2>Progress</h2>
      <div class="scroll" id="progress"><span class="empty">Waiting…</span></div>
    </div>
    <div class="panel blue grow">
      <h2>Messages &amp; Tools
        <label><input type="checkbox" id="follow-msg" checked> follow</label></h2>
      <div class="scroll" id="messages"><span class="empty">Waiting…</span></div>
    </div>
  </div>
  <div class="panel" id="report-panel">
    <h2>Current Report
      <label><input type="checkbox" id="follow-rep" checked> follow</label></h2>
    <div class="scroll md" id="report"><span class="empty">Waiting for analysis report…</span></div>
  </div>
</main>
<script>
const $ = id => document.getElementById(id);
function esc(s){ return String(s??'').replace(/[&<>"]/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function mdLite(src){
  // Minimal markdown: code fences, headings, bold, inline code, hrs, bullets.
  let h = esc(src), out = [], inPre = false, inList = false;
  for (const line of h.split('\\n')) {
    if (/^```/.test(line)) {
      out.push(inList ? '</ul>' : ''); inList = false;
      out.push(inPre ? '</pre>' : '<pre>'); inPre = !inPre; continue;
    }
    if (inPre) { out.push(line + '\\n'); continue; }
    let m;
    if (m = line.match(/^(#{1,4})\\s+(.*)/)) {
      if (inList) { out.push('</ul>'); inList = false; }
      const lvl = m[1].length;
      out.push(`<h${lvl}>${m[2]}</h${lvl}>`); continue;
    }
    if (/^\\s*---\\s*$/.test(line)) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push('<hr>'); continue;
    }
    if (/^\\s*[-*]\\s+/.test(line)) {
      if (!inList) { out.push('<ul>'); inList = true; }
      out.push('<li>' + line.replace(/^\\s*[-*]\\s+/, '') + '</li>'); continue;
    }
    if (inList) { out.push('</ul>'); inList = false; }
    out.push('<p>' + line + '</p>');
  }
  if (inList) out.push('</ul>');
  if (inPre) out.push('</pre>');
  return out.join('\\n')
    .replace(/\\*\\*(.+?)\\*\\*/g, '<b>$1</b>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}
function follow(el, box){ if (box.checked) el.scrollTop = el.scrollHeight; }
async function tick(){
  try {
    const r = await fetch('/api/state', {cache:'no-store'});
    const s = await r.json();
    const m = s.meta || {};
    $('meta').textContent =
      `${m.ticker||''}  ${m.analysis_date||''}  ${m.llm_provider||''}`.trim() || 'live';
    const st = s.stats || {};
    const mm = String(Math.floor((s.elapsed_seconds||0)/60)).padStart(2,'0');
    const ss = String((s.elapsed_seconds||0)%60).padStart(2,'0');
    $('stats').textContent =
      `Agents: ${s.agents_completed}/${s.agents_total} | LLM: ${st.llm_calls??'--'} | ` +
      `Tools: ${st.tool_calls??'--'} | Reports: ${s.reports_completed}/${s.reports_total} | ${mm}:${ss}`;
    $('progress').innerHTML = s.teams.map(t =>
      `<h3 style="color:var(--cyan);font-weight:normal">${esc(t.team)}</h3>` +
      '<table><tr><th>Agent</th><th>Status</th></tr>' +
      t.agents.map(a => {
        const stt = s.statuses[a] || 'pending';
        return `<tr><td>${esc(a)}</td><td class="st-${stt}">${esc(stt)}</td></tr>`;
      }).join('') + '</table>').join('') || '<span class="empty">No agents yet.</span>';
    const mel = $('messages');
    mel.innerHTML = s.messages.map(x =>
      `<div class="msg"><span class="meta">${esc(x.time)} · </span>` +
      `<span class="type">${esc(x.type)}</span><pre>${esc(x.content)}</pre></div>`
    ).join('') || '<span class="empty">No messages yet.</span>';
    follow(mel, $('follow-msg'));
    const rel = $('report');
    let html = s.current_report ? mdLite(s.current_report)
      : '<span class="empty">Waiting for analysis report…</span>';
    const secs = Object.entries(s.sections||{}).filter(([,c]) => c);
    if (secs.length)
      html += '<hr>' + secs.map(([k,c]) =>
        `<details><summary>${esc((s.section_titles||{})[k]||k)}</summary>` +
        `<div class="body md">${mdLite(c)}</div></details>`).join('');
    rel.innerHTML = html;
    follow(rel, $('follow-rep'));
    pollPrompt(s);
  } catch(e) { $('stats').textContent = 'reconnecting…'; }
}
let lastQ = null;
async function pollPrompt(s){
  const p = s.pending_prompt || {};
  const bar = $('promptbar');
  if (p.question) {
    bar.style.display = 'block';
    $('promptq').textContent = p.question + (p.default ? ` [${p.default}]` : '');
    if (lastQ !== p.question) { $('prompta').value = p.default || ''; lastQ = p.question; }
  } else { bar.style.display = 'none'; lastQ = null; }
}
$('promptsb').onclick = async () => {
  const v = $('prompta').value;
  await fetch('/api/answer', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({answer: v})});
};
$('prompta').onkeydown = e => { if (e.key === 'Enter') $('promptsb').click(); };
setInterval(tick, 1000); tick();
</script>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    server_version = "TradingAgentsDashboard/1"

    def log_message(self, *args):  # keep CLI output clean
        pass

    def _send_json(self, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] == "/api/state":
            try:
                snap = build_snapshot(
                    self.server.message_buffer,
                    getattr(self.server, "stats_handler", None),
                    getattr(self.server, "start_time", None),
                    getattr(self.server, "meta", None),
                )
                snap["pending_prompt"] = getattr(
                    self.server, "pending_prompt",
                    {"question": None, "default": None, "answer": None},
                )
            except Exception as exc:  # never break polling on a snapshot bug
                return self._send_json({"error": str(exc)})
            return self._send_json(snap)
        body = PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path.split("?")[0] != "/api/answer":
            self.send_response(404)
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception:
            return self._send_json({"ok": False, "error": "bad request"})
        prompt = getattr(self.server, "pending_prompt", None)
        answer = payload.get("answer")
        if prompt and prompt.get("question") and isinstance(answer, str):
            prompt["answer"] = answer
            return self._send_json({"ok": True})
        return self._send_json({"ok": False, "error": "no pending prompt"})


def find_free_port(host, start, tries=50):
    """Return the first free TCP port in ``[start, start + tries)``."""
    import socket

    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    return None


def start_dashboard(message_buffer, stats_handler=None, start_time=None,
                    meta=None, host="127.0.0.1", port=8765):
    """Start the dashboard thread. Returns ``(server, url)`` or ``(None, None)``.

    Each session gets its own port: when the base port is busy the next free
    one is picked automatically, so parallel runs (different tickers) each
    get a dashboard.
    """
    if os.environ.get("TRADINGAGENTS_WEB", "1") == "0":
        return None, None
    try:
        port = int(os.environ.get("TRADINGAGENTS_WEB_PORT", port))
    except ValueError:
        port = 8765
    port = find_free_port(host, port)
    if port is None:
        return None, None  # no free port nearby: CLI continues without dashboard
    try:
        server = ThreadingHTTPServer((host, port), _Handler)
    except OSError:
        return None, None
    server.daemon_threads = True
    server.message_buffer = message_buffer
    server.stats_handler = stats_handler
    server.start_time = start_time
    server.meta = meta
    # Post-run prompts (save/display report) are published here so they can
    # be answered from the page; see cli.main.ask_everywhere.
    server.pending_prompt = {"question": None, "default": None, "answer": None}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://{host}:{port}"


def stop_dashboard(server):
    if server is None:
        return
    try:
        server.shutdown()
        server.server_close()
    except Exception:
        pass
