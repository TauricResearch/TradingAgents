from __future__ import annotations

import unicodedata
import re
import textwrap
from pathlib import Path
from typing import Any


PAGE_W = 612
PAGE_H = 792
MARGIN_X = 46
TOP_Y = 744
BOTTOM_Y = 52

NAVY = (18, 31, 51)
INK = (35, 43, 55)
MUTED = (99, 111, 128)
LIGHT = (244, 247, 251)
BORDER = (214, 221, 230)
GOLD = (190, 146, 64)
GREEN = (28, 132, 92)
RED = (188, 66, 66)
AMBER = (186, 126, 35)


def write_text_pdf(markdown_text: str, output_path: Path, *, title: str = "TradingAgents Report") -> Path:
    """Backward-compatible wrapper for the richer investment memo renderer."""
    return write_investment_pdf(markdown_text, output_path, title=title)


def write_investment_pdf(
    markdown_text: str,
    output_path: Path,
    *,
    title: str = "TradingAgents Report",
    signal: dict[str, Any] | None = None,
    price_history: list[dict[str, Any]] | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    clean_markdown = _clean_text(markdown_text)
    ticker = _infer_ticker(title, clean_markdown, signal)
    generated = _infer_generated(clean_markdown)
    doc = _PdfDoc()

    _draw_cover(doc, title=title, ticker=ticker, generated=generated, signal=signal)
    _draw_dashboard(doc, ticker=ticker, signal=signal, markdown=clean_markdown)
    if price_history:
        _draw_price_chart(doc, ticker=ticker, signal=signal, price_history=price_history)
        _draw_technical_snapshot(doc, ticker=ticker, signal=signal, price_history=price_history)
    _draw_body(doc, clean_markdown, title=title)

    doc.write(output_path)
    return output_path


def _draw_cover(
    doc: "_PdfDoc",
    *,
    title: str,
    ticker: str,
    generated: str,
    signal: dict[str, Any] | None,
) -> None:
    page = doc.new_page()
    page.rect(0, 0, PAGE_W, PAGE_H, NAVY, fill=True)
    page.rect(0, 0, PAGE_W, 158, (12, 20, 34), fill=True)
    page.line(MARGIN_X, 598, PAGE_W - MARGIN_X, 598, GOLD, 1.4)

    page.text(MARGIN_X, 690, "TRADINGAGENTS", size=10, color=GOLD, font="Helvetica-Bold", char_space=1.5)
    page.text(MARGIN_X, 648, "Investment Memo", size=32, color=(255, 255, 255), font="Helvetica-Bold")
    page.text(MARGIN_X, 616, ticker, size=20, color=(225, 231, 239), font="Helvetica-Bold")
    page.text(MARGIN_X, 575, _safe_line(title), size=11, color=(190, 200, 214))

    action = _display_action(signal)
    rating = str((signal or {}).get("rating") or "N/A")
    badge_color = _action_color(action)
    page.round_rect(MARGIN_X, 468, 170, 54, badge_color, fill=True)
    page.text(MARGIN_X + 18, 499, "OPERATIVE SIGNAL", size=8, color=(255, 255, 255), font="Helvetica-Bold")
    page.text(MARGIN_X + 18, 477, action, size=18, color=(255, 255, 255), font="Helvetica-Bold")

    page.text(MARGIN_X + 205, 502, "Portfolio rating", size=9, color=(190, 200, 214))
    page.text(MARGIN_X + 205, 476, rating, size=20, color=(255, 255, 255), font="Helvetica-Bold")
    page.text(MARGIN_X, 378, "Prepared for personal investment review", size=13, color=(225, 231, 239))
    page.text(MARGIN_X, 352, f"Generated: {generated}", size=10, color=(166, 176, 191))

    disclaimer = str((signal or {}).get("disclaimer") or "Informacion generada para apoyo operativo; no es recomendacion financiera.")
    for idx, line in enumerate(textwrap.wrap(disclaimer, 92)):
        page.text(MARGIN_X, 92 - idx * 13, line, size=8, color=(151, 161, 177))


def _draw_dashboard(doc: "_PdfDoc", *, ticker: str, signal: dict[str, Any] | None, markdown: str) -> None:
    page = doc.new_page()
    _draw_header(page, "Executive Dashboard", ticker)

    if signal:
        action = _display_action(signal)
        entry_label = "Entry" if action == "BUY" else "Reference"
        metrics = [
            ("Action", action),
            ("Rating", signal.get("rating")),
            ("Confidence", signal.get("confidence")),
            ("Risk / Reward", signal.get("risk_reward")),
            (entry_label, _fmt_price(signal.get("entry_price"))),
            ("Stop Loss", _fmt_price(signal.get("stop_loss"))),
            ("Take Profit", _fmt_price(signal.get("take_profit"))),
            ("Bias", signal.get("position_bias")),
        ]
    else:
        metrics = [
            ("Action", "Review"),
            ("Rating", _extract_label(markdown, "Rating") or "N/A"),
            ("Confidence", "N/A"),
            ("Risk / Reward", "N/A"),
        ]

    x0, y0 = MARGIN_X, 648
    card_w, card_h = 122, 70
    for idx, (label, value) in enumerate(metrics):
        col = idx % 4
        row = idx // 4
        x = x0 + col * (card_w + 12)
        y = y0 - row * (card_h + 14)
        color = _metric_color(label, str(value))
        page.round_rect(x, y, card_w, card_h, LIGHT, stroke=BORDER, fill=True)
        page.rect(x, y + card_h - 5, card_w, 5, color, fill=True)
        page.text(x + 10, y + 46, label.upper(), size=7, color=MUTED, font="Helvetica-Bold")
        page.text(x + 10, y + 22, _safe_line(str(value or "N/A"), 18), size=14, color=INK, font="Helvetica-Bold")

    y = 452
    page.text(MARGIN_X, y, "Investment Read-Through", size=15, color=NAVY, font="Helvetica-Bold")
    page.line(MARGIN_X, y - 8, PAGE_W - MARGIN_X, y - 8, BORDER, 0.8)
    y -= 32

    bullets = []
    if signal:
        bullets.extend(str(item) for item in signal.get("reasons", [])[:4])
    bullets.extend(_extract_conclusion_bullets(markdown, limit=4))
    if not bullets:
        bullets = ["Review the detailed analyst sections for the full rationale."]

    for bullet in bullets[:7]:
        y = _draw_bullet(page, MARGIN_X, y, bullet)

    page.text(MARGIN_X, 168, "Operating Protocol", size=15, color=NAVY, font="Helvetica-Bold")
    page.line(MARGIN_X, 160, PAGE_W - MARGIN_X, 160, BORDER, 0.8)
    guide = [
        "Primary decision is taken from Action, Bias and the forward risk bands above.",
        "Do not chase price away from the reference level; reassess on the next close.",
        "A rating downgrade without an existing position should be read as Avoid, not a forced short.",
    ]
    y = 136
    for item in guide:
        y = _draw_bullet(page, MARGIN_X, y, item)


def _draw_price_chart(
    doc: "_PdfDoc",
    *,
    ticker: str,
    signal: dict[str, Any] | None,
    price_history: list[dict[str, Any]],
) -> None:
    points = _normalise_price_history(price_history)
    if len(points) < 2:
        return

    page = doc.new_page()
    _draw_header(page, "Price & Risk Map", ticker)
    page.text(MARGIN_X, 664, "Daily close with forward risk levels", size=15, color=NAVY, font="Helvetica-Bold")
    page.text(
        MARGIN_X,
        646,
        "Historical close prices are plotted to the left; stop loss and take profit extend into the forward watch window.",
        size=8.5,
        color=MUTED,
    )

    chart_x = MARGIN_X
    chart_y = 230
    chart_w = PAGE_W - 2 * MARGIN_X
    chart_h = 370
    future_slots = 10
    total_slots = (len(points) - 1) + future_slots

    level_values = _signal_levels(signal)
    values = [p["close"] for p in points] + [v for v in level_values.values() if v is not None]
    min_v, max_v = min(values), max(values)
    pad = max((max_v - min_v) * 0.10, max_v * 0.005, 1)
    min_v -= pad
    max_v += pad

    page.rect(chart_x, chart_y, chart_w, chart_h, (255, 255, 255), stroke=BORDER, fill=True)
    page.rect(chart_x + chart_w * (len(points) - 1) / total_slots, chart_y, chart_w * future_slots / total_slots, chart_h, (248, 241, 226), fill=True)

    for idx in range(5):
        y = chart_y + idx * chart_h / 4
        page.line(chart_x, y, chart_x + chart_w, y, (229, 234, 241), 0.5)
        value = min_v + idx * (max_v - min_v) / 4
        page.text(chart_x + chart_w + 6, y - 3, _fmt_price(value), size=7, color=MUTED)

    coords = []
    for idx, point in enumerate(points):
        x = chart_x + idx * chart_w / total_slots
        y = chart_y + (point["close"] - min_v) / (max_v - min_v) * chart_h
        coords.append((x, y))
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        page.line(x1, y1, x2, y2, NAVY, 1.6)
    _draw_sma_overlay(page, points, chart_x, chart_y, chart_w, chart_h, total_slots, min_v, max_v, window=20, color=GOLD, label="SMA 20")
    _draw_sma_overlay(page, points, chart_x, chart_y, chart_w, chart_h, total_slots, min_v, max_v, window=50, color=(91, 117, 158), label="SMA 50")
    for x, y in coords[-4:]:
        page.circle(x, y, 2.5, NAVY, fill=True)

    last_x, last_y = coords[-1]
    page.line(last_x, last_y, chart_x + chart_w, last_y, (149, 160, 176), 0.7)
    page.text(last_x + 8, last_y + 8, f"Last close {_fmt_price(points[-1]['close'])}", size=8, color=INK, font="Helvetica-Bold")

    reference_label = "Entry" if _display_action(signal) == "BUY" else "Reference"
    level_specs = [
        (reference_label, level_values.get("entry_price"), GOLD),
        ("Stop Loss", level_values.get("stop_loss"), RED),
        ("Take Profit", level_values.get("take_profit"), GREEN),
    ]
    future_x0 = chart_x + chart_w * (len(points) - 1) / total_slots
    for label, value, color in level_specs:
        if value is None:
            continue
        y = chart_y + (value - min_v) / (max_v - min_v) * chart_h
        page.line(future_x0, y, chart_x + chart_w, y, color, 1.4)
        page.text(future_x0 + 8, y + 5, f"{label}: {_fmt_price(value)}", size=8.2, color=color, font="Helvetica-Bold")

    first_label = points[0]["date"]
    last_label = points[-1]["date"]
    page.text(chart_x, chart_y - 22, first_label, size=7.5, color=MUTED)
    page.text(chart_x + chart_w * 0.62, chart_y - 22, last_label, size=7.5, color=MUTED)
    page.text(chart_x + chart_w - 72, chart_y - 22, "Forward watch", size=7.5, color=AMBER, font="Helvetica-Bold")

    y = 170
    page.text(MARGIN_X, y, "How to read it", size=13, color=NAVY, font="Helvetica-Bold")
    y -= 24
    action = _display_action(signal)
    notes = [
        f"Signal context: {action}. Risk levels are not historical prices; they are forward reference bands.",
        "A close through stop loss invalidates the current setup for this run.",
        "A close near take profit marks the first area to reassess or harvest gains.",
    ]
    for note in notes:
        y = _draw_bullet(page, MARGIN_X, y, note)


def _draw_technical_snapshot(
    doc: "_PdfDoc",
    *,
    ticker: str,
    signal: dict[str, Any] | None,
    price_history: list[dict[str, Any]],
) -> None:
    points = _normalise_price_history(price_history)
    stats = _technical_stats(points, signal)
    if not stats:
        return

    page = doc.new_page()
    _draw_header(page, "Technical Snapshot", ticker)
    page.text(MARGIN_X, 664, "What changed in the tape", size=15, color=NAVY, font="Helvetica-Bold")
    page.text(MARGIN_X, 646, "Compact diagnostics from recent daily closes; this is the investment committee one-page view.", size=8.5, color=MUTED)

    metrics = [
        ("Last Close", _fmt_price(stats["last_close"]), "neutral"),
        ("20D Return", _fmt_pct(stats["return_20d"]), "return"),
        ("60D Return", _fmt_pct(stats["return_60d"]), "return"),
        ("Drawdown", _fmt_pct(stats["drawdown"]), "risk"),
        ("SMA 20", _fmt_price(stats["sma20"]), "neutral"),
        ("SMA 50", _fmt_price(stats["sma50"]), "neutral"),
        ("Trend", stats["trend"], "trend"),
        ("RSI 14", _fmt_number(stats["rsi14"]), "momentum"),
        ("Stop Dist.", _fmt_pct(stats["stop_distance"]), "risk"),
        ("Target Dist.", _fmt_pct(stats["target_distance"]), "return"),
        ("Action", _display_action(signal), "action"),
        ("Bias", str((signal or {}).get("position_bias") or "N/A"), "neutral"),
    ]

    x0, y0 = MARGIN_X, 584
    card_w, card_h = 122, 62
    for idx, (label, value, kind) in enumerate(metrics):
        col = idx % 4
        row = idx // 4
        x = x0 + col * (card_w + 12)
        y = y0 - row * (card_h + 14)
        color = _snapshot_color(kind, value)
        page.round_rect(x, y, card_w, card_h, LIGHT, stroke=BORDER, fill=True)
        page.rect(x, y + card_h - 4, card_w, 4, color, fill=True)
        page.text(x + 10, y + 39, label.upper(), size=7, color=MUTED, font="Helvetica-Bold")
        page.text(x + 10, y + 17, _safe_line(str(value), 18), size=12.5, color=INK, font="Helvetica-Bold")

    page.text(MARGIN_X, 316, "Decision Checklist", size=15, color=NAVY, font="Helvetica-Bold")
    page.line(MARGIN_X, 307, PAGE_W - MARGIN_X, 307, BORDER, 0.8)
    y = 282
    for item in _decision_checklist(stats, signal):
        y = _draw_bullet(page, MARGIN_X, y, item)

    page.text(MARGIN_X, 126, "Improvement note", size=13, color=NAVY, font="Helvetica-Bold")
    y = 104
    y = _draw_bullet(page, MARGIN_X, y, "Future versions should add benchmark-relative performance against SPY or IPSA once the data source is stable.")
    _draw_bullet(page, MARGIN_X, y, "For position sizing, connect portfolio holdings so Avoid / Reduce / Exit can be separated cleanly.")


def _draw_body(doc: "_PdfDoc", markdown_text: str, *, title: str) -> None:
    subtitle = _safe_line(title.replace("Trading Analysis Report:", "").strip() or title, 42)
    page = doc.new_page()
    _draw_header(page, "Detailed Analysis", subtitle)
    y = 662

    for block in _iter_blocks(markdown_text):
        kind = block["kind"]
        text = block["text"]
        if kind == "h1":
            page, y = _ensure_space(doc, page, y, 46, "Detailed Analysis", subtitle)
            _draw_marked_text(page, MARGIN_X, y, _safe_line(text, 72), size=17, color=NAVY, font="Helvetica-Bold")
            page.line(MARGIN_X, y - 9, PAGE_W - MARGIN_X, y - 9, GOLD, 1.0)
            y -= 28
        elif kind == "h2":
            page, y = _ensure_space(doc, page, y, 38, "Detailed Analysis", subtitle)
            _draw_marked_text(page, MARGIN_X, y, _safe_line(text, 80), size=13, color=NAVY, font="Helvetica-Bold")
            y -= 21
        elif kind == "h3":
            page, y = _ensure_space(doc, page, y, 30, "Detailed Analysis", subtitle)
            _draw_marked_text(page, MARGIN_X, y, _safe_line(text, 88), size=11, color=INK, font="Helvetica-Bold")
            y -= 17
        elif kind == "table":
            page, y = _draw_table_block(doc, page, y, text, subtitle)
        elif kind == "bullet":
            page, y = _ensure_space(doc, page, y, 30, "Detailed Analysis", subtitle)
            y = _draw_bullet(page, MARGIN_X, y, text)
        else:
            for line in textwrap.wrap(text, width=96):
                page, y = _ensure_space(doc, page, y, 16, "Detailed Analysis", subtitle)
                _draw_marked_text(page, MARGIN_X, y, line, size=9.2, color=INK)
                y -= 13
            y -= 4


def _draw_table_block(doc: "_PdfDoc", page: "_PdfPage", y: float, rows: list[list[str]], title: str):
    if not rows:
        return page, y
    page, y = _ensure_space(doc, page, y, 28 + min(len(rows), 8) * 19, "Detailed Analysis", title)
    max_cols = min(max(len(row) for row in rows), 4)
    table_w = PAGE_W - 2 * MARGIN_X
    col_w = table_w / max_cols
    header = rows[0][:max_cols]
    page.rect(MARGIN_X, y - 16, table_w, 20, NAVY, fill=True)
    for idx, cell in enumerate(header):
        _draw_marked_text(page, MARGIN_X + idx * col_w + 6, y - 10, _safe_line(cell, int(col_w / 5.2)), size=7.2, color=(255, 255, 255), font="Helvetica-Bold")
    y -= 36
    for ridx, row in enumerate(rows[1:9]):
        bg = (250, 252, 255) if ridx % 2 == 0 else (236, 241, 247)
        page.rect(MARGIN_X, y - 7, table_w, 18, bg, fill=True)
        for idx, cell in enumerate(row[:max_cols]):
            _draw_marked_text(page, MARGIN_X + idx * col_w + 6, y - 1, _safe_line(cell, int(col_w / 5.2)), size=7.0, color=INK)
        y -= 18
    if len(rows) > 9:
        page.text(MARGIN_X, y, f"+ {len(rows) - 9} additional rows in source Markdown.", size=7.5, color=MUTED)
        y -= 14
    y -= 8
    return page, y


def _draw_header(page: "_PdfPage", section: str, subtitle: str) -> None:
    page.rect(0, PAGE_H - 74, PAGE_W, 74, NAVY, fill=True)
    page.text(MARGIN_X, PAGE_H - 34, section, size=16, color=(255, 255, 255), font="Helvetica-Bold")
    page.text(MARGIN_X, PAGE_H - 54, subtitle, size=8.5, color=(190, 200, 214))
    page.line(MARGIN_X, PAGE_H - 76, PAGE_W - MARGIN_X, PAGE_H - 76, GOLD, 1.2)


def _draw_bullet(page: "_PdfPage", x: float, y: float, text: str) -> float:
    marker, clean = _extract_marker(_strip_markdown(text))
    wrapped = textwrap.wrap(clean, width=92)
    _draw_marker_icon(page, x + 4, y - 3, marker or "bullet")
    for idx, line in enumerate(wrapped):
        page.text(x + 16, y - idx * 13, line, size=9.2, color=INK)
    return y - max(1, len(wrapped)) * 13 - 8


def _draw_marked_text(page: "_PdfPage", x: float, y: float, text: str, *, size: float, color=INK, font: str = "Helvetica") -> None:
    marker, clean = _extract_marker(_strip_markdown(text))
    if marker:
        _draw_marker_icon(page, x + 3, y + size * 0.25, marker)
        page.text(x + 12, y, clean, size=size, color=color, font=font)
    else:
        page.text(x, y, clean, size=size, color=color, font=font)


def _draw_marker_icon(page: "_PdfPage", x: float, y: float, marker: str) -> None:
    if marker in {"GREEN", "PLUS"}:
        page.circle(x, y, 3.0, GREEN, fill=True)
    elif marker == "RED":
        page.circle(x, y, 3.0, RED, fill=True)
    elif marker == "WARN":
        page.circle(x, y, 3.0, AMBER, fill=True)
        page.text(x - 1.2, y - 2.2, "!", size=5.2, color=(255, 255, 255), font="Helvetica-Bold")
    elif marker == "INFO":
        page.circle(x, y, 3.0, (58, 111, 181), fill=True)
    else:
        page.circle(x, y, 2.4, GOLD, fill=True)


def _ensure_space(doc: "_PdfDoc", page: "_PdfPage", y: float, needed: float, section: str, subtitle: str):
    if y - needed >= BOTTOM_Y:
        return page, y
    page = doc.new_page()
    _draw_header(page, section, _safe_line(subtitle, 42))
    return page, 662


def _iter_blocks(markdown_text: str):
    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    paragraph: list[str] = []
    table: list[list[str]] = []

    def flush_paragraph():
        nonlocal paragraph
        if paragraph:
            text = " ".join(paragraph).strip()
            paragraph = []
            if text:
                return {"kind": "paragraph", "text": _strip_markdown(text)}
        return None

    def flush_table():
        nonlocal table
        if table:
            rows = table
            table = []
            if len(rows) >= 2:
                return {"kind": "table", "text": rows}
        return None

    for raw in lines:
        line = raw.strip()
        if _is_boilerplate_line(line):
            item = flush_paragraph()
            if item:
                yield item
            continue
        if not line:
            item = flush_paragraph()
            if item:
                yield item
            item = flush_table()
            if item:
                yield item
            continue
        if line.startswith("|") and line.endswith("|"):
            item = flush_paragraph()
            if item:
                yield item
            if re.fullmatch(r"\|[\s:\-|]+\|", line):
                continue
            table.append([_strip_markdown(c.strip()) for c in line.strip("|").split("|")])
            continue
        item = flush_table()
        if item:
            yield item
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            item = flush_paragraph()
            if item:
                yield item
            depth = len(heading.group(1))
            kind = "h1" if depth == 1 else "h2" if depth == 2 else "h3"
            yield {"kind": kind, "text": _strip_markdown(heading.group(2))}
        elif line.startswith(("- ", "* ")):
            item = flush_paragraph()
            if item:
                yield item
            yield {"kind": "bullet", "text": line[2:]}
        elif re.match(r"^\d+\.\s+", line):
            item = flush_paragraph()
            if item:
                yield item
            yield {"kind": "bullet", "text": re.sub(r"^\d+\.\s+", "", line)}
        elif line in {"---", "***"}:
            item = flush_paragraph()
            if item:
                yield item
        else:
            paragraph.append(line)
    for item in (flush_paragraph(), flush_table()):
        if item:
            yield item


def _extract_conclusion_bullets(markdown: str, *, limit: int) -> list[str]:
    hits = []
    capture = False
    for line in markdown.splitlines():
        clean = _strip_markdown(line.strip())
        if not clean:
            continue
        low = clean.lower()
        if "conclusion" in low or "resumen ejecutivo" in low or "executive summary" in low:
            capture = True
            continue
        if capture and clean.startswith("#"):
            break
        if capture and len(clean) > 45:
            hits.append(clean)
        if len(hits) >= limit:
            break
    return hits


def _normalise_price_history(price_history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points = []
    for item in price_history:
        try:
            close = float(item["close"])
        except (KeyError, TypeError, ValueError):
            continue
        date = str(item.get("date") or "")
        points.append({"date": date[:10], "close": close})
    return points


def _signal_levels(signal: dict[str, Any] | None) -> dict[str, float | None]:
    if not signal:
        return {"entry_price": None, "stop_loss": None, "take_profit": None}

    def as_float(key: str) -> float | None:
        value = signal.get(key)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    return {
        "entry_price": as_float("entry_price"),
        "stop_loss": as_float("stop_loss"),
        "take_profit": as_float("take_profit"),
    }


def _display_action(signal: dict[str, Any] | None) -> str:
    if not signal:
        return "REVIEW"
    action = str(signal.get("action") or "REVIEW").upper()
    bias = str(signal.get("position_bias") or "").lower()
    if action == "SELL" and bias == "avoid":
        return "AVOID"
    return action


def _draw_sma_overlay(
    page: "_PdfPage",
    points: list[dict[str, Any]],
    chart_x: float,
    chart_y: float,
    chart_w: float,
    chart_h: float,
    total_slots: int,
    min_v: float,
    max_v: float,
    *,
    window: int,
    color,
    label: str,
) -> None:
    closes = [p["close"] for p in points]
    if len(closes) < window:
        return
    coords = []
    for idx in range(window - 1, len(closes)):
        avg = sum(closes[idx - window + 1 : idx + 1]) / window
        x = chart_x + idx * chart_w / total_slots
        y = chart_y + (avg - min_v) / (max_v - min_v) * chart_h
        coords.append((x, y))
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        page.line(x1, y1, x2, y2, color, 0.9)
    legend_x = chart_x + 12 + (0 if window == 20 else 74)
    legend_y = chart_y + chart_h - 18
    page.line(legend_x, legend_y, legend_x + 18, legend_y, color, 1.5)
    page.text(legend_x + 23, legend_y - 3, label, size=7.5, color=MUTED)


def _technical_stats(points: list[dict[str, Any]], signal: dict[str, Any] | None) -> dict[str, Any]:
    closes = [p["close"] for p in points]
    if len(closes) < 2:
        return {}
    last = closes[-1]
    levels = _signal_levels(signal)
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    trend = "Uptrend" if sma20 and sma50 and last >= sma20 >= sma50 else "Mixed"
    if sma20 and sma50 and last < sma20 < sma50:
        trend = "Downtrend"
    period_high = max(closes)
    drawdown = (last / period_high - 1) if period_high else None
    return {
        "last_close": last,
        "return_20d": _period_return(closes, 20),
        "return_60d": _period_return(closes, 60),
        "drawdown": drawdown,
        "sma20": sma20,
        "sma50": sma50,
        "trend": trend,
        "rsi14": _rsi(closes, 14),
        "stop_distance": _distance_from_last(last, levels.get("stop_loss")),
        "target_distance": _distance_from_last(last, levels.get("take_profit")),
    }


def _decision_checklist(stats: dict[str, Any], signal: dict[str, Any] | None) -> list[str]:
    action = _display_action(signal)
    items = []
    trend_marker = "[GREEN]" if stats.get("trend") == "Uptrend" else "[!]"
    items.append(f"{trend_marker} Trend state: {stats.get('trend')}. Price is compared against SMA 20 and SMA 50.")
    rsi = stats.get("rsi14")
    if rsi is not None and rsi >= 70:
        items.append(f"[!] Momentum is stretched: RSI 14 is {_fmt_number(rsi)}.")
    elif rsi is not None and rsi <= 30:
        items.append(f"[!] Momentum is oversold: RSI 14 is {_fmt_number(rsi)}.")
    elif rsi is not None:
        items.append(f"[GREEN] Momentum is not extreme: RSI 14 is {_fmt_number(rsi)}.")
    if action == "AVOID":
        items.append("[!] Signal is Avoid, not an instruction to short unless a shorting workflow is explicitly enabled.")
    elif action == "SELL":
        items.append("[RED] Sell signal: stop and target should be read as short/reduction risk bands.")
    elif action == "BUY":
        items.append("[GREEN] Buy signal: stop and target define the forward risk envelope.")
    stop = stats.get("stop_distance")
    target = stats.get("target_distance")
    if stop is not None and target is not None:
        items.append(f"[INFO] Distance from last close: stop {_fmt_pct(stop)}, target {_fmt_pct(target)}.")
    return items


def _sma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def _period_return(values: list[float], days: int) -> float | None:
    if len(values) <= days or values[-days - 1] == 0:
        return None
    return values[-1] / values[-days - 1] - 1


def _distance_from_last(last: float, level: float | None) -> float | None:
    if level is None or last == 0:
        return None
    return level / last - 1


def _rsi(values: list[float], window: int) -> float | None:
    if len(values) <= window:
        return None
    deltas = [values[i] - values[i - 1] for i in range(1, len(values))]
    recent = deltas[-window:]
    gains = [max(delta, 0) for delta in recent]
    losses = [abs(min(delta, 0)) for delta in recent]
    avg_gain = sum(gains) / window
    avg_loss = sum(losses) / window
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _extract_marker(text: str) -> tuple[str | None, str]:
    clean = text.strip()
    marker_map = {
        "[GREEN]": "GREEN",
        "[RED]": "RED",
        "[!]": "WARN",
        "[+]": "PLUS",
        "[INFO]": "INFO",
    }
    for token, marker in marker_map.items():
        if clean.startswith(token):
            return marker, clean[len(token):].strip()
    for token, marker in marker_map.items():
        if token in clean:
            return marker, clean.replace(token, "").strip()
    return None, clean


def _is_boilerplate_line(line: str) -> bool:
    clean = _strip_markdown(line).strip()
    clean = clean.lstrip("#").strip()
    if not clean:
        return False
    lower = clean.lower()
    if lower.startswith("trading analysis report:"):
        return True
    if lower.startswith("generated:"):
        return True
    process_phrases = (
        "datos completos",
        "ahora procedo",
        "procedo a realizar",
        "procedo a elaborar",
        "excelente",
    )
    return any(phrase in lower for phrase in process_phrases) and len(clean) < 140


def _clean_text(text: str) -> str:
    if "Ã" in text or "Â" in text:
        try:
            text = text.encode("latin-1").decode("utf-8")
        except UnicodeError:
            pass
    text = re.sub(r"[0-9]\ufe0f?\u20e3", "", text)
    replacements = {
        "→": "->",
        "—": "-",
        "–": "-",
        "−": "-",
        "“": '"',
        "”": '"',
        "’": "'",
        "‘": "'",
        "•": "-",
        "✅": "[+]",
        "⚠️": "[!]",
        "⚠": "[!]",
        "🔴": "[RED]",
        "🟢": "[GREEN]",
        "🟡": "[!]",
        "🔵": "[INFO]",
        "❌": "[RED]",
        "📈": "",
        "📊": "",
        "📉": "",
        "📐": "",
        "📋": "",
        "🌍": "",
        "🌐": "",
        "🔍": "",
        "⚡": "",
        "🧩": "",
        "🧠": "",
        "🔄": "",
        "📏": "",
        "🎯": "",
        "\u200b": "",
        "\ufeff": "",
        "\ufe0f": "",
        "\u20e3": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = _strip_unsupported_pdf_chars(text)
    return re.sub(r"[ \t]{2,}", " ", text)


def _strip_markdown(text: str) -> str:
    text = _clean_text(text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.strip()


def _infer_ticker(title: str, markdown: str, signal: dict[str, Any] | None) -> str:
    if signal and signal.get("ticker"):
        return str(signal["ticker"])
    match = re.search(r"Report:\s*([A-Za-z0-9._\-^]+)", title)
    if match:
        return match.group(1)
    match = re.search(r"Report:\s*([A-Za-z0-9._\-^]+)", markdown)
    return match.group(1) if match else "Portfolio Review"


def _infer_generated(markdown: str) -> str:
    match = re.search(r"Generated:\s*([0-9:\-\s]+)", markdown)
    return match.group(1).strip() if match else "N/A"


def _extract_label(markdown: str, label: str) -> str | None:
    match = re.search(rf"{re.escape(label)}\**\s*[:\-]\s*([^\n]+)", markdown, re.IGNORECASE)
    return _strip_markdown(match.group(1)) if match else None


def _fmt_price(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value) * 100:+.1f}%"
    except (TypeError, ValueError):
        return str(value)


def _fmt_number(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return str(value)


def _safe_line(value: str, max_chars: int = 90) -> str:
    clean = _strip_markdown(value)
    return clean if len(clean) <= max_chars else clean[: max_chars - 1] + "..."


def _action_color(action: str):
    action = action.upper()
    if action == "BUY":
        return GREEN
    if action == "SELL":
        return RED
    if action == "HOLD":
        return AMBER
    return GOLD


def _metric_color(label: str, value: str):
    if label == "Action":
        return _action_color(value)
    if label in {"Stop Loss"}:
        return RED
    if label in {"Take Profit", "Risk / Reward"}:
        return GREEN
    return GOLD


def _snapshot_color(kind: str, value: str):
    if kind == "action":
        return _action_color(value)
    if kind == "risk":
        return RED if "-" in value or value.startswith("+") else AMBER
    if kind == "return":
        return RED if value.startswith("-") else GREEN
    if kind == "trend":
        return GREEN if value == "Uptrend" else AMBER
    if kind == "momentum":
        try:
            numeric = float(value)
        except ValueError:
            return GOLD
        if numeric >= 70 or numeric <= 30:
            return AMBER
        return GREEN
    return GOLD


class _PdfDoc:
    def __init__(self) -> None:
        self.pages: list[_PdfPage] = []

    def new_page(self) -> "_PdfPage":
        page = _PdfPage()
        self.pages.append(page)
        return page

    def write(self, output_path: Path) -> None:
        objects: list[bytes] = []
        page_ids: list[int] = []

        def add(body: bytes) -> int:
            objects.append(body)
            return len(objects)

        font_regular = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        font_bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")

        for page in self.pages:
            content = page.render().encode("cp1252", errors="ignore")
            content_id = add(b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream")
            page_id = add(
                (
                    "<< /Type /Page /Parent 0 0 R /MediaBox [0 0 612 792] "
                    f"/Resources << /Font << /F1 {font_regular} 0 R /F2 {font_bold} 0 R >> >> "
                    f"/Contents {content_id} 0 R >>"
                ).encode("latin-1")
            )
            page_ids.append(page_id)

        pages_id = add(
            (
                f"<< /Type /Pages /Kids [{' '.join(f'{pid} 0 R' for pid in page_ids)}] "
                f"/Count {len(page_ids)} >>"
            ).encode("latin-1")
        )
        catalog_id = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("latin-1"))
        for pid in page_ids:
            objects[pid - 1] = objects[pid - 1].replace(b"/Parent 0 0 R", f"/Parent {pages_id} 0 R".encode("latin-1"))

        pdf_parts = [b"%PDF-1.4\n"]
        offsets = [0]
        for idx, body in enumerate(objects, start=1):
            offsets.append(sum(len(part) for part in pdf_parts))
            pdf_parts.append(f"{idx} 0 obj\n".encode("latin-1") + body + b"\nendobj\n")

        xref_offset = sum(len(part) for part in pdf_parts)
        pdf_parts.append(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
        pdf_parts.append(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            pdf_parts.append(f"{offset:010d} 00000 n \n".encode("latin-1"))
        pdf_parts.append(
            (
                f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
                f"startxref\n{xref_offset}\n%%EOF\n"
            ).encode("latin-1")
        )
        output_path.write_bytes(b"".join(pdf_parts))


class _PdfPage:
    def __init__(self) -> None:
        self.ops: list[str] = []

    def render(self) -> str:
        return "\n".join(self.ops)

    def text(self, x: float, y: float, text: str, *, size: float = 10, color=INK, font: str = "Helvetica", char_space: float = 0) -> None:
        text = _clean_text(str(text))
        font_id = "F2" if "Bold" in font else "F1"
        self.ops.append("BT")
        self.ops.append(f"/{font_id} {size:.2f} Tf")
        if char_space:
            self.ops.append(f"{char_space:.2f} Tc")
        self.ops.append(f"{_rgb(color)} rg")
        self.ops.append(f"1 0 0 1 {x:.2f} {y:.2f} Tm")
        self.ops.append(f"({_pdf_escape(text)}) Tj")
        self.ops.append("ET")

    def rect(self, x: float, y: float, w: float, h: float, color, *, stroke=None, fill: bool = False) -> None:
        if fill:
            self.ops.append(f"{_rgb(color)} rg")
            self.ops.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")
        if stroke:
            self.ops.append(f"{_rgb(stroke)} RG")
            self.ops.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re S")

    def round_rect(self, x: float, y: float, w: float, h: float, color, *, stroke=None, fill: bool = False) -> None:
        # PDF path rounded corners are not worth the verbosity here; use a clean rectangle.
        self.rect(x, y, w, h, color, stroke=stroke, fill=fill)

    def line(self, x1: float, y1: float, x2: float, y2: float, color, width: float = 1) -> None:
        self.ops.append(f"{_rgb(color)} RG")
        self.ops.append(f"{width:.2f} w")
        self.ops.append(f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def circle(self, x: float, y: float, r: float, color, *, fill: bool = False) -> None:
        c = 0.5522847498 * r
        self.ops.append(f"{_rgb(color)} {'rg' if fill else 'RG'}")
        self.ops.append(
            f"{x + r:.2f} {y:.2f} m "
            f"{x + r:.2f} {y + c:.2f} {x + c:.2f} {y + r:.2f} {x:.2f} {y + r:.2f} c "
            f"{x - c:.2f} {y + r:.2f} {x - r:.2f} {y + c:.2f} {x - r:.2f} {y:.2f} c "
            f"{x - r:.2f} {y - c:.2f} {x - c:.2f} {y - r:.2f} {x:.2f} {y - r:.2f} c "
            f"{x + c:.2f} {y - r:.2f} {x + r:.2f} {y - c:.2f} {x + r:.2f} {y:.2f} c "
            f"{'f' if fill else 'S'}"
        )


def _rgb(color) -> str:
    return " ".join(f"{c / 255:.4f}" for c in color)


def _pdf_escape(value: str) -> str:
    safe = _strip_unsupported_pdf_chars(value)
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _strip_unsupported_pdf_chars(value: str) -> str:
    cleaned = []
    for char in value:
        category = unicodedata.category(char)
        if category in {"Mn", "Me", "Cf"}:
            continue
        if category == "So":
            continue
        try:
            char.encode("cp1252")
        except UnicodeEncodeError:
            continue
        cleaned.append(char)
    return "".join(cleaned)
