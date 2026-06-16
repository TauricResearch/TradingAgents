from .fmp_common import make_request
from .symbol_utils import NoMarketDataError
from .vendor_utils import rows_to_csv


def _normalize_row(row: dict) -> dict:
    return {
        "date": str(row.get("date", ""))[:10],
        "open": row.get("open", ""),
        "high": row.get("high", ""),
        "low": row.get("low", ""),
        "close": row.get("close", ""),
        "volume": row.get("volume", ""),
    }


def get_stock(symbol: str, start_date: str, end_date: str) -> str:
    payload = make_request(
        "historical-price-eod/full",
        {"symbol": symbol, "from": start_date, "to": end_date},
    )
    rows = payload.get("historical", payload) if isinstance(payload, dict) else payload
    if not rows:
        raise NoMarketDataError(symbol, symbol, "FMP returned no EOD rows")
    normalized = [_normalize_row(row) for row in rows]
    normalized.sort(key=lambda row: row["date"])
    return rows_to_csv(normalized, ["date", "open", "high", "low", "close", "volume"])
