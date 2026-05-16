"""Extract structured recommendation data from final_trade_decision.md files.

This is the core of "Approach C: Extract-at-Write" -- called at persist time
(right after the report is written, format is fresh and known) and during
one-time migration of historical reports (can fail gracefully).

Reports are written in Russian by the AI trading agent system.  The extractor
handles both Russian *and* English keywords so it survives format drift.

Typical header patterns found in production reports
----------------------------------------------------
- ``# Вердикт Портфельного Менеджера: NFLX``
- ``# ФИНАЛЬНОЕ РЕШЕНИЕ ПОРТФЕЛЬНОГО МЕНЕДЖЕРА: CRWD``
- ``## ИТОГОВОЕ РЕШЕНИЕ ПОРТФЕЛЬНОГО УПРАВЛЯЮЩЕГО``
- ``# Решение Портфельного Управляющего: SPY``

Verdict patterns (always in bold)::

    ## Итоговый рейтинг: **HOLD**
    ## ⚖️ ВЕРДИКТ: **Hold**
    ### Рейтинг: **SELL**
    ## Рейтинг: Underweight          (no bold, still valid)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

_VALID_VERDICTS = frozenset({
    "BUY",
    "HOLD",
    "SELL",
    "UNDERWEIGHT",
    "OVERWEIGHT",
    "UNKNOWN",
})

_NOTES_MAX_LEN = 200

# ── Data transfer object ────────────────────────────────────────────────


@dataclass(frozen=True)
class ExtractedRecommendation:
    """Immutable container for structured recommendation data.

    Every field except *ticker* and *verdict* is optional -- the extractor
    returns ``None`` for anything it cannot confidently parse.
    """

    ticker: str
    verdict: str  # BUY | HOLD | SELL | UNDERWEIGHT | OVERWEIGHT | UNKNOWN
    confidence: int | None = None  # 1-10 if mentioned
    price_at_analysis: float | None = None  # current price at analysis time
    stop_loss: float | None = None  # dollar amount
    entry_trigger: float | None = None  # dollar amount
    profit_target: float | None = None  # dollar amount
    review_date: str | None = None  # when to re-evaluate
    notes: str | None = None  # key catalyst / first 200 chars of conclusion
    analysis_id: int | None = None  # FK back to analyses table


# ── Price regex ──────────────────────────────────────────────────────────
# Matches $77, $89.17, $89,17 (Russian decimal), $1,283, $2,850.50 etc.
_PRICE_RE = re.compile(r"\$\s?([\d]+(?:[.,]\d{1,3})*)")


def _parse_price_str(raw: str) -> float | None:
    """Parse a price string handling both English and Russian decimal formats.

    Rules for comma disambiguation:
    - Comma followed by exactly 2 digits at end of string: Russian decimal
      ($89,17 -> 89.17, $94,70 -> 94.70)
    - Comma followed by 3 digits: thousands separator
      ($1,283 -> 1283.0)
    - Dot followed by 1-2 digits: English decimal ($89.17 -> 89.17)
    """
    if not raw:
        return None

    # Check for Russian decimal: single comma + exactly 2 trailing digits
    russian_decimal = re.match(r"^(\d+),(\d{2})$", raw)
    if russian_decimal:
        try:
            return float(f"{russian_decimal.group(1)}.{russian_decimal.group(2)}")
        except ValueError:
            return None

    # Standard format: strip thousands commas, keep dot as decimal
    cleaned = raw.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _first_price(text: str) -> float | None:
    """Return the first dollar-denominated price found in *text*, or None."""
    m = _PRICE_RE.search(text)
    if m is None:
        return None
    return _parse_price_str(m.group(1))


def _all_prices(text: str) -> list[float]:
    """Return every dollar-denominated price found in *text*."""
    results: list[float] = []
    for m in _PRICE_RE.finditer(text):
        val = _parse_price_str(m.group(1))
        if val is not None:
            results.append(val)
    return results


# ── Verdict extraction ───────────────────────────────────────────────────
# Ordered so the longest alternatives come first in the alternation.
_VERDICT_KEYWORDS = re.compile(
    r"\b(UNDERWEIGHT|OVERWEIGHT|HOLD|SELL|BUY)\b",
    re.IGNORECASE,
)

# Bold variant: **HOLD**, **Sell**, etc.
_VERDICT_BOLD_RE = re.compile(
    r"\*\*\s*(UNDERWEIGHT|OVERWEIGHT|HOLD|SELL|BUY)\s*\*\*",
    re.IGNORECASE,
)

# Russian + English verdict header lines (case-insensitive).
# Matches:  ## Итоговый рейтинг: **HOLD**
#           ## ВЕРДИКТ: **Hold**
#           ### Рейтинг: **SELL**
#           ## Рейтинг: Underweight
_VERDICT_LINE_RE = re.compile(
    r"^#{1,4}\s*[^\n]*?"
    r"(?:рейтинг|вердикт|verdict|rating|решение|decision)"
    r"[:\s]*\**\s*"
    r"(UNDERWEIGHT|OVERWEIGHT|HOLD|SELL|BUY)"
    r"\s*\**",
    re.IGNORECASE | re.MULTILINE,
)


def _extract_verdict(text: str) -> str:
    """Extract the recommendation verdict from the markdown text.

    Strategy: prefer a verdict that appears in a header line (most reliable),
    then fall back to the first bold verdict, then any verdict keyword in
    the first 30 lines.
    """
    # 1. Header-line verdict (highest confidence)
    m = _VERDICT_LINE_RE.search(text)
    if m is not None:
        return m.group(1).upper()

    # 2. Bold verdict in the first ~40 lines (covers most real reports)
    first_chunk = "\n".join(text.splitlines()[:40])
    m = _VERDICT_BOLD_RE.search(first_chunk)
    if m is not None:
        return m.group(1).upper()

    # 3. Any bare keyword in the first ~15 lines
    header_chunk = "\n".join(text.splitlines()[:15])
    m = _VERDICT_KEYWORDS.search(header_chunk)
    if m is not None:
        return m.group(1).upper()

    return "UNKNOWN"


# ── Ticker extraction ────────────────────────────────────────────────────
# Looks for the ticker in the first H1/H2 header:
#   # Вердикт Портфельного Менеджера: NFLX
#   # ФИНАЛЬНОЕ РЕШЕНИЕ ПОРТФЕЛЬНОГО МЕНЕДЖЕРА: CRWD
_TICKER_HEADER_RE = re.compile(
    r"^#{1,3}\s*[^\n]*?:\s*([A-Z]{1,5})\b",
    re.MULTILINE,
)
# Fallback: look for ticker mentioned in context like "позиции в FIG",
# "позиции** в FIG", "Инструмент: CRWD", or "акции NFLX".
# Allows optional markdown bold markers (**) between words.
_TICKER_BODY_RE = re.compile(
    r"(?:позици\w+)\*{0,2}\s+(?:в\s+)?([A-Z]{1,5})\b",
    re.MULTILINE,
)
# Also: **Инструмент:** CRWD (CrowdStrike)
_TICKER_INSTRUMENT_RE = re.compile(
    r"\*{0,2}инструмент\*{0,2}[\s:]+\*{0,2}([A-Z]{1,5})\b",
    re.IGNORECASE,
)


def _extract_ticker(text: str, fallback: str | None) -> str:
    """Extract ticker from markdown headers or use the provided fallback.

    Tries multiple strategies:
    1. Header with colon (most reliable)
    2. "Инструмент:" field
    3. Body text context ("позиции в XXX")
    4. Fallback argument
    """
    m = _TICKER_HEADER_RE.search(text)
    if m is not None:
        return m.group(1).upper()

    m = _TICKER_INSTRUMENT_RE.search(text)
    if m is not None:
        return m.group(1).upper()

    # Only search in first ~20 lines for body ticker to avoid false positives
    first_chunk = "\n".join(text.splitlines()[:20])
    m = _TICKER_BODY_RE.search(first_chunk)
    if m is not None:
        return m.group(1).upper()

    if fallback:
        return fallback.upper()
    return "UNKNOWN"


# ── Confidence extraction ────────────────────────────────────────────────
# Matches: "Убеждённость: 8/10", "убеждённость 7 / 10",
#          "confidence: 8", "confidence 7/10", "7 из 10"
_CONFIDENCE_RE = re.compile(
    r"(?:убеждённость|убежденность|уверенность|confidence)"
    r"[\s:]*(\d{1,2})\s*/?\s*10",
    re.IGNORECASE,
)
_CONFIDENCE_IZ_RE = re.compile(
    r"(\d{1,2})\s+из\s+10",
    re.IGNORECASE,
)


def _extract_confidence(text: str) -> int | None:
    """Extract confidence score (1-10) if present."""
    m = _CONFIDENCE_RE.search(text)
    if m is not None:
        val = int(m.group(1))
        if 1 <= val <= 10:
            return val

    m = _CONFIDENCE_IZ_RE.search(text)
    if m is not None:
        val = int(m.group(1))
        if 1 <= val <= 10:
            return val

    return None


# ── Stop-loss extraction ─────────────────────────────────────────────────
# Russian and English keywords that precede or surround the stop-loss price.
_STOP_LOSS_LINE_RE = re.compile(
    r"(?:стоп[\s-]*лосс|stop[\s-]*loss)"
    r"[^\n$]*?"
    r"\$\s?([\d]+(?:[.,]\d{1,3})*)",
    re.IGNORECASE,
)
# Also check table rows like:  | Стоп-лосс | **$77** |
_STOP_LOSS_TABLE_RE = re.compile(
    r"\|\s*\**\s*(?:стоп[\s-]*лосс|stop[\s-]*loss)[^\|]*\|\s*\**\s*"
    r"\$\s?([\d]+(?:[.,]\d{1,3})*)",
    re.IGNORECASE,
)


def _extract_stop_loss(text: str) -> float | None:
    """Extract the stop-loss price."""
    # Table row is most precise
    m = _STOP_LOSS_TABLE_RE.search(text)
    if m is not None:
        return _parse_price_str(m.group(1))

    # Inline reference
    m = _STOP_LOSS_LINE_RE.search(text)
    if m is not None:
        return _parse_price_str(m.group(1))

    return None


# ── Entry trigger extraction ─────────────────────────────────────────────
# Prefer specific action-oriented keywords over generic "вход" which
# appears in debate/analysis context too.
_ENTRY_SPECIFIC_RE = re.compile(
    r"(?:закрытие\s*выше|триггер\s*входа|entry\s*trigger|breakout)"
    r"[^\n$]*?"
    r"\$\s?([\d]+(?:[.,]\d{1,3})*)",
    re.IGNORECASE,
)
_ENTRY_GENERIC_RE = re.compile(
    r"(?:вход|entry)"
    r"[^\n$]*?"
    r"\$\s?([\d]+(?:[.,]\d{1,3})*)",
    re.IGNORECASE,
)


def _extract_entry_trigger(text: str) -> float | None:
    """Extract entry trigger price from nearby keywords.

    Prefers specific action keywords (закрытие выше, триггер входа) over
    generic "вход" which appears frequently in debate sections.
    Searches the investment plan section (lower half) first.
    """
    # Search in the plan/action section (second half of doc) for specific triggers
    midpoint = len(text) // 3
    plan_text = text[midpoint:]

    m = _ENTRY_SPECIFIC_RE.search(plan_text)
    if m is not None:
        val = _parse_price_str(m.group(1))
        if val is not None:
            return val

    # Try specific pattern anywhere
    m = _ENTRY_SPECIFIC_RE.search(text)
    if m is not None:
        val = _parse_price_str(m.group(1))
        if val is not None:
            return val

    # Fall back to generic "вход" in plan section only
    m = _ENTRY_GENERIC_RE.search(plan_text)
    if m is not None:
        return _parse_price_str(m.group(1))

    return None


# ── Profit target extraction ─────────────────────────────────────────────
_TARGET_LINE_RE = re.compile(
    r"(?:целевая|цель|target|profit\s*target|фиксация|полная\s*фиксация)"
    r"[^\n$]*?"
    r"\$\s?([\d]+(?:[.,]\d{1,3})*)",
    re.IGNORECASE,
)
_TARGET_TABLE_RE = re.compile(
    r"\|\s*\**\s*(?:целевая|цель|target|полная\s*фиксация|частичная\s*фиксация|фиксация)"
    r"[^\|]*\|\s*\**\s*"
    r"\$\s?([\d]+(?:[.,]\d{1,3})*)",
    re.IGNORECASE,
)

# Dedicated pattern for "полная фиксация" (full take-profit) in tables.
_FULL_TARGET_TABLE_RE = re.compile(
    r"\|\s*\**\s*(?:полная\s*фиксация|full\s*target)"
    r"[^\|]*\|\s*\**\s*"
    r"\$\s?([\d]+(?:[.,]\d{1,3})*)",
    re.IGNORECASE,
)


def _extract_profit_target(text: str) -> float | None:
    """Extract the profit target / take-profit price.

    Prefers "полная фиксация" over "частичная фиксация" when both appear
    in separate table rows.
    """
    # Try "полная фиксация" table row first
    m = _FULL_TARGET_TABLE_RE.search(text)
    if m is not None:
        val = _parse_price_str(m.group(1))
        if val is not None:
            return val

    # Any target table row
    m = _TARGET_TABLE_RE.search(text)
    if m is not None:
        val = _parse_price_str(m.group(1))
        if val is not None:
            return val

    # Inline reference
    m = _TARGET_LINE_RE.search(text)
    if m is not None:
        return _parse_price_str(m.group(1))

    return None


# ── Price at analysis time ───────────────────────────────────────────────
# Looks for specific patterns indicating the current market price:
#   "текущая цена $580", "текущей рыночной цене $87",
#   "по текущей цене $87", "current price $580", "при цене $87"
# NOTE: bare "по $X" is too common in Russian (means "at/by") and causes
# false positives -- we require "по текущей" or "при цене" specificity.
# High-confidence: nominative "текущая цена $X" (direct statement of price).
_PRICE_DIRECT_RE = re.compile(
    r"текуща[яй]\s+(?:рыноч\w*\s+)?цен\w*\s+\$\s?([\d]+(?:[.,]\d{1,3})*)",
    re.IGNORECASE,
)
# Medium-confidence: oblique "текущей цены", "current price", "при цене".
_PRICE_OBLIQUE_RE = re.compile(
    r"(?:текущ\w*\s*(?:рыноч\w*\s*)?цен\w*|current\s*price|при\s*цене)"
    r"[^\n$]{0,30}?"
    r"\$\s?([\d]+(?:[.,]\d{1,3})*)",
    re.IGNORECASE,
)
# Pattern for "акция стоит $X" or "цена акции $X"
_STOCK_PRICE_RE = re.compile(
    r"(?:акци\w+\s+(?:стоит|торгуется)|цена\s+акци\w+)"
    r"[^\n$]{0,20}?"
    r"\$\s?([\d]+(?:[.,]\d{1,3})*)",
    re.IGNORECASE,
)


def _extract_price_at_analysis(text: str) -> float | None:
    """Extract the price at analysis time (best-effort).

    Prefers direct nominative statements ("текущая цена $580") over
    oblique references ("текущей цены ($520"), which often appear in
    descriptions of other parameters (trailing stops, ranges).
    Returns None rather than risk a false positive.
    """
    # Highest confidence: "текущая цена $580"
    m = _PRICE_DIRECT_RE.search(text)
    if m is not None:
        return _parse_price_str(m.group(1))

    # Medium confidence: oblique references
    m = _PRICE_OBLIQUE_RE.search(text)
    if m is not None:
        return _parse_price_str(m.group(1))

    m = _STOCK_PRICE_RE.search(text)
    if m is not None:
        return _parse_price_str(m.group(1))

    return None


# ── Review date extraction ───────────────────────────────────────────────
# Only match explicit review-date patterns, not bare "пересмотр" which
# appears frequently in "пересмотр на Underweight" contexts.
_REVIEW_DATE_RE = re.compile(
    r"(?:горизонт\s*пересмотра|дата\s*пересмотра|review\s*date|re-?evaluation\s*date)"
    r"[\s:]*([^\n|]{5,80})",
    re.IGNORECASE,
)
# Also match "Горизонт пересмотра:" as a table/metadata field
_REVIEW_FIELD_RE = re.compile(
    r"(?:горизонт|срок)\s*(?:пересмотра|ревью)"
    r"[\s:]+([^\n|]{5,80})",
    re.IGNORECASE,
)


def _extract_review_date(text: str) -> str | None:
    """Extract the review / re-evaluation date string if mentioned.

    Only matches explicit review-horizon patterns to avoid false positives
    from "пересмотр на Underweight" and similar rating-change phrases.
    """
    m = _REVIEW_DATE_RE.search(text)
    if m is not None:
        raw = m.group(1).strip().rstrip("|").strip()
        cleaned = raw.replace("**", "").replace("*", "").strip()
        if cleaned:
            return cleaned[:100]

    m = _REVIEW_FIELD_RE.search(text)
    if m is not None:
        raw = m.group(1).strip().rstrip("|").strip()
        cleaned = raw.replace("**", "").replace("*", "").strip()
        if cleaned:
            return cleaned[:100]

    return None


# ── Notes extraction ─────────────────────────────────────────────────────
# Match conclusion/summary headers but NOT "итоговый рейтинг" or
# "итоговое решение" (which are verdict headers, not conclusions).
_CONCLUSION_HEADER_RE = re.compile(
    r"^#{1,4}\s*(?:заключение|вывод[ы]?\b|conclusion|summary|итог\b(?!\w))",
    re.IGNORECASE | re.MULTILINE,
)


def _extract_notes(text: str) -> str | None:
    """Extract key takeaway from the conclusion section.

    Falls back to the last bold sentence in the document if no explicit
    conclusion header is found.
    """
    m = _CONCLUSION_HEADER_RE.search(text)
    if m is not None:
        # Grab text after the header until the next header or end
        after = text[m.end():]
        lines = after.strip().splitlines()
        # Collect non-empty, non-header lines
        note_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                break
            if stripped:
                note_lines.append(stripped)
            if len("\n".join(note_lines)) >= _NOTES_MAX_LEN:
                break
        if note_lines:
            joined = " ".join(note_lines)
            # Strip markdown formatting
            cleaned = joined.replace("**", "").replace("*", "").strip()
            return cleaned[:_NOTES_MAX_LEN] if cleaned else None

    # Fallback: find the last bold sentence that looks like a standalone
    # remark (min 20 chars, contains a letter, not a fragment from a list).
    bold_sentences = re.findall(r"\*\*([^*]{20,200})\*\*", text)
    # Filter out list-item fragments and short labels
    candidates = [
        s.strip()
        for s in bold_sentences
        if re.search(r"[а-яА-Яa-zA-Z]{3,}", s)
        and not s.strip().startswith(("—", "-", "|"))
    ]
    if candidates:
        last = candidates[-1]
        return last[:_NOTES_MAX_LEN] if last else None

    return None


# ── Public API ───────────────────────────────────────────────────────────


def extract_recommendation(
    markdown: str,
    *,
    ticker: str | None = None,
    analysis_id: int | None = None,
) -> ExtractedRecommendation:
    """Parse a final_trade_decision.md and extract structured recommendation data.

    Parameters
    ----------
    markdown:
        The raw markdown content of the report.
    ticker:
        Override ticker (if already known from the caller context).
        Falls back to extracting from the document header.
    analysis_id:
        Optional FK to the ``analyses`` table for traceability.

    Returns
    -------
    ExtractedRecommendation
        A frozen dataclass with all fields populated where data was found.
        Fields that could not be extracted are set to ``None``.
    """
    if not markdown or not markdown.strip():
        log.warning("Empty markdown provided to extract_recommendation")
        return ExtractedRecommendation(
            ticker=ticker.upper() if ticker else "UNKNOWN",
            verdict="UNKNOWN",
            analysis_id=analysis_id,
        )

    extracted_ticker = _extract_ticker(markdown, ticker)
    verdict = _extract_verdict(markdown)
    confidence = _extract_confidence(markdown)
    price_at_analysis = _extract_price_at_analysis(markdown)
    stop_loss = _extract_stop_loss(markdown)
    entry_trigger = _extract_entry_trigger(markdown)
    profit_target = _extract_profit_target(markdown)
    review_date = _extract_review_date(markdown)
    notes = _extract_notes(markdown)

    log.debug(
        "Extracted recommendation: ticker=%s verdict=%s confidence=%s "
        "stop_loss=%s entry=%s target=%s",
        extracted_ticker,
        verdict,
        confidence,
        stop_loss,
        entry_trigger,
        profit_target,
    )

    return ExtractedRecommendation(
        ticker=extracted_ticker,
        verdict=verdict,
        confidence=confidence,
        price_at_analysis=price_at_analysis,
        stop_loss=stop_loss,
        entry_trigger=entry_trigger,
        profit_target=profit_target,
        review_date=review_date,
        notes=notes,
        analysis_id=analysis_id,
    )


def extract_from_file(
    path: Path,
    *,
    ticker: str | None = None,
    analysis_id: int | None = None,
) -> ExtractedRecommendation:
    """Read a ``final_trade_decision.md`` file and extract recommendation data.

    Parameters
    ----------
    path:
        Path to the markdown file.
    ticker:
        Override ticker (if already known).
    analysis_id:
        Optional FK to the ``analyses`` table.

    Returns
    -------
    ExtractedRecommendation
        Structured data from the file.  Returns a minimal object with
        ``verdict="UNKNOWN"`` if the file cannot be read.
    """
    resolved = path.resolve()
    if not resolved.is_file():
        log.warning("Report file not found: %s", resolved)
        return ExtractedRecommendation(
            ticker=ticker.upper() if ticker else "UNKNOWN",
            verdict="UNKNOWN",
            analysis_id=analysis_id,
        )

    try:
        markdown = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        log.error("Failed to read report file %s: %s", resolved, exc)
        return ExtractedRecommendation(
            ticker=ticker.upper() if ticker else "UNKNOWN",
            verdict="UNKNOWN",
            analysis_id=analysis_id,
        )

    return extract_recommendation(
        markdown,
        ticker=ticker,
        analysis_id=analysis_id,
    )
