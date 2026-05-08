"""Export a finished run to markdown, PDF, or standalone interactive HTML.

All exports go to ``~/.tradingagents/exports/<TICKER>/<run_id>__<trade_date>__<utc_ts>.<ext>``.
The path is chosen so re-running the same ticker+date never overwrites
a prior export — every export is timestamped and tied to the run_id.

The three formats serve different jobs:
- **markdown**: cheap, diffable, easy to paste into anywhere.
- **PDF**: archive-ready static document rendered with matplotlib PdfPages.
- **standalone HTML**: a single self-contained file that renders the run
  with tabs in vanilla JS — emailable, viewable offline, no server
  needed.

Standalone HTML / markdown render prettier markdown when ``markdown`` is
installed but degrade gracefully to plain text if not.
"""

from __future__ import annotations

import html
import io
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from tradingagents.default_config import DEFAULT_CONFIG

try:
    import markdown as _md
    _HAS_MARKDOWN = True
except Exception:  # pragma: no cover
    _md = None
    _HAS_MARKDOWN = False

EXPORTS_DIR = Path(str(DEFAULT_CONFIG.get("results_dir", Path.home() / ".tradingagents" / "logs"))).parent / "exports"


# ---------------------------------------------------------------------------
# Section assembly
# ---------------------------------------------------------------------------

# Display order and the state-dict key each section reads from.
_SECTIONS: list[tuple[str, str | None]] = [
    ("Market", "market_report"),
    ("Sentiment", "sentiment_report"),
    ("News", "news_report"),
    ("Fundamentals", "fundamentals_report"),
    ("Bull vs Bear", None),
    ("Research Mgr", None),
    ("Trader Plan", None),
    ("Risk Debate", None),
    ("Final Decision", "final_trade_decision"),
]


def _section_body(state: Dict[str, Any], label: str, key: Optional[str]) -> str:
    """Return the markdown body for one section."""
    if label == "Bull vs Bear":
        d = state.get("investment_debate_state") or {}
        bull = d.get("bull_history") or "_(no content)_"
        bear = d.get("bear_history") or "_(no content)_"
        return f"### Bull\n\n{bull}\n\n### Bear\n\n{bear}\n"
    if label == "Research Mgr":
        d = state.get("investment_debate_state") or {}
        return d.get("judge_decision") or "_(no content)_"
    if label == "Trader Plan":
        return (state.get("trader_investment_decision")
                or state.get("trader_investment_plan")
                or state.get("investment_plan")
                or "_(no content)_")
    if label == "Risk Debate":
        d = state.get("risk_debate_state") or {}
        parts = []
        for side, k in (("Aggressive", "aggressive_history"),
                        ("Conservative", "conservative_history"),
                        ("Neutral", "neutral_history")):
            parts.append(f"### {side}\n\n{d.get(k) or '_(no content)_'}\n")
        if d.get("judge_decision"):
            parts.append(f"### Risk Judge\n\n{d['judge_decision']}\n")
        return "\n".join(parts)
    if key:
        return state.get(key) or "_(no content)_"
    return "_(no content)_"


def _meta_header(meta: Dict[str, Any]) -> str:
    """Top metadata block shared by markdown/HTML/PDF."""
    ticker = meta.get("ticker", "?")
    trade_date = meta.get("trade_date", "?")
    decision = meta.get("decision") or "—"
    provider = meta.get("provider") or "—"
    deep = meta.get("deep_model") or "—"
    quick = meta.get("quick_model") or "—"
    started = meta.get("started_at") or ""
    completed = meta.get("completed_at") or ""
    tokens_in = meta.get("tokens_in") or 0
    tokens_out = meta.get("tokens_out") or 0
    run_id = meta.get("run_id") or "—"
    return (
        f"# {ticker} — {trade_date}\n\n"
        f"**Decision:** {decision}  \n"
        f"**Provider:** {provider}  \n"
        f"**Deep model:** {deep}  \n"
        f"**Quick model:** {quick}  \n"
        f"**Started:** {started}  \n"
        f"**Completed:** {completed}  \n"
        f"**Tokens in / out:** {tokens_in:,} / {tokens_out:,}  \n"
        f"**Run id:** `{run_id}`\n"
    )


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------

