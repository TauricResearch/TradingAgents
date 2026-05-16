"""PDF export service: markdown -> HTML -> PDF.

Uses ``markdown2`` for Markdown conversion and ``weasyprint`` for
HTML-to-PDF rendering.  Falls back with a clear ``ImportError`` if
weasyprint is not installed (it has native dependencies).

See also: PLAN-desktop.md, Phase 4.
"""

from __future__ import annotations

import html as html_mod
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Lazy imports (fail gracefully) ────────────────────────────────────────

try:
    import markdown2  # type: ignore[import-untyped]

    _MD_AVAILABLE = True
except ImportError:
    markdown2 = None  # type: ignore[assignment]
    _MD_AVAILABLE = False

_MD_EXTRAS = ["tables", "fenced-code-blocks", "strike", "task_list"]

# ── Dark-themed HTML template ─────────────────────────────────────────────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {{ size: A4; margin: 1.5cm; }}
  body {{
    background: #1a1a2e;
    color: #e0e0e0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 11pt;
    line-height: 1.5;
  }}
  .header {{
    border-bottom: 2px solid #16213e;
    padding-bottom: 12px;
    margin-bottom: 20px;
  }}
  .header h1 {{
    color: #4ecca3;
    margin: 0 0 4px 0;
    font-size: 18pt;
  }}
  .meta {{ color: #8892b0; font-size: 9pt; }}
  .verdict-badge {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 4px;
    font-weight: bold;
    font-size: 10pt;
    color: #fff;
  }}
  .verdict-buy {{ background: #2e7d32; }}
  .verdict-sell {{ background: #c62828; }}
  .verdict-hold {{ background: #f57f17; }}
  .verdict-default {{ background: #455a64; }}
  .section {{
    background: #16213e;
    border-radius: 6px;
    padding: 14px 18px;
    margin-bottom: 14px;
  }}
  .section h2 {{
    color: #4ecca3;
    font-size: 13pt;
    margin: 0 0 8px 0;
    border-bottom: 1px solid #1a1a2e;
    padding-bottom: 6px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 8px 0;
  }}
  th, td {{
    border: 1px solid #2a2a4a;
    padding: 6px 10px;
    text-align: left;
    font-size: 9pt;
  }}
  th {{ background: #0f3460; color: #4ecca3; }}
  code {{
    background: #0f3460;
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 9pt;
  }}
  pre {{
    background: #0f3460;
    padding: 10px;
    border-radius: 4px;
    overflow-x: auto;
    font-size: 9pt;
  }}
  .footer {{
    border-top: 1px solid #16213e;
    padding-top: 8px;
    margin-top: 24px;
    text-align: center;
    color: #555;
    font-size: 8pt;
  }}
</style>
</head>
<body>
{content}
</body>
</html>
"""


def _verdict_class(verdict: str) -> str:
    """Map a verdict string to a CSS class name."""
    v = verdict.upper()
    if v in ("BUY", "OVERWEIGHT"):
        return "verdict-buy"
    if v in ("SELL", "UNDERWEIGHT"):
        return "verdict-sell"
    if v == "HOLD":
        return "verdict-hold"
    return "verdict-default"


def _md_to_html(text: str) -> str:
    """Convert Markdown text to HTML, with fallback to plain <pre>."""
    if _MD_AVAILABLE and markdown2 is not None:
        return markdown2.markdown(text, extras=_MD_EXTRAS)
    # Minimal fallback: escape and wrap in <pre> to preserve formatting.
    return f"<pre>{html_mod.escape(text)}</pre>"


def _now_stamp() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _require_weasyprint():  # noqa: ANN202
    """Import weasyprint or raise a helpful error."""
    try:
        import weasyprint  # type: ignore[import-untyped]

        return weasyprint
    except ImportError as exc:
        raise ImportError(
            "weasyprint is required for PDF export but is not installed. "
            "Install with: pip install weasyprint  "
            "(Note: weasyprint requires system libraries — see "
            "https://doc.courtbouillon.org/weasyprint/stable/first_steps.html)"
        ) from exc


# ── Public service ────────────────────────────────────────────────────────


class PDFExporter:
    """Export analyses and summaries to dark-themed PDF files."""

    def export_analysis(
        self,
        *,
        result_dir: Path,
        ticker: str,
        verdict: str,
        date: str,
    ) -> Path:
        """Export a single analysis to PDF.

        Reads all ``.md`` files in *result_dir* and renders them as
        styled sections. Returns the path to the generated PDF.
        """
        weasyprint = _require_weasyprint()

        parts: list[str] = []

        # Header — escape user-controlled values to prevent XSS
        badge_cls = _verdict_class(verdict)
        esc_ticker = html_mod.escape(ticker)
        esc_date = html_mod.escape(date)
        esc_verdict = html_mod.escape(verdict.upper())
        parts.append(
            f'<div class="header">'
            f"<h1>TradingAgents &mdash; {esc_ticker}</h1>"
            f'<div class="meta">Analysis Date: {esc_date} &nbsp;|&nbsp; '
            f'<span class="{badge_cls} verdict-badge">{esc_verdict}</span>'
            f"</div></div>"
        )

        # Report sections
        md_files = sorted(result_dir.glob("**/*.md"))
        if not md_files:
            parts.append('<div class="section"><p>No report files found.</p></div>')

        for md_path in md_files:
            try:
                raw = md_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raw = f"*Error reading {md_path.name}: {exc}*"

            section_title = html_mod.escape(md_path.stem.replace("_", " ").title())
            html_body = _md_to_html(raw)
            parts.append(
                f'<div class="section">'
                f"<h2>{section_title}</h2>"
                f"{html_body}</div>"
            )

        # Footer
        parts.append(
            f'<div class="footer">'
            f"Generated by TradingAgents Desktop &mdash; {_now_stamp()}"
            f"</div>"
        )

        full_html = _HTML_TEMPLATE.format(content="\n".join(parts))

        out_path = result_dir / f"{ticker}_{date}_report.pdf"
        weasyprint.HTML(string=full_html).write_pdf(str(out_path))
        logger.info("Exported analysis PDF: %s", out_path)
        return out_path

    def export_summary(
        self,
        *,
        recommendations: list,  # list[RecommendationRow]
        prices: dict,  # dict[str, PriceResult]
    ) -> Path:
        """Export all active recommendations as a summary PDF.

        Returns the path to the generated file (in a temp-like location
        under ``~/.tradingagents/exports/``).
        """
        weasyprint = _require_weasyprint()

        parts: list[str] = []

        # Header
        parts.append(
            '<div class="header">'
            "<h1>TradingAgents &mdash; Portfolio Summary</h1>"
            f'<div class="meta">Generated: {_now_stamp()}</div>'
            "</div>"
        )

        # Summary table
        rows_html: list[str] = []
        for rec in recommendations:
            pr = prices.get(rec.ticker)
            current = pr.price if pr and pr.price else None
            change = ""
            if current is not None and rec.price_at_analysis:
                pct = ((current - rec.price_at_analysis) / rec.price_at_analysis) * 100
                color = "#4ecca3" if pct >= 0 else "#ef5350"
                change = f'<span style="color:{color}">{pct:+.2f}%</span>'

            badge_cls = _verdict_class(rec.verdict)
            rows_html.append(
                f"<tr>"
                f"<td><strong>{rec.ticker}</strong></td>"
                f'<td><span class="{badge_cls} verdict-badge">{rec.verdict}</span></td>'
                f"<td>{rec.confidence or 'N/A'}%</td>"
                f"<td>${rec.price_at_analysis or 0:.2f}</td>"
                f"<td>${current or 0:.2f}</td>"
                f"<td>{change}</td>"
                f"</tr>"
            )

        table = (
            '<div class="section"><h2>Active Recommendations</h2>'
            "<table><tr>"
            "<th>Ticker</th><th>Verdict</th><th>Confidence</th>"
            "<th>Entry Price</th><th>Current</th><th>Return</th>"
            "</tr>"
            + "\n".join(rows_html)
            + "</table></div>"
        )
        parts.append(table)

        # Footer
        parts.append(
            f'<div class="footer">'
            f"Generated by TradingAgents Desktop &mdash; {_now_stamp()}"
            f"</div>"
        )

        full_html = _HTML_TEMPLATE.format(content="\n".join(parts))

        export_dir = Path.home() / ".tradingagents" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_path = export_dir / f"summary_{stamp}.pdf"
        weasyprint.HTML(string=full_html).write_pdf(str(out_path))
        logger.info("Exported summary PDF: %s", out_path)
        return out_path
