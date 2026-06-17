"""Persist a TradingAgents run to disk and produce downstream artefacts.

Two consumers today: the interactive CLI (``cli.main``) and the headless
``scripts/run_daily.py`` scheduled runner. Both build the same
``reports/<TICKER>_<TIMESTAMP>/`` folder tree, so the logic lives here.

Also exposes the small helpers the scheduled runner needs on top of the raw
artefacts: parse the Portfolio Manager decision into structured fields, and
render the same ``decision.md`` to a PDF for Telegram delivery.
"""

from __future__ import annotations

import datetime as _dt
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def save_report_to_disk(final_state: dict[str, Any], ticker: str, save_path: Path) -> Path:
    """Write the canonical reports folder for one run.

    Layout::

        save_path/
            1_analysts/{market,sentiment,news,fundamentals}.md
            2_research/{bull,bear,manager}.md
            3_trading/trader.md
            4_risk/{aggressive,conservative,neutral}.md
            5_portfolio/decision.md     <-- Portfolio Manager final decision
            complete_report.md           <-- all of the above concatenated

    Returns the path to ``complete_report.md``. The decision.md file is
    always the last thing the Portfolio Manager emits, so it is the only
    artefact the Telegram notifier needs to read.
    """
    save_path = Path(save_path)
    save_path.mkdir(parents=True, exist_ok=True)
    sections: list[str] = []

    # 1. Analysts
    analyst_parts: list[tuple[str, str]] = []
    if final_state.get("market_report"):
        _write_section(save_path / "1_analysts", "market.md", final_state["market_report"])
        analyst_parts.append(("Market Analyst", final_state["market_report"]))
    if final_state.get("sentiment_report"):
        _write_section(save_path / "1_analysts", "sentiment.md", final_state["sentiment_report"])
        analyst_parts.append(("Sentiment Analyst", final_state["sentiment_report"]))
    if final_state.get("news_report"):
        _write_section(save_path / "1_analysts", "news.md", final_state["news_report"])
        analyst_parts.append(("News Analyst", final_state["news_report"]))
    if final_state.get("fundamentals_report"):
        _write_section(save_path / "1_analysts", "fundamentals.md", final_state["fundamentals_report"])
        analyst_parts.append(("Fundamentals Analyst", final_state["fundamentals_report"]))
    if analyst_parts:
        content = "\n\n".join(f"### {name}\n{text}" for name, text in analyst_parts)
        sections.append(f"## I. Analyst Team Reports\n\n{content}")

    # 2. Research
    if final_state.get("investment_debate_state"):
        debate = final_state["investment_debate_state"]
        research_parts: list[tuple[str, str]] = []
        if debate.get("bull_history"):
            _write_section(save_path / "2_research", "bull.md", debate["bull_history"])
            research_parts.append(("Bull Researcher", debate["bull_history"]))
        if debate.get("bear_history"):
            _write_section(save_path / "2_research", "bear.md", debate["bear_history"])
            research_parts.append(("Bear Researcher", debate["bear_history"]))
        if debate.get("judge_decision"):
            _write_section(save_path / "2_research", "manager.md", debate["judge_decision"])
            research_parts.append(("Research Manager", debate["judge_decision"]))
        if research_parts:
            content = "\n\n".join(f"### {name}\n{text}" for name, text in research_parts)
            sections.append(f"## II. Research Team Decision\n\n{content}")

    # 3. Trading
    if final_state.get("trader_investment_plan"):
        _write_section(save_path / "3_trading", "trader.md", final_state["trader_investment_plan"])
        sections.append(
            f"## III. Trading Team Plan\n\n### Trader\n{final_state['trader_investment_plan']}"
        )

    # 4. Risk Management
    if final_state.get("risk_debate_state"):
        risk = final_state["risk_debate_state"]
        risk_parts: list[tuple[str, str]] = []
        if risk.get("aggressive_history"):
            _write_section(save_path / "4_risk", "aggressive.md", risk["aggressive_history"])
            risk_parts.append(("Aggressive Analyst", risk["aggressive_history"]))
        if risk.get("conservative_history"):
            _write_section(save_path / "4_risk", "conservative.md", risk["conservative_history"])
            risk_parts.append(("Conservative Analyst", risk["conservative_history"]))
        if risk.get("neutral_history"):
            _write_section(save_path / "4_risk", "neutral.md", risk["neutral_history"])
            risk_parts.append(("Neutral Analyst", risk["neutral_history"]))
        if risk_parts:
            content = "\n\n".join(f"### {name}\n{text}" for name, text in risk_parts)
            sections.append(f"## IV. Risk Management Team Decision\n\n{content}")

        # 5. Portfolio Manager — last section, also written standalone for the
        # scheduled runner to pick up directly.
        if risk.get("judge_decision"):
            _write_section(save_path / "5_portfolio", "decision.md", risk["judge_decision"])
            sections.append(
                f"## V. Portfolio Manager Decision\n\n### Portfolio Manager\n{risk['judge_decision']}"
            )

    header = (
        f"# Trading Analysis Report: {ticker}\n\n"
        f"Generated: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    complete = save_path / "complete_report.md"
    complete.write_text(header + "\n\n".join(sections), encoding="utf-8")
    return complete


def _write_section(directory: Path, name: str, text: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Decision summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DecisionSummary:
    """Structured view of a Portfolio Manager ``decision.md``.

    The Portfolio Manager emits a small set of ``**Field**: value`` lines at
    the top of the document (Rating, Executive Summary, Investment Thesis,
    Price Target, Time Horizon). This dataclass captures them so the
    scheduled runner can build a short Telegram message without re-parsing
    the whole markdown every time.
    """

    rating: str | None = None
    executive_summary: str | None = None
    investment_thesis: str | None = None
    price_target: float | None = None
    time_horizon: str | None = None


_FIELD_PATTERNS: dict[str, re.Pattern[str]] = {
    "rating": re.compile(r"\*\*Rating\*\*\s*[:\-]\s*(.+?)(?=\n\*\*|\Z)", re.DOTALL),
    "executive_summary": re.compile(
        r"\*\*Executive Summary\*\*\s*[:\-]\s*(.+?)(?=\n\*\*[A-Za-z]|\Z)", re.DOTALL
    ),
    "investment_thesis": re.compile(
        r"\*\*Investment Thesis\*\*\s*[:\-]\s*(.+?)(?=\n\*\*[A-Za-z]|\Z)", re.DOTALL
    ),
    "price_target": re.compile(r"\*\*Price Target\*\*\s*[:\-]\s*([\d.,]+)"),
    "time_horizon": re.compile(r"\*\*Time Horizon\*\*\s*[:\-]\s*(.+?)(?=\n\*\*|\Z)", re.DOTALL),
}


def extract_decision_summary(decision_md: str) -> DecisionSummary:
    """Parse the Portfolio Manager's ``decision.md`` into structured fields.

    The Portfolio Manager prompt asks for the canonical fields in a fixed
    order; we tolerate a small amount of slop (extra whitespace, extra
    fields) without raising. Unknown fields land in ``extras`` so they
    still surface in the parsed payload.
    """
    if not decision_md:
        return DecisionSummary()

    def _clean(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    rating = _clean(_FIELD_PATTERNS["rating"].search(decision_md).group(1)) \
        if _FIELD_PATTERNS["rating"].search(decision_md) else None
    exec_summary = _clean(_FIELD_PATTERNS["executive_summary"].search(decision_md).group(1)) \
        if _FIELD_PATTERNS["executive_summary"].search(decision_md) else None
    thesis = _clean(_FIELD_PATTERNS["investment_thesis"].search(decision_md).group(1)) \
        if _FIELD_PATTERNS["investment_thesis"].search(decision_md) else None
    time_horizon = _clean(_FIELD_PATTERNS["time_horizon"].search(decision_md).group(1)) \
        if _FIELD_PATTERNS["time_horizon"].search(decision_md) else None

    price_target: float | None = None
    if match := _FIELD_PATTERNS["price_target"].search(decision_md):
        try:
            price_target = float(match.group(1).replace(",", "").replace(".", ".", 1))
        except ValueError:
            price_target = None

    return DecisionSummary(
        rating=rating,
        executive_summary=exec_summary,
        investment_thesis=thesis,
        price_target=price_target,
        time_horizon=time_horizon,
    )


# ---------------------------------------------------------------------------
# Markdown -> PDF
# ---------------------------------------------------------------------------


def markdown_to_pdf(markdown_path: Path, pdf_path: Path | None = None) -> Path | None:
    """Render a markdown file to PDF.

    Uses ``fpdf2`` + ``markdown-it-py`` (both pulled in by the ``scheduled``
    extra in ``pyproject.toml``). Returns the resolved PDF path on success,
    or ``None`` if the conversion failed — the caller is expected to fall
    back to the raw ``.md`` file in that case.

    We rely on the core ``Helvetica`` font (latin-1). That covers the
    Italian diacritics that show up in a Portfolio Manager ``decision.md``
    (à è é ì ò ù). Any character outside latin-1 (€, em-dashes from a
    copy-pasted source, emoji) is replaced with ``?`` rather than crashing
    the conversion — silent truncation is preferable to a scheduled run
    failing the whole pipeline.
    """
    markdown_path = Path(markdown_path)
    if not markdown_path.exists():
        raise FileNotFoundError(markdown_path)

    target = Path(pdf_path) if pdf_path else markdown_path.with_suffix(".pdf")

    try:
        from fpdf import FPDF  # type: ignore[import-not-found]
        from markdown_it import MarkdownIt  # type: ignore[import-not-found]
    except ImportError as exc:
        logger.warning("PDF conversion skipped (missing dep): %s", exc)
        return None

    text = markdown_path.read_text(encoding="utf-8")
    tokens = MarkdownIt("commonmark").parse(text)

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_margins(15, 15, 15)
    pdf.set_font("Helvetica", size=11)

    in_list = False

    for token in tokens:
        if token.type == "heading_open":
            level = int(token.tag[1])
            pdf.ln(2 if in_list else 4)
            in_list = False
            pdf.set_font("Helvetica", style="B", size=14 - level)
            continue
        if token.type == "heading_close":
            pdf.ln(2)
            continue
        if token.type == "paragraph_open":
            pdf.set_font("Helvetica", style="", size=11)
            in_list = False
            continue
        if token.type == "paragraph_close":
            pdf.ln(4)
            continue
        if token.type == "bullet_list_open":
            in_list = True
            continue
        if token.type == "bullet_list_close":
            in_list = False
            pdf.ln(2)
            continue
        if token.type == "list_item_open":
            pdf.set_x(pdf.l_margin + 5)
            # Middle dot (U+00B7) — latin-1 native, so it encodes cleanly under
            # the built-in Helvetica font. The previous bullet (U+2022) raised
            # FPDFUnicodeEncodingException on any decision.md that contained a
            # list.
            pdf.cell(5, 6, "\u00b7")
            continue
        if token.type == "list_item_close":
            pdf.ln(6)
            continue
        if token.type == "inline":
            available_w = pdf.w - pdf.l_margin - pdf.r_margin
            indent = pdf.l_margin + (10 if in_list else 0)
            pdf.set_x(indent)
            _write_inline(pdf, token.content, available_w - (10 if in_list else 0))
            if not in_list:
                pdf.ln(4)
            continue

    try:
        pdf.output(str(target))
    except Exception as exc:  # latin-1 fallback, or unknown fpdf2 internal
        logger.warning("PDF generation failed for %s: %s", markdown_path, exc)
        return None
    return target


def _to_latin1(text: str) -> str:
    """Coerce text to latin-1 so the built-in Helvetica font accepts it.

    fpdf2 raises on out-of-range code points. Decision.md content is
    overwhelmingly ASCII + Italian diacritics, all of which are latin-1;
    anything else (``€``, emoji, dashes from a copy-paste) becomes ``?``
    so the scheduled run doesn't crash on a stray glyph.
    """
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _write_inline(pdf: Any, content: str, width: float) -> None:
    """Render an inline token's text with bold/italic honoured.

    We re-parse ``content`` for ``**...**`` and ``*...*`` markers and emit
    mixed-style ``multi_cell`` segments. Output is conservative — unsupported
    markers are flattened to plain text.
    """
    style = ""
    cursor = 0
    for match in re.finditer(r"(\*\*([^*]+)\*\*|\*([^*]+)\*|([^*]+))", content):
        text: str | None = None
        if match.group(2) is not None:
            text = match.group(2)
            new_style = "B"
        elif match.group(3) is not None:
            text = match.group(3)
            new_style = "I"
        elif match.group(4) is not None:
            text = match.group(4)
            new_style = ""
        if text is None:
            continue
        if new_style != style:
            pdf.set_font("Helvetica", style=new_style, size=11)
            style = new_style
        pdf.multi_cell(width, 6, _to_latin1(text))
        cursor = match.end()
    if cursor < len(content) and not content[cursor:].strip():
        return
    # Trailing unprocessed tail (rare)
    tail = content[cursor:]
    if tail.strip():
        pdf.multi_cell(width, 6, _to_latin1(tail))