def render_markdown(state: Dict[str, Any], meta: Dict[str, Any]) -> str:
    parts = [_meta_header(meta), "\n---\n"]
    for label, key in _SECTIONS:
        parts.append(f"\n## {label}\n\n")
        parts.append(_section_body(state, label, key))
        parts.append("\n")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Standalone interactive HTML
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  :root {{
    --fg: #1e1e1e; --muted: #6a6a6a; --bg: #fafafa; --card: #fff;
    --accent: #1f6feb; --border: #e0e0e0; --tab-active: #1f6feb;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --fg: #e6e6e6; --muted: #9a9a9a; --bg: #0d1117; --card: #161b22; --border: #30363d; }}
  }}
  html, body {{ margin: 0; padding: 0; background: var(--bg); color: var(--fg); font-family: -apple-system, "Segoe UI", Roboto, sans-serif; }}
  .wrap {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
  header h1 {{ margin: 0 0 4px 0; }}
  header .meta {{ color: var(--muted); font-size: 14px; margin-bottom: 16px; }}
  header .meta b {{ color: var(--fg); }}
  .tabs {{ display: flex; flex-wrap: wrap; gap: 4px; border-bottom: 1px solid var(--border); margin-bottom: 16px; }}
  .tab {{
    padding: 8px 14px; cursor: pointer; border: 1px solid transparent;
    border-bottom: none; border-radius: 6px 6px 0 0; color: var(--muted);
    user-select: none; font-size: 14px;
  }}
  .tab:hover {{ color: var(--fg); }}
  .tab.active {{ color: var(--tab-active); border-color: var(--border); background: var(--card); border-bottom: 1px solid var(--card); margin-bottom: -1px; }}
  .panel {{ display: none; background: var(--card); border: 1px solid var(--border); border-top: none; padding: 18px 22px; border-radius: 0 6px 6px 6px; }}
  .panel.active {{ display: block; }}
  .panel h2, .panel h3 {{ margin-top: 0; }}
  .panel p, .panel li {{ line-height: 1.55; }}
  pre, code {{ font-family: ui-monospace, "Cascadia Code", monospace; }}
  pre {{ background: rgba(127,127,127,0.08); padding: 12px; border-radius: 6px; overflow-x: auto; }}
  blockquote {{ border-left: 3px solid var(--accent); margin: 0; padding-left: 12px; color: var(--muted); }}
  .footer {{ color: var(--muted); font-size: 12px; margin-top: 24px; text-align: right; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>{ticker} <span style="color: var(--muted)">— {trade_date}</span></h1>
    <div class="meta">
      <b>Decision:</b> {decision} &nbsp;·&nbsp;
      <b>{provider}</b> · deep <code>{deep}</code> · quick <code>{quick}</code> &nbsp;·&nbsp;
      <b>tokens:</b> {tokens_in:,} in / {tokens_out:,} out &nbsp;·&nbsp;
      <span title="{started} → {completed}">{completed}</span>
    </div>
  </header>
  <div class="tabs" id="tabs">{tab_buttons}</div>
  {panels}
  <div class="footer">Exported {exported_at} · run id <code>{run_id}</code></div>
</div>
<script>
(function() {{
  var tabs = document.querySelectorAll('.tab');
  var panels = document.querySelectorAll('.panel');
  function activate(name) {{
    tabs.forEach(function(t) {{ t.classList.toggle('active', t.dataset.tab === name); }});
    panels.forEach(function(p) {{ p.classList.toggle('active', p.dataset.tab === name); }});
  }}
  tabs.forEach(function(t) {{
    t.addEventListener('click', function() {{ activate(t.dataset.tab); }});
  }});
  if (tabs.length) activate(tabs[0].dataset.tab);
}})();
</script>
</body>
</html>
"""


def _md_to_html(text: str) -> str:
    """Render markdown text → HTML, falling back to a <pre> block if the
    ``markdown`` library isn't installed."""
    if not text:
        return "<p><em>(no content)</em></p>"
    if _HAS_MARKDOWN:
        return _md.markdown(text, extensions=["extra", "sane_lists"])
    return f"<pre>{html.escape(text)}</pre>"


def render_html(state: Dict[str, Any], meta: Dict[str, Any]) -> str:
    tab_buttons = []
    panels = []
    for i, (label, key) in enumerate(_SECTIONS):
        body_md = _section_body(state, label, key)
        body_html = _md_to_html(body_md)
        tab_buttons.append(f'<div class="tab" data-tab="t{i}">{html.escape(label)}</div>')
        panels.append(
            f'<div class="panel" data-tab="t{i}"><h2>{html.escape(label)}</h2>{body_html}</div>'
        )

    return _HTML_TEMPLATE.format(
        title=html.escape(f"{meta.get('ticker', '?')} – {meta.get('trade_date', '?')} TradingAgents report"),
        ticker=html.escape(meta.get("ticker", "?")),
        trade_date=html.escape(meta.get("trade_date", "?")),
        decision=html.escape(meta.get("decision") or "—"),
        provider=html.escape(meta.get("provider") or "—"),
        deep=html.escape(meta.get("deep_model") or "—"),
        quick=html.escape(meta.get("quick_model") or "—"),
        tokens_in=int(meta.get("tokens_in") or 0),
        tokens_out=int(meta.get("tokens_out") or 0),
        started=html.escape(meta.get("started_at") or ""),
        completed=html.escape(meta.get("completed_at") or ""),
        run_id=html.escape(meta.get("run_id") or "—"),
        exported_at=html.escape(datetime.utcnow().isoformat(timespec="seconds") + "Z"),
        tab_buttons="".join(tab_buttons),
        panels="".join(panels),
    )


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------

def _pdf_title(meta: Dict[str, Any]) -> str:
    return f"{meta.get('ticker', '?')} - {meta.get('trade_date', '?')} TradingAgents report"


_PDF_CSS = ""


def _pdf_html(state: Dict[str, Any], meta: Dict[str, Any]) -> str:
    sections_html = []
    for label, key in _SECTIONS:
        body_md = _section_body(state, label, key)
        body_html = _md_to_html(body_md)
        sections_html.append(
            f'<div class="section"><h2>{html.escape(label)}</h2>{body_html}</div>'
        )

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>{_PDF_CSS}</style></head>
<body>
<h1>{html.escape(meta.get('ticker', '?'))} — {html.escape(meta.get('trade_date', '?'))}</h1>
<div class="meta">
  Decision: <b>{html.escape(meta.get('decision') or '—')}</b><br/>
  {html.escape(meta.get('provider') or '—')} · deep <code>{html.escape(meta.get('deep_model') or '—')}</code> ·
  quick <code>{html.escape(meta.get('quick_model') or '—')}</code><br/>
  Tokens: {int(meta.get('tokens_in') or 0):,} in / {int(meta.get('tokens_out') or 0):,} out<br/>
  Started: {html.escape(meta.get('started_at') or '—')} &nbsp; Completed: {html.escape(meta.get('completed_at') or '—')}<br/>
  Run id: <code>{html.escape(meta.get('run_id') or '—')}</code>
</div>
{"".join(sections_html)}
</body></html>"""


def _pdf_pages(markdown_text: str) -> list[str]:
    wrapped_lines: list[str] = []
    for raw_line in markdown_text.splitlines():
        if not raw_line:
            wrapped_lines.append("")
            continue
        wrapped_lines.extend(textwrap.wrap(raw_line, width=96, replace_whitespace=False) or [raw_line])

    lines_per_page = 58
    pages = [
        "\n".join(wrapped_lines[start:start + lines_per_page])
        for start in range(0, len(wrapped_lines), lines_per_page)
    ]
    return pages or [""]


def render_pdf(state: Dict[str, Any], meta: Dict[str, Any]) -> bytes:
    """Render a print-friendly PDF using matplotlib's built-in PDF backend."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    title = _pdf_title(meta)
    out = io.BytesIO()

    with PdfPages(out) as pdf:
        info = pdf.infodict()
        info["Title"] = title
        info["Subject"] = "TradingAgents GUI export"
        info["Creator"] = "TradingAgents"
        info["Keywords"] = "; ".join(
            f"{key}: {value}"
            for key, value in meta.items()
            if value is not None and key in {"ticker", "trade_date", "decision", "provider", "run_id"}
        )

        for page_number, body in enumerate(_pdf_pages(render_markdown(state, meta)), start=1):
            fig = plt.figure(figsize=(8.5, 11))
            fig.patch.set_facecolor("white")
            fig.text(0.07, 0.95, title, fontsize=14, fontweight="bold", va="top")
            fig.text(
                0.07,
                0.90,
                body,
                fontsize=9,
                family="monospace",
                va="top",
                linespacing=1.25,
            )
            fig.text(0.5, 0.03, f"Page {page_number}", fontsize=8, ha="center", color="#666666")
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

    return out.getvalue()


# ---------------------------------------------------------------------------
# Path planning + write helpers
# ---------------------------------------------------------------------------

def export_basename(meta: Dict[str, Any]) -> str:
    """Stable, never-overwriting basename: ``<run_id>__<date>__<ts>``.

    Falls back to a hash of the source log path when ``run_id`` is missing
    so legacy CLI runs can still be exported uniquely.
    """
    run_id = meta.get("run_id") or ""
    if not run_id:
        seed = meta.get("log_path") or meta.get("ticker", "")
        run_id = "legacy-" + str(abs(hash(seed)))[:8]
    trade_date = meta.get("trade_date", "unknown")
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return f"{run_id}__{trade_date}__{ts}"


def export_path(meta: Dict[str, Any], ext: str) -> Path:
    """Return the disk path an export of this run should be written to.

    Layout: ``<exports>/<TICKER>/<basename>.<ext>``. The folder is created
    if it doesn't exist.
    """
    ticker = meta.get("ticker", "UNKNOWN") or "UNKNOWN"
    folder = EXPORTS_DIR / ticker
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{export_basename(meta)}.{ext.lstrip('.')}"


def write_export(content: str | bytes, meta: Dict[str, Any], ext: str) -> Path:
    """Write ``content`` to a fresh, never-overwriting export path."""
    path = export_path(meta, ext)
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_bytes(content)
    return path


def list_exports_for_run(meta: Dict[str, Any]) -> Dict[str, Path]:
    """Find existing exports for a run id under the exports tree.

    Looks for files starting with ``<run_id>__`` so re-export creates new
    timestamped files but the page can still surface the most recent of
    each format if desired.
    """
    out: Dict[str, Path] = {}
    ticker = meta.get("ticker") or ""
    run_id = meta.get("run_id") or ""
    if not ticker or not run_id:
        return out
    folder = EXPORTS_DIR / ticker
    if not folder.exists():
        return out
    for ext in ("md", "html", "pdf"):
        matches = sorted(folder.glob(f"{run_id}__*.{ext}"))
        if matches:
            out[ext] = matches[-1]  # most recent
    return out


def has_pdf_support() -> bool:
    return True
