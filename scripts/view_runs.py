"""Generate an HTML dashboard from raw.jsonl and open it in the browser.

Usage:
    python3 scripts/view_runs.py
    python3 scripts/view_runs.py --symbol BTC/USDT
    python3 scripts/view_runs.py --no-open   # chỉ tạo file, không mở browser
"""

from __future__ import annotations

import argparse
import json
import os
import re
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from tradingagents.default_config import CRYPTO_TRAIN_CONFIG


RATING_COLOR = {
    "buy": "#16a34a",
    "overweight": "#16a34a",
    "bullish": "#16a34a",
    "hold": "#ca8a04",
    "neutral": "#ca8a04",
    "sell": "#dc2626",
    "underweight": "#dc2626",
    "bearish": "#dc2626",
    "wait": "#6b7280",
}

ACTION_ICON = {
    "buy": "🟢",
    "overweight": "🟢",
    "bullish": "🟢",
    "hold": "🟡",
    "neutral": "🟡",
    "wait": "⚪",
    "sell": "🔴",
    "underweight": "🔴",
    "bearish": "🔴",
    "reduce": "🟠",
}


def _rating_color(rating: str) -> str:
    return RATING_COLOR.get(rating.lower().strip(), "#6b7280")


def _action_icon(rating: str) -> str:
    return ACTION_ICON.get(rating.lower().strip(), "❓")


def _extract_field(decision: str, field: str) -> str:
    """Trích giá trị từ Decision text, ví dụ 'Confidence: 0.75'."""
    pattern = rf"(?i)\*{{0,2}}{re.escape(field)}\*{{0,2}}[:\s]+([^\n*]+)"
    m = re.search(pattern, decision)
    return m.group(1).strip() if m else "—"


def _md_to_html(text: str) -> str:
    """Minimal markdown → HTML: bold, italic, bullet lists."""
    # Escape HTML first
    import html
    text = html.escape(text)
    # Bold **...**
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Italic *...*
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    # Bullet lines starting with * or -
    lines = []
    in_list = False
    for line in text.split("\n"):
        stripped = line.strip()
        if re.match(r"^[*\-•]\s+", stripped):
            if not in_list:
                lines.append("<ul>")
                in_list = True
            lines.append(f"<li>{re.sub(r'^[*\\-•]\\s+', '', stripped)}</li>")
        else:
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append(f"{line}<br>")
    if in_list:
        lines.append("</ul>")
    return "\n".join(lines)


def load_runs(jsonl_path: Path, symbol_filter: str | None = None) -> list[dict]:
    runs = []
    if not jsonl_path.exists():
        return runs
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if symbol_filter and d.get("symbol", "") != symbol_filter:
                continue
            runs.append(d)
    # Newest first
    runs.sort(key=lambda r: r.get("timestamp_utc", r.get("trade_date", "")), reverse=True)
    return runs


