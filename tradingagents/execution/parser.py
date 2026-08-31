"""Parse Portfolio Manager and Trader prose into execution-ready parameters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Literal, Optional

from tradingagents.agents.utils.rating import parse_rating


TradeAction = Literal["buy", "sell", "hold"]

_PRICE_RE = re.compile(
    r"(?<![\w.])\$?\s*(\d{1,4}(?:,\d{3})*(?:\.\d+)?)"
    r"(?:\s*(?:-|to|–|—)\s*\$?\s*(\d{1,4}(?:,\d{3})*(?:\.\d+)?))?"
    r"(?!\s*[%xX]|\w)",
    re.IGNORECASE,
)

_ENTRY_LABEL_RE = re.compile(
    r"(?:\*\*)?\b(?:entry price|entry level|entry zone|entry target|entry|"
    r"enter(?:ing)?|initial entry|limit order|starter position|starter tranche|"
    r"pullback zone|pullback area|buy zone|accumulation zone|add(?:\s+near|\s+at)?)"
    r"\b(?:\*\*)?\s*(?::|-|at|around|near|~)?\s*",
    re.IGNORECASE,
)
_STOP_LABEL_RE = re.compile(
    r"(?:\*\*)?\b(?:stop loss|stop-loss|stop|protective stop|risk threshold|"
    r"thesis invalidation|invalidated|invalidation|breaks down|below)"
    r"\b(?:\*\*)?\s*(?::|-|at|around|near|~)?\s*",
    re.IGNORECASE,
)
_TARGET_LABEL_RE = re.compile(
    r"(?:\*\*)?\b(?:price target|target price|target|take profit|profit target)"
    r"\b(?:\*\*)?\s*(?::|-|at|around|near|~)?\s*",
    re.IGNORECASE,
)
_UPSIDE_TARGET_RE = re.compile(
    r"(?:toward|towards|back toward|move back toward|upside(?:\s+target)?|profit(?:\s+taking)?(?:\s+levels?)?|"
    r"target reflects .*? toward|aiming for .*? toward)[^\n]{0,80}",
    re.IGNORECASE,
)
_SKIP_PRICE_TRAILING_RE = re.compile(
    r"\s*(?:shares?|sessions?|days?|weeks?|months?|years?|tranches?|times?|closes?|atr)\b",
    re.IGNORECASE,
)
_CASH_PCT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*%(?:\s*of\s+(?:the\s+)?"
    r"(?:available\s+)?(?:cash|buying\s+power|usable\s+(?:cash|money|capital)|"
    r"free\s+cash|capital|portfolio|equity))?",
    re.IGNORECASE,
)
_POSITION_SIZING_RE = re.compile(
    r"(?:\*\*)?position sizing(?:\*\*)?\s*:\s*(.+)",
    re.IGNORECASE,
)

_ENTRY_WORDS = (
    "entry",
    "enter",
    "buy",
    "add",
    "accumulate",
    "limit order",
    "starter position",
    "starter tranche",
    "pullback zone",
    "pullback area",
    "buy zone",
    "accumulation zone",
)
_STOP_WORDS = (
    "stop",
    "stop-loss",
    "risk threshold",
    "invalidat",
    "breaks down",
    "below",
)
_TARGET_WORDS = ("price target", "target price", "profit target", "take profit", "target")
_IGNORE_ENTRY_WORDS = ("price target", "target price", "stop", "time horizon")
_HARD_STOP_WORDS = (
    "hard invalidation",
    "hard stop",
    "structural break",
    "exit remaining",
    "thesis invalidation",
)
_CASH_HINTS = (
    "cash",
    "buying power",
    "usable",
    "available",
    "free cash",
    "deployable",
)


@dataclass(frozen=True)
class ParsedTradeDecision:
    """Decision distilled from the Portfolio Manager report and Trader plan."""

    rating: str
    action: TradeAction
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    price_target: Optional[float] = None
    time_horizon: Optional[str] = None
    cash_allocation_pct: Optional[float] = None
    rating_source: str = "portfolio_manager"
    price_source: str = "portfolio_manager"

    @property
    def should_trade(self) -> bool:
        return self.action in {"buy", "sell"}


def parse_trade_decision(
    portfolio_manager_text: str,
    fallback_text: str | None = None,
) -> ParsedTradeDecision:
    """Parse the final PM text and optional trader fallback into a decision.

    The Portfolio Manager remains authoritative for direction. Price levels,
    time horizon, and cash-percent sizing are taken from the PM report first;
    missing prices and sizing fall back to the Trader proposal.
    """
    pm_text = portfolio_manager_text or ""
    trader_text = fallback_text or ""
    rating = parse_rating(pm_text)
    action = _rating_to_action(rating)

    entry_price = _extract_entry_price(pm_text)
    stop_loss = _extract_stop_loss(pm_text, entry_price)
    price_target = _extract_target_price(pm_text, entry_price, stop_loss)
    if price_target is None:
        price_target = _extract_upside_target_price(pm_text, entry_price, stop_loss)
    price_source = "portfolio_manager"

    if entry_price is None and trader_text:
        entry_price = _extract_entry_price(trader_text)
        if entry_price is not None:
            price_source = "trader_fallback"

    if stop_loss is None and trader_text:
        stop_loss = _extract_stop_loss(trader_text, entry_price)
        if stop_loss is not None and price_source == "portfolio_manager":
            price_source = "trader_fallback"

    if price_target is None and trader_text:
        price_target = _extract_target_price(trader_text, entry_price, stop_loss)
        if price_target is None:
            price_target = _extract_upside_target_price(trader_text, entry_price, stop_loss)
        if price_target is not None and price_source == "portfolio_manager":
            price_source = "trader_fallback"

    time_horizon = extract_time_horizon(pm_text) or extract_time_horizon(trader_text)
    cash_allocation_pct = extract_cash_allocation_pct(pm_text)
    if cash_allocation_pct is None:
        cash_allocation_pct = extract_cash_allocation_pct(trader_text)

    return ParsedTradeDecision(
        rating=rating,
        action=action,
        entry_price=entry_price,
        stop_loss=stop_loss,
        price_target=price_target,
        time_horizon=time_horizon,
        cash_allocation_pct=cash_allocation_pct,
        price_source=price_source,
    )


def extract_time_horizon(text: str) -> Optional[str]:
    """Read a Time Horizon / estimated hold period from rendered markdown."""
    if not text:
        return None
    for marker in ("**Time Horizon**:", "Time Horizon:", "**Hold Period**:", "Hold Period:"):
        start = text.find(marker)
        if start < 0:
            continue
        body = text[start + len(marker) :].strip()
        next_section = body.find("\n\n**")
        if next_section >= 0:
            body = body[:next_section]
        line = body.split("\n", 1)[0].strip()
        return line or None
    return None


def extract_cash_allocation_pct(text: str) -> Optional[float]:
    """Extract a 0-100 allocation percent, preferring language about available cash."""
    if not text:
        return None

    sizing_line = None
    match = _POSITION_SIZING_RE.search(text)
    if match:
        sizing_line = match.group(1).strip()

    candidates: list[tuple[int, float]] = []
    for source in (sizing_line, text):
        if not source:
            continue
        for pct_match in _CASH_PCT_RE.finditer(source):
            value = _clamp_pct(_to_float(pct_match.group(1)))
            if value is None:
                continue
            snippet = source[max(0, pct_match.start() - 40) : pct_match.end() + 40].lower()
            rank = 0 if any(hint in snippet for hint in _CASH_HINTS) else 1
            if source is sizing_line:
                rank -= 1
            candidates.append((rank, value))
        if source is sizing_line:
            break

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _rating_to_action(rating: str) -> TradeAction:
    normalized = rating.strip().lower()
    if normalized in {"buy", "overweight"}:
        return "buy"
    if normalized in {"sell", "underweight"}:
        return "sell"
    return "hold"


def _extract_entry_price(text: str) -> Optional[float]:
    return _extract_price_from_text(
        text,
        label_re=_ENTRY_LABEL_RE,
        context_words=_ENTRY_WORDS,
        ignore_words=_IGNORE_ENTRY_WORDS,
        selector=_select_entry_price,
    )


def _extract_stop_loss(text: str, entry_price: Optional[float]) -> Optional[float]:
    return _extract_price_from_text(
        text,
        label_re=_STOP_LABEL_RE,
        context_words=_STOP_WORDS,
        ignore_words=("price target", "target price", "time horizon"),
        selector=lambda prices, context: _select_stop_price(prices, entry_price, context),
    )


def _extract_target_price(
    text: str,
    entry_price: Optional[float],
    stop_loss: Optional[float],
) -> Optional[float]:
    return _extract_price_from_text(
        text,
        label_re=_TARGET_LABEL_RE,
        context_words=_TARGET_WORDS,
        ignore_words=("time horizon",),
        selector=lambda prices, context: _select_target_price(
            prices, entry_price, stop_loss, context
        ),
    )


def _extract_upside_target_price(
    text: str,
    entry_price: Optional[float],
    stop_loss: Optional[float],
) -> Optional[float]:
    if not text:
        return None
    for match in _UPSIDE_TARGET_RE.finditer(text):
        snippet = match.group(0)
        prices = _prices_in(snippet)
        chosen = _select_target_price(prices, entry_price, stop_loss, snippet)
        if chosen is not None:
            return chosen
    return None


def _extract_price_from_text(
    text: str,
    *,
    label_re: re.Pattern[str],
    context_words: Iterable[str],
    ignore_words: Iterable[str],
    selector,
) -> Optional[float]:
    if not text:
        return None

    for match in label_re.finditer(text):
        snippet = text[match.end() : match.end() + 120]
        prices = _prices_in(snippet)
        chosen = selector(prices, snippet)
        if chosen is not None:
            return chosen

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if any(word in lowered for word in ignore_words):
            continue
        if any(word in lowered for word in context_words):
            prices = _prices_in(line)
            chosen = selector(prices, line)
            if chosen is not None:
                return chosen

    return None


def _prices_in(text: str) -> list[float]:
    prices: list[float] = []
    for match in _PRICE_RE.finditer(text):
        if _should_skip_price_match(text, match):
            continue
        price = _to_float(match.group(1))
        if match.group(2) is not None:
            end = _to_float(match.group(2))
            if price is not None and end is not None:
                price = min(price, end)
        if price is None:
            continue
        if price not in prices:
            prices.append(price)
    return prices


def _should_skip_price_match(text: str, match: re.Match[str]) -> bool:
    trailing = text[match.end() : match.end() + 24]
    return bool(_SKIP_PRICE_TRAILING_RE.match(trailing))


def _to_float(value: str) -> Optional[float]:
    try:
        return float(value.replace(",", ""))
    except (TypeError, ValueError):
        return None


def _clamp_pct(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    if value <= 0 or value > 100:
        return None
    return value


def _select_entry_price(prices: list[float], _context: str = "") -> Optional[float]:
    realistic = [price for price in prices if price >= 1]
    return realistic[0] if realistic else None


def _select_stop_price(
    prices: list[float], entry_price: Optional[float], context: str = ""
) -> Optional[float]:
    realistic = [price for price in prices if price >= 1]
    if not realistic:
        return None

    if entry_price is not None:
        floor = max(1.0, entry_price * 0.5)
        below_entry = [price for price in realistic if floor <= price < entry_price]
        if not below_entry:
            below_entry = [price for price in realistic if price < entry_price]
        if below_entry:
            lowered = context.lower()
            if any(word in lowered for word in _HARD_STOP_WORDS):
                return min(below_entry)
            return max(below_entry)

    return realistic[0]


def _select_target_price(
    prices: list[float],
    entry_price: Optional[float],
    stop_loss: Optional[float],
    _context: str = "",
) -> Optional[float]:
    realistic = [price for price in prices if price >= 1]
    if not realistic:
        return None

    floor = max(value for value in (entry_price, stop_loss, 0) if value is not None)
    above_floor = [price for price in realistic if price > floor]
    if above_floor:
        return max(above_floor)
    return realistic[0]
