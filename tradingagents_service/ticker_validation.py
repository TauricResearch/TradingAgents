from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import requests


_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,30}$")
_KNOWN_CORRECTIONS = {
    "APPL": "AAPL",
    "GOOGL.US": "GOOGL",
    "GOOG.US": "GOOG",
}


@dataclass(frozen=True)
class TickerValidationResult:
    accepted: bool
    symbol: str
    reason: str | None = None
    suggestion: str | None = None
    validator: str = "yahoo-chart"


def validate_ticker_for_shadow_run(ticker: str) -> TickerValidationResult:
    """Validate instrument identity before queueing expensive LLM work.

    This is intentionally conservative: reject known typo aliases and symbols
    Yahoo explicitly says are unknown; fail open on transient network errors.
    """
    symbol = ticker.strip().upper()
    if not _SYMBOL_RE.fullmatch(symbol):
        return TickerValidationResult(
            accepted=False,
            symbol=symbol,
            reason="ticker must be an uppercase exchange symbol using letters, numbers, '.', or '-'",
        )

    suggestion = _KNOWN_CORRECTIONS.get(symbol)
    if suggestion is not None:
        return TickerValidationResult(
            accepted=False,
            symbol=symbol,
            reason=f"ticker {symbol} is a likely typo",
            suggestion=suggestion,
            validator="known-correction",
        )

    if os.getenv("TRADINGAGENTS_TICKER_VALIDATION", "yahoo").lower() in {"off", "false", "0"}:
        return TickerValidationResult(accepted=True, symbol=symbol, validator="disabled")

    return _validate_with_yahoo_chart(symbol)


@lru_cache(maxsize=2048)
def _validate_with_yahoo_chart(symbol: str) -> TickerValidationResult:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    try:
        response = requests.get(
            url,
            params={"range": "5d", "interval": "1d"},
            headers={"User-Agent": "tradingagents-flint-shadow/0.1"},
            timeout=float(os.getenv("TRADINGAGENTS_TICKER_VALIDATION_TIMEOUT_SECONDS", "2.0")),
        )
        payload: dict[str, Any] = response.json()
    except (requests.RequestException, ValueError):
        return TickerValidationResult(
            accepted=True,
            symbol=symbol,
            reason="ticker validator unavailable; accepted without semantic confirmation",
            validator="yahoo-chart-unavailable",
        )

    chart = payload.get("chart") if isinstance(payload, dict) else {}
    error = chart.get("error") if isinstance(chart, dict) else None
    if error:
        return TickerValidationResult(
            accepted=False,
            symbol=symbol,
            reason=str(error.get("description") or error.get("code") or "ticker was not found"),
            suggestion=_suggest_symbol(symbol),
        )

    results = chart.get("result") if isinstance(chart, dict) else None
    if not results:
        return TickerValidationResult(
            accepted=False,
            symbol=symbol,
            reason="ticker validator returned no instrument data",
            suggestion=_suggest_symbol(symbol),
        )

    meta = results[0].get("meta") if isinstance(results[0], dict) else {}
    validated_symbol = str(meta.get("symbol") or symbol).upper()
    if validated_symbol.split(".", 1)[0] != symbol.split(".", 1)[0]:
        return TickerValidationResult(
            accepted=False,
            symbol=symbol,
            reason=f"ticker resolved to unexpected instrument {validated_symbol}",
            suggestion=validated_symbol,
        )
    return TickerValidationResult(accepted=True, symbol=symbol)


def _suggest_symbol(symbol: str) -> str | None:
    return _KNOWN_CORRECTIONS.get(symbol)
