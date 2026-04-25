"""Alpha Vantage market-price fetchers for gold, oil, and bitcoin."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from .alpha_vantage_common import (
    AlphaVantageError,
    ThirdPartyParseError,
    _make_api_request,
)


def _parse_json(text: str, context: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ThirdPartyParseError(f"Failed to parse JSON response for {context}: {exc}") from exc


def _format_price_table(title: str, rows: list[dict[str, str]]) -> str:
    lines = [
        title,
        f"_Data retrieved on: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "| Asset | Symbol | Current Price | Change | Change % |",
        "|---|---|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['asset']} | {row['symbol']} | {row['current_price']} | {row['change']} | {row['percent_change']} |"
        )
    return "\n".join(lines)


def get_gold_price_alpha_vantage() -> str:
    text = _make_api_request("GOLD_SILVER_SPOT", {"symbol": "GOLD"})
    payload = _parse_json(text, "GOLD_SILVER_SPOT/GOLD")

    if "price" not in payload:
        raise AlphaVantageError(f"GOLD_SILVER_SPOT response missing price: {payload}")

    return _format_price_table(
        "# Gold Price Snapshot",
        [
            {
                "asset": "Gold",
                "symbol": payload.get("nominal", "XAUUSD"),
                "current_price": f"${float(payload['price']):,.2f}",
                "change": "N/A",
                "percent_change": "N/A",
            }
        ],
    )


def _parse_oil_row(function_name: str, asset: str, symbol: str) -> dict[str, str]:
    text = _make_api_request(function_name, {"interval": "daily"})
    payload = _parse_json(text, function_name)

    data = payload.get("data")
    if not isinstance(data, list) or len(data) < 2:
        raise AlphaVantageError(f"{function_name} response missing daily data rows: {payload}")

    latest = data[0]
    previous = data[1]
    current_price = float(latest["value"])
    previous_price = float(previous["value"])
    change = current_price - previous_price
    pct = (change / previous_price * 100) if previous_price else 0.0

    return {
        "asset": asset,
        "symbol": symbol,
        "current_price": f"${current_price:,.2f}",
        "change": f"{change:+.2f}",
        "percent_change": f"{pct:+.2f}%",
    }


def get_oil_prices_alpha_vantage() -> str:
    rows = [
        _parse_oil_row("WTI", "WTI Crude", "WTI"),
        _parse_oil_row("BRENT", "Brent Crude", "BRENT"),
    ]
    return _format_price_table("# Oil Price Snapshot", rows)


def get_bitcoin_price_alpha_vantage() -> str:
    text = _make_api_request(
        "CURRENCY_EXCHANGE_RATE",
        {"from_currency": "BTC", "to_currency": "USD"},
    )
    payload = _parse_json(text, "CURRENCY_EXCHANGE_RATE/BTCUSD")

    rate = payload.get("Realtime Currency Exchange Rate")
    if not isinstance(rate, dict):
        raise AlphaVantageError(f"CURRENCY_EXCHANGE_RATE response missing rate block: {payload}")

    current_price = float(rate["5. Exchange Rate"])
    return _format_price_table(
        "# Bitcoin Price Snapshot",
        [
            {
                "asset": "Bitcoin",
                "symbol": "BTC/USD",
                "current_price": f"${current_price:,.2f}",
                "change": "N/A",
                "percent_change": "N/A",
            }
        ],
    )
