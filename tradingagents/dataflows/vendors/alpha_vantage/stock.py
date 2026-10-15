import json
from datetime import datetime
from pathlib import Path

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.vendors.alpha_vantage.common import (
    AlphaVantagePremiumEndpointError,
    _filter_csv_by_date_range,
    _make_api_request,
)


def _resolve_symbol(symbol: str) -> str:
    """Resolve a TradingAgents ticker to the vendor-specific registry symbol."""
    registry_path = Path(
        get_config().get("issuer_registry_path", "~/.tradingagents/german_equities.json")
    ).expanduser()
    if not registry_path.is_file():
        return symbol
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VendorUnavailableError(f"could not read instrument registry: {exc}") from None

    instruments = registry.get("instruments", {}) if isinstance(registry, dict) else {}
    wanted = symbol.strip().upper()
    if not isinstance(instruments, dict):
        raise VendorUnavailableError("instrument registry 'instruments' must be a JSON object")
    for key, record in instruments.items():
        if not isinstance(record, dict):
            continue
        aliases = record.get("aliases", [])
        candidates = [
            key,
            record.get("ticker"),
            record.get("isin"),
            record.get("wkn"),
            record.get("yahoo_symbol"),
            record.get("alpha_vantage_symbol"),
            *(aliases if isinstance(aliases, list) else []),
        ]
        if any(str(value).strip().upper() == wanted for value in candidates if value):
            provider_symbol = record.get("alpha_vantage_symbol")
            return str(provider_symbol).strip() if provider_symbol else symbol
    return symbol


def get_stock(
    symbol: str,
    start_date: str,
    end_date: str
) -> str:
    """
    Returns raw daily OHLCV values, adjusted close values, and historical split/dividend events
    filtered to the specified date range.

    Args:
        symbol: The name of the equity. For example: symbol=IBM
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        CSV string containing the daily adjusted time series data filtered to the date range.
    """
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    today = datetime.now()

    # Choose outputsize based on whether the requested range is within the latest 100 days
    # Compact returns latest 100 data points, so check if start_date is recent enough
    days_from_today_to_start = (today - start_dt).days
    outputsize = "compact" if days_from_today_to_start < 100 else "full"

    provider_symbol = _resolve_symbol(symbol)
    params = {
        "symbol": provider_symbol,
        "outputsize": outputsize,
        "datatype": "csv",
    }

    try:
        response = _make_api_request("TIME_SERIES_DAILY_ADJUSTED", params)
        filtered = _filter_csv_by_date_range(response, start_date, end_date)
        if not filtered.strip() or len(filtered.splitlines()) < 2:
            return ""
        # Name the price basis explicitly: the adjusted series reflects splits
        # and dividends, so a reader must not mistake it for raw prices (the
        # unadjusted fallback below carries its own contrasting label).
        return (
            f"# Alpha Vantage primary for {symbol} (queried as {provider_symbol}): "
            "TIME_SERIES_DAILY_ADJUSTED; close adjusted for splits and dividends.\n"
            + filtered
        )
    except AlphaVantagePremiumEndpointError:
        # The standard key can access the unadjusted daily series. Do not
        # silently imply corporate-action-adjusted prices when using this path.
        fallback_params = {
            "symbol": provider_symbol,
            "outputsize": outputsize,
            "datatype": "csv",
        }
        response = _make_api_request("TIME_SERIES_DAILY", fallback_params)
        filtered = _filter_csv_by_date_range(response, start_date, end_date)
        if not filtered.strip() or len(filtered.splitlines()) < 2:
            return ""
        return (
            f"# Alpha Vantage fallback for {symbol} (queried as {provider_symbol}): "
            "TIME_SERIES_DAILY; unadjusted OHLCV. "
            "Dividends and splits are not reflected in the close series.\n"
            + filtered
        )
