from __future__ import annotations

from typing import Any


def _normalize_ticker(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().upper()


def _normalize_tickers(value: Any) -> list[str]:
    parts: list[str] = []
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, (list, tuple)):
        for item in value:
            parts.extend(str(item).split(","))

    tickers: list[str] = []
    seen: set[str] = set()
    for part in parts:
        ticker = _normalize_ticker(part)
        if ticker and ticker not in seen:
            tickers.append(ticker)
            seen.add(ticker)
    return tickers


def normalize_run_params(run_type: str, params: dict[str, Any] | None) -> dict[str, Any]:
    """Return a canonical params shape for persisted run metadata."""
    normalized = dict(params or {})
    ticker = _normalize_ticker(normalized.get("ticker"))
    tickers = _normalize_tickers(normalized.get("tickers"))

    if run_type == "pipeline":
        if ticker:
            normalized["ticker"] = ticker
        else:
            normalized.pop("ticker", None)
        normalized.pop("tickers", None)
        return normalized

    if run_type == "mock":
        mock_type = str(normalized.get("mock_type") or "pipeline").strip().lower() or "pipeline"
        normalized["mock_type"] = mock_type
        if mock_type == "auto":
            if tickers:
                normalized["tickers"] = tickers
            else:
                normalized.pop("tickers", None)
            normalized.pop("ticker", None)
            return normalized
        if mock_type == "pipeline":
            if ticker:
                normalized["ticker"] = ticker
            else:
                normalized.pop("ticker", None)
            normalized.pop("tickers", None)
            return normalized
        normalized.pop("ticker", None)
        normalized.pop("tickers", None)
        return normalized

    if run_type in {"auto", "scan", "portfolio"}:
        normalized.pop("ticker", None)
        normalized.pop("tickers", None)
        return normalized

    if ticker:
        normalized["ticker"] = ticker
    else:
        normalized.pop("ticker", None)
    if tickers:
        normalized["tickers"] = tickers
    else:
        normalized.pop("tickers", None)
    return normalized
