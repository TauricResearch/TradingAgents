"""Explicit NSE/BSE ticker normalization."""

from __future__ import annotations

import re

_EXCHANGE_SUFFIX = {"NSE": ".NS", "BSE": ".BO"}
_SUFFIX_EXCHANGE = {suffix: exchange for exchange, suffix in _EXCHANGE_SUFFIX.items()}
_TICKER_RE = re.compile(r"^[A-Z0-9](?:[A-Z0-9&-]{0,27}[A-Z0-9])?$")


def normalize_indian_symbol(symbol: str, exchange: str | None = None) -> str:
    """Return a Yahoo-style Indian symbol, requiring exchange context if bare.

    A suffix supplies exchange context. A conflicting explicit exchange is an
    error, and a bare ticker without context is never guessed as NSE or BSE.
    """
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("Indian ticker must be a non-empty string")

    value = symbol.strip().upper().rstrip("+")
    if not value:
        raise ValueError("Indian ticker must be a non-empty string")
    if exchange is not None and not isinstance(exchange, str):
        raise ValueError("exchange must be NSE or BSE")
    suffix_exchange = next(
        (known for suffix, known in _SUFFIX_EXCHANGE.items() if value.endswith(suffix)),
        None,
    )
    selected_exchange = exchange.strip().upper() if isinstance(exchange, str) else exchange
    if selected_exchange is not None and selected_exchange not in _EXCHANGE_SUFFIX:
        raise ValueError(f"Unsupported Indian exchange {exchange!r}; use NSE or BSE")
    if suffix_exchange and selected_exchange and suffix_exchange != selected_exchange:
        raise ValueError(
            f"Ticker {symbol!r} identifies {suffix_exchange}, not {selected_exchange}"
        )

    resolved_exchange = selected_exchange or suffix_exchange
    if resolved_exchange is None:
        raise ValueError("Exchange is required for a bare Indian ticker")

    suffix = _EXCHANGE_SUFFIX[resolved_exchange]
    if suffix_exchange:
        value = value[: -len(suffix)]
    if not value or value.endswith((".NS", ".BO")):
        raise ValueError(f"Invalid Indian ticker {symbol!r}")
    if not _TICKER_RE.fullmatch(value):
        raise ValueError(f"Invalid Indian ticker syntax {symbol!r}")
    return f"{value}{suffix}"