def build_html(runs: list[dict], output_path: Path) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    symbols = sorted({r.get("symbol", "?") for r in runs})

    cards = []
    for r in runs:
        symbol = r.get("symbol", "?")
        trade_date = r.get("trade_date", "?")
        ts = r.get("timestamp_utc", "")
        rating = r.get("rating", "Unknown")
        decision = r.get("final_trade_decision", "")

        action = _extract_field(decision, "Action")
        confidence = _extract_field(decision, "Confidence")
        entry = _extract_field(decision, "Entry Zone")
        sl = _extract_field(decision, "Stop Loss")
        tp = _extract_field(decision, "Take Profit")
        reasoning_m = re.search(r"(?i)\*{0,2}Reasoning\*{0,2}[:\s]+(.+?)(?=\n\n|\Z)", decision, re.DOTALL)
        reasoning = reasoning_m.group(1).strip()[:400] if reasoning_m else decision[:400]

        color = _rating_color(rating)
        icon = _action_icon(rating)

        reports = r.get("reports", {})
        market_report = reports.get("market", "")
        news_report = reports.get("news", "") or reports.get("news_report", "")
        sentiment_report = reports.get("sentiment", "") or reports.get("sentiment_report", "")

        card_id = f"card_{id(r)}"
        cards.append(f"""
<div class="card" id="{card_id}">
  <div class="card-header" style="border-left: 5px solid {color}">
    <div class="card-title">
      <span class="icon">{icon}</span>
      <strong>{symbol}</strong>
      <span class="badge" style="background:{color}">{rating}</span>
      <span class="date">{trade_date} &nbsp;·&nbsp; {ts[:16] if ts else ""} UTC</span>
    </div>
    <button class="toggle-btn" onclick="toggle('{card_id}')">Chi tiết ▼</button>
  </div>
  <div class="summary-row">
    <div class="summary-item"><label>Action</label><span style="color:{color}">{action}</span></div>
    <div class="summary-item"><label>Confidence</label><span>{confidence}</span></div>
    <div class="summary-item"><label>Entry Zone</label><span>{entry}</span></div>
    <div class="summary-item"><label>Stop Loss</label><span>{sl}</span></div>
    <div class="summary-item"><label>Take Profit</label><span>{tp}</span></div>
  </div>
  <div class="reasoning"><em>Reasoning:</em> {reasoning}…</div>
  <div class="detail" id="detail_{card_id}" style="display:none">
    <h4>Phân tích đầy đủ</h4>
    <div class="full-decision">{_md_to_html(decision)}</div>
    {"<h4>Market Data</h4><pre class='report'>" + market_report[:1500] + "</pre>" if market_report else ""}
    {"<h4>News</h4><pre class='report'>" + news_report[:1000] + "</pre>" if news_report else ""}
    {"<h4>Sentiment</h4><pre class='report'>" + sentiment_report[:500] + "</pre>" if sentiment_report else ""}
  </div>
</div>""")

    symbol_buttons = " ".join(
        f'<button class="sym-btn" onclick="filterSymbol(\'{s}\')">{s}</button>'
        for s in symbols
    )

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TradingAgents – Crypto Runs</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }}
  h1 {{ color: #f8fafc; margin-bottom: 4px; }}
  .meta {{ color: #94a3b8; font-size: 13px; margin-bottom: 16px; }}
  .filter-bar {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }}
  .sym-btn {{ background: #1e293b; border: 1px solid #334155; color: #cbd5e1; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; }}
  .sym-btn:hover, .sym-btn.active {{ background: #3b82f6; border-color: #3b82f6; color: #fff; }}
  .sym-btn.all {{ background: #475569; border-color: #475569; color: #fff; }}
  .card {{ background: #1e293b; border-radius: 10px; margin-bottom: 16px; overflow: hidden; transition: box-shadow .2s; }}
  .card:hover {{ box-shadow: 0 0 0 1px #3b82f6; }}
  .card-header {{ padding: 14px 16px; display: flex; justify-content: space-between; align-items: center; background: #1e293b; }}
  .card-title {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
  .icon {{ font-size: 20px; }}
  .badge {{ font-size: 11px; padding: 2px 8px; border-radius: 12px; color: #fff; font-weight: 600; text-transform: uppercase; }}
  .date {{ color: #64748b; font-size: 12px; }}
  .toggle-btn {{ background: #334155; border: none; color: #94a3b8; padding: 5px 10px; border-radius: 6px; cursor: pointer; font-size: 12px; }}
  .toggle-btn:hover {{ background: #475569; color: #fff; }}
  .summary-row {{ display: flex; flex-wrap: wrap; gap: 0; border-top: 1px solid #334155; }}
  .summary-item {{ flex: 1; min-width: 100px; padding: 10px 16px; border-right: 1px solid #334155; }}
  .summary-item:last-child {{ border-right: none; }}
  .summary-item label {{ display: block; font-size: 10px; color: #64748b; text-transform: uppercase; margin-bottom: 2px; }}
  .summary-item span {{ font-size: 14px; font-weight: 600; }}
  .reasoning {{ padding: 10px 16px; font-size: 13px; color: #94a3b8; border-top: 1px solid #334155; }}
  .detail {{ padding: 16px; border-top: 1px solid #334155; }}
  .detail h4 {{ color: #94a3b8; font-size: 12px; text-transform: uppercase; margin: 12px 0 6px; }}
  .full-decision {{ font-size: 14px; line-height: 1.7; color: #cbd5e1; }}
  pre.report {{ font-size: 11px; background: #0f172a; padding: 10px; border-radius: 6px; overflow-x: auto; color: #94a3b8; white-space: pre-wrap; }}
  .stats {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 20px; }}
  .stat-box {{ background: #1e293b; border-radius: 8px; padding: 12px 20px; min-width: 150px; }}
  .stat-box .val {{ font-size: 28px; font-weight: 700; }}
  .stat-box .lbl {{ font-size: 12px; color: #64748b; }}
  .hidden {{ display: none !important; }}
</style>
</head>
<body>
<h1>📊 TradingAgents – Crypto Runs</h1>
<div class="meta">Cập nhật: {now} &nbsp;·&nbsp; Tổng: {len(runs)} lần phân tích</div>

<div class="stats">
  <div class="stat-box"><div class="val" style="color:#16a34a">{sum(1 for r in runs if r.get('rating','').lower() in ('buy','overweight','bullish'))}</div><div class="lbl">BUY / Overweight</div></div>
  <div class="stat-box"><div class="val" style="color:#ca8a04">{sum(1 for r in runs if r.get('rating','').lower() in ('hold','neutral','wait'))}</div><div class="lbl">HOLD / Neutral</div></div>
  <div class="stat-box"><div class="val" style="color:#dc2626">{sum(1 for r in runs if r.get('rating','').lower() in ('sell','underweight','bearish'))}</div><div class="lbl">SELL / Underweight</div></div>
  <div class="stat-box"><div class="val">{len(symbols)}</div><div class="lbl">Symbols</div></div>
</div>

<div class="filter-bar">
  <button class="sym-btn all" onclick="filterSymbol('all')">Tất cả</button>
  {symbol_buttons}
</div>

<div id="runs-list">
{''.join(cards)}
</div>

<script>
function toggle(id) {{
  const d = document.getElementById('detail_' + id);
  const btn = document.querySelector('#' + id + ' .toggle-btn');
  if (d.style.display === 'none') {{ d.style.display = 'block'; btn.textContent = 'Thu gọn ▲'; }}
  else {{ d.style.display = 'none'; btn.textContent = 'Chi tiết ▼'; }}
}}
function filterSymbol(sym) {{
  document.querySelectorAll('.sym-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  document.querySelectorAll('.card').forEach(c => {{
    const title = c.querySelector('.card-title strong').textContent;
    c.classList.toggle('hidden', sym !== 'all' && title !== sym);
  }});
}}
</script>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Tạo HTML viewer cho crypto runs")
    parser.add_argument("--symbol", default=None, help="Lọc theo symbol, ví dụ BTC/USDT")
    parser.add_argument("--no-open", action="store_true", help="Chỉ tạo file, không mở browser")
    parser.add_argument("--out", default=None, help="Đường dẫn file HTML output")
    args = parser.parse_args()

    config = CRYPTO_TRAIN_CONFIG
    memory_dir = Path(config.get("crypto_memory_dir", Path.home() / ".tradingagents" / "crypto_memory"))
    jsonl_path = memory_dir / "raw.jsonl"

    out_path = Path(args.out) if args.out else memory_dir / "runs.html"

    runs = load_runs(jsonl_path, symbol_filter=args.symbol)
    if not runs:
        print(f"Không có dữ liệu trong {jsonl_path}")
        return

    build_html(runs, out_path)
    print(f"✓ Đã tạo: {out_path}  ({len(runs)} runs)")

    if not args.no_open:
        webbrowser.open(out_path.as_uri())


if __name__ == "__main__":
    main()
