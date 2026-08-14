"""StockTwits public symbol-stream fetcher.

StockTwits exposes a per-symbol message stream at
``api.stocktwits.com/api/2/streams/symbol/{ticker}.json`` that requires no
API key, no OAuth, and no registration. Each message includes a
user-labeled sentiment field (``Bullish``/``Bearish``/null), the message
body, timestamp, and posting user.

The function is deliberately self-contained: short timeout, graceful
degradation on any HTTP or parse failure, and a string return type so
the calling agent gets a uniform interface regardless of whether the
network call succeeded.
"""

from __future__ import annotations

import http.client
import json
import logging
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen

from .symbol_utils import crypto_base

logger = logging.getLogger(__name__)

_API = "https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"


def _iso_to_epoch(iso_str: str | None) -> float | None:
    """Parse StockTwits' ISO-8601 ``created_at`` to a UTC epoch, or None."""
    if not iso_str:
        return None
    try:
        normalized = iso_str[:-1] + "+00:00" if iso_str.endswith("Z") else iso_str
        return datetime.fromisoformat(normalized).timestamp()
    except (ValueError, TypeError):
        return None


def _window_epochs(start_date: str | None, end_date: str | None) -> tuple[float | None, float | None]:
    """UTC window [start midnight, end+1 day midnight) for inclusive date bounds.

    ``end_date`` stays inclusive for the whole day (mirrors the yfinance-news
    convention: a message timestamped anywhere on ``end_date`` belongs to the
    window; anything on the following midnight does not).
    """
    start_ts = None
    if start_date:
        start_ts = datetime.strptime(start_date, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        ).timestamp()
    end_ts = None
    if end_date:
        end_ts = (
            datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            + timedelta(days=1)
        ).timestamp()
    return start_ts, end_ts


def _in_window(epoch: float | None, start_ts: float | None, end_ts: float | None) -> bool:
    """True when ``epoch`` is in [start_ts, end_ts).

    Undated rows are excluded from a dated window (they could be anything,
    including future posts); in live mode with no window they are kept,
    mirroring the yfinance-news convention.
    """
    if epoch is None:
        return start_ts is None and end_ts is None
    if start_ts is not None and epoch < start_ts:
        return False
    return not (end_ts is not None and epoch >= end_ts)


def _stocktwits_symbol(ticker: str) -> str:
    """Map a crypto pair to StockTwits' ``<BASE>.X`` convention.

    StockTwits lists crypto as ``BTC.X`` (Yahoo's ``BTC-USD`` form 404s), so any
    crypto symbol resolves to its base plus ``.X``; other symbols pass through
    upper-cased.
    """
    base = crypto_base(ticker)
    return f"{base}.X" if base else ticker.strip().upper()


def fetch_stocktwits_messages(
    ticker: str,
    limit: int = 30,
    timeout: float = 10.0,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """Fetch recent StockTwits messages for ``ticker`` and return them as a
    formatted plaintext block ready for prompt injection.

    When ``start_date`` / ``end_date`` are provided (e.g. a historical
    backtest trade date), messages timestamped outside the window are dropped
    and a window-specific placeholder is returned when nothing survives the
    filter -- StockTwits' public stream only serves current posts, so a
    historical analysis must not present today's posts as historical signal
    (#1220).

    Returns a placeholder string when the endpoint is unreachable, the
    symbol has no messages, or the response shape is unexpected — the
    caller never has to special-case None or exceptions.
    """
    url = _API.format(ticker=_stocktwits_symbol(ticker))
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except (OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
        # OSError covers URLError/TimeoutError/connection resets; HTTPException
        # covers chunked-transfer errors (IncompleteRead/BadStatusLine, #1024).
        logger.warning("StockTwits fetch failed for %s: %s", ticker, exc)
        return f"<stocktwits unavailable: {type(exc).__name__}>"

    messages = data.get("messages", []) if isinstance(data, dict) else []
    if not messages:
        return f"<no StockTwits messages found for ${ticker.upper()}>"

    start_ts, end_ts = _window_epochs(start_date, end_date)
    messages = [
        m
        for m in messages
        if _in_window(_iso_to_epoch(m.get("created_at")), start_ts, end_ts)
    ]
    if not messages:
        if end_date:
            return (
                f"<no StockTwits messages found for ${ticker.upper()} in the "
                f"requested window (through {end_date}); historical social "
                f"data may be unavailable>"
            )
        return f"<no StockTwits messages found for ${ticker.upper()}>"

    lines = []
    bullish = bearish = unlabeled = 0
    for m in messages[:limit]:
        created = m.get("created_at", "")
        user = (m.get("user") or {}).get("username", "?")
        entities = m.get("entities") or {}
        sentiment_obj = entities.get("sentiment") or {}
        sentiment = sentiment_obj.get("basic") if isinstance(sentiment_obj, dict) else None
        body = (m.get("body") or "").replace("\n", " ").strip()
        if len(body) > 280:
            body = body[:280] + "…"

        if sentiment == "Bullish":
            bullish += 1
            tag = "Bullish"
        elif sentiment == "Bearish":
            bearish += 1
            tag = "Bearish"
        else:
            unlabeled += 1
            tag = "no-label"
        lines.append(f"[{created} · @{user} · {tag}] {body}")

    total = bullish + bearish + unlabeled
    bull_pct = round(100 * bullish / total) if total else 0
    bear_pct = round(100 * bearish / total) if total else 0
    summary = (
        f"Bullish: {bullish} ({bull_pct}%) · "
        f"Bearish: {bearish} ({bear_pct}%) · "
        f"Unlabeled: {unlabeled} · "
        f"Total: {total} most-recent messages"
    )
    return summary + "\n\n" + "\n".join(lines)
