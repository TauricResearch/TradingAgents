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
_MAX_CONTENT_CHARS = 6000

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
    agents = list(getattr(message_buffer, "message_agents", []))[-_MAX_MESSAGES:]
    entries = list(message_buffer.messages)[-_MAX_MESSAGES:]
    for i, (timestamp, msg_type, content) in enumerate(entries):
        agent = agents[i] if i < len(agents) else None
        combined.append(
            {"time": timestamp, "type": str(msg_type), "agent": agent,
             "content": clip(content)}
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
    try:
        last_activity_age = message_buffer.last_activity_age()
        current_agent = message_buffer.current_agent
    except Exception:
        last_activity_age = 0
        current_agent = None
    return {
        "meta": meta or {},
        "last_activity_age": last_activity_age,
        "current_agent": current_agent,
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
  :root { --bg:#fafafa; --panel:#ffffff; --border:#e5e5e5; --accent:#ea580c;
          --accent-soft:#fff3eb; --text:#111111; --dim:#6b7280; --green:#15803d;
          --yellow:#b45309; --red:#dc2626; --cyan:#0e7490; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font-family:Consolas,Menlo,monospace; font-size:14px; }
  header { padding:10px 16px; border-bottom:2px solid var(--accent);
           background:var(--panel); box-shadow:0 2px 8px rgba(0,0,0,.08); }
  header h1 { margin:0; font-size:16px; color:var(--text); }
  header h1 span { color:var(--accent); }
  header .sub { color:var(--dim); font-size:12px; }
  #stats { padding:6px 16px; color:var(--dim); font-size:12px;
           border-bottom:1px solid var(--border); background:var(--panel); }
  main { display:flex; flex-direction:column; gap:12px; padding:12px 16px;
         height:calc(100vh - 110px); }
  .row { display:flex; gap:12px; min-height:0; flex:1.1; }
  .panel { background:var(--panel); border:1px solid var(--border);
           border-radius:10px; display:flex; flex-direction:column; min-width:0;
           box-shadow:0 4px 14px rgba(0,0,0,.10); }
  .panel.grow { flex:1.4; }
  .panel h2 { margin:0; padding:8px 12px; font-size:13px; font-weight:bold;
              color:var(--text); border-bottom:2px solid var(--accent);
              display:flex; justify-content:space-between; align-items:center; }
  .panel h2 label { font-size:11px; color:var(--dim); font-weight:normal; }
  .scroll { overflow-y:auto; padding:8px 12px; min-height:0; }
  #report-panel { flex:1; }
  table { border-collapse:collapse; width:100%; }
  th { color:var(--accent); font-weight:bold; padding:4px 8px;
       border-bottom:1px solid var(--border); }
  td { padding:4px 8px; border-bottom:1px solid #f0f0f0; vertical-align:top; }
  .st-completed { color:var(--green); } .st-pending { color:var(--yellow); }
  .st-in_progress { color:var(--accent); font-weight:bold; } .st-error { color:var(--red); }
  .msg { border-bottom:1px solid #f0f0f0; padding:6px 0; }
  .msg .meta { color:var(--dim); font-size:12px; }
  .msg .type { color:var(--accent); font-weight:bold; }
  .msg pre { white-space:pre-wrap; word-break:break-word; margin:4px 0 0; }
  .md h1,.md h2,.md h3 { color:var(--accent); } .md hr { border-color:var(--border); }
  .md code { background:#f4f4f4; padding:0 4px; border-radius:3px; }
  .md pre { background:#111111; color:#f5f5f5; padding:8px; border-radius:6px;
            overflow-x:auto; white-space:pre-wrap; }
  details { margin:8px 0; border:1px solid var(--border); border-radius:8px;
            box-shadow:0 2px 6px rgba(0,0,0,.06); }
  summary { cursor:pointer; padding:6px 10px; color:var(--accent); font-weight:bold; }
  details .body { padding:0 10px 10px; }
  .empty { color:var(--dim); font-style:italic; }
  #activity { position:fixed; right:16px; bottom:16px; width:360px; max-height:46vh;
              background:var(--panel); border:2px solid var(--accent); border-radius:12px;
              box-shadow:0 10px 30px rgba(0,0,0,.25); display:flex; flex-direction:column;
              z-index:50; }
  #activity header { padding:8px 12px; cursor:move; border-bottom:2px solid var(--accent);
                     border-radius:10px 10px 0 0; font-weight:bold; background:var(--accent-soft);
                     display:flex; justify-content:space-between; align-items:center; }
  #activity header h1 { font-size:13px; margin:0; color:var(--text); }
  #activity header button { border:0; background:transparent; cursor:pointer; font-size:14px; }
  #actlist { overflow-y:auto; padding:4px 12px 10px; }
  .act { border-bottom:1px solid #f0f0f0; padding:6px 0; cursor:pointer; }
  .act:hover { background:var(--accent-soft); }
  .act .meta { color:var(--dim); font-size:11px; }
  .act .prev { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-size:12px; }
  #actmodal { position:fixed; inset:0; background:rgba(0,0,0,.55); display:none;
              align-items:center; justify-content:center; z-index:100; }
  #actmodal .box { background:#fff; color:#111; border-radius:12px; max-width:720px;
                   width:90%; max-height:80vh; display:flex; flex-direction:column;
                   box-shadow:0 20px 60px rgba(0,0,0,.4); }
  #actmodal .box header { border-radius:12px 12px 0 0; }
  #actmodal .box pre { overflow-y:auto; padding:12px 16px; white-space:pre-wrap;
                       word-break:break-word; margin:0; }
</style>
</head>
<body>
<header>
  <h1>TradingAgents <span>Dashboard</span></h1>
  <div class="sub" id="meta">connecting…</div>
</header>
<div id="stats">connecting…</div>
<div id="promptbar" style="display:none;padding:8px 16px;border-bottom:2px solid var(--accent);background:#fff7ed">
  <span id="promptq" style="color:var(--accent);font-weight:bold"></span>
  <input id="prompta" style="margin-left:8px;background:#fff;color:var(--text);border:1px solid var(--border);border-radius:4px;padding:4px 8px;width:40%">
  <button id="promptsb" style="margin-left:8px;background:var(--accent);color:#fff;border:0;border-radius:4px;padding:5px 14px;cursor:pointer">Send</button>
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
<div id="activity">
  <header id="acthead"><h1>Live activity</h1><button id="actmin" title="collapse">–</button></header>
  <div id="actlist"><span class="empty">Waiting for agent events…</span></div>
</div>
<div id="actmodal"><div class="box">
  <header><h1 id="acttitle">Event</h1><button id="actclose" title="close">✕</button></header>
  <pre id="actbody"></pre>
</div></div>
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
    const age = s.last_activity_age ?? 0;
    const who = s.current_agent || 'idle';
    $('stats').textContent =
      `Agents: ${s.agents_completed}/${s.agents_total} | LLM: ${st.llm_calls??'--'} | ` +
      `Tools: ${st.tool_calls??'--'} | Reports: ${s.reports_completed}/${s.reports_total} | ${mm}:${ss} | ` +
      `● ${who} ${age}s ago`;
    renderActivity(s.messages || []);
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
// Floating activity card: newest events, click for full context, draggable.
let actMin = false;
$('actmin').onclick = () => {
  actMin = !actMin;
  $('actlist').style.display = actMin ? 'none' : 'block';
  $('actmin').textContent = actMin ? '+' : '–';
};
$('actclose').onclick = () => { $('actmodal').style.display = 'none'; };
$('actmodal').onclick = e => { if (e.target.id === 'actmodal') $('actmodal').style.display = 'none'; };
function renderActivity(msgs){
  const list = $('actlist');
  // Agent messages only — tool calls already live in Messages & Tools.
  const agents = msgs.map((x, i) => ({...x, i})).filter(x => x.type !== 'Tool');
  const items = agents.slice(-30).reverse();
  if (!items.length) { list.innerHTML = '<span class="empty">Waiting for agent messages…</span>'; return; }
  list.innerHTML = items.map(x => {
    const prev = String(x.content || '').replace(/\\s+/g, ' ').slice(0, 140);
    const who = x.agent ? esc(x.agent) + ' · ' : '';
    return `<div class="act" data-i="${x.i}">` +
      `<div class="meta">${who}${esc(x.time)} · ${esc(x.type)}</div>` +
      `<div class="prev">${esc(prev)}${String(x.content || '').length > 140 ? '…' : ''}</div></div>`;
  }).join('');
  list.querySelectorAll('.act').forEach(el => {
    el.onclick = () => {
      const x = msgs[+el.dataset.i];
      $('acttitle').textContent = `${x.agent ? x.agent + ' · ' : ''}${x.time} · ${x.type}`;
      $('actbody').textContent = x.content || '(empty)';
      $('actmodal').style.display = 'flex';
    };
  });
}
(function drag(){
  const card = $('activity'), head = $('acthead');
  let sx=0, sy=0, ox=0, oy=0, on=false;
  head.addEventListener('mousedown', e => {
    on = true;
    const r = card.getBoundingClientRect();
    card.style.left = r.left + 'px'; card.style.top = r.top + 'px';
    card.style.right = 'auto'; card.style.bottom = 'auto';
    sx = e.clientX; sy = e.clientY; ox = r.left; oy = r.top;
  });
  document.addEventListener('mousemove', e => {
    if (!on) return;
    card.style.left = (ox + e.clientX - sx) + 'px';
    card.style.top = (oy + e.clientY - sy) + 'px';
  });
  document.addEventListener('mouseup', () => { on = false; });
})();
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